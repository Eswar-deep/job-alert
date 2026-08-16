# scrapers/ats/greenhouse.py
"""
Polls every active Greenhouse board in the registry.

    GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs

No auth, no HTML, no Playwright. Content bodies are omitted — they roughly
triple the payload and are only needed at match time, not detection time.

Time filtering uses `updated_at`, which changes on edit as well as creation,
so a re-edited posting can resurface. Mongo dedup on job id absorbs that.
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from discovery import registry
from pipeline.types import Job
from scrapers.base import BaseScraper

US_HOST = "boards-api.greenhouse.io"
EU_HOST = "boards-api.eu.greenhouse.io"


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    """Greenhouse emits ISO-8601 with an offset; tolerate a trailing Z too."""
    if not raw:
        return None
    try:
        cleaned = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


class GreenhouseScraper(BaseScraper):
    name = "greenhouse"
    concurrency = 25

    def __init__(self, window_minutes: int = 15, max_boards: Optional[int] = None) -> None:
        self.window_minutes = window_minutes
        self.max_boards = max_boards

    def _url(self, board: Dict[str, Any]) -> str:
        host = EU_HOST if (board.get("extra") or {}).get("region") == "eu" else US_HOST
        return f"https://{host}/v1/boards/{board['slug']}/jobs"

    async def _scrape_board(
        self,
        session: aiohttp.ClientSession,
        sem: asyncio.Semaphore,
        board: Dict[str, Any],
        cutoff: Optional[datetime],
    ) -> Tuple[str, Optional[List[Job]], int]:
        """Returns (registry_key, jobs or None on failure, total jobs on board)."""
        async with sem:
            data = await self.fetch_json(session, self._url(board))

        if data is None or not isinstance(data, dict):
            return board["_id"], None, 0

        raw_jobs = data.get("jobs") or []
        slug = board["slug"]
        out: List[Job] = []

        for j in raw_jobs:
            job_id = j.get("id")
            title = (j.get("title") or "").strip()
            url = j.get("absolute_url") or ""
            if not job_id or not title or not url:
                continue

            posted = _parse_ts(j.get("updated_at") or j.get("first_published"))
            if cutoff is not None and (posted is None or posted < cutoff):
                continue

            location = ""
            loc = j.get("location")
            if isinstance(loc, dict):
                location = (loc.get("name") or "").strip()

            out.append(
                Job(
                    id=f"greenhouse:{slug}:{job_id}",
                    title=title,
                    company=slug,
                    url=url,
                    location=location,
                    source="greenhouse",
                    posted_date=posted,
                    description="",  # omitted by design; enrich.py fetches on demand
                    detail_ref=f"https://{EU_HOST if (board.get('extra') or {}).get('region') == 'eu' else US_HOST}/v1/boards/{slug}/jobs/{job_id}?questions=false",
                )
            )

        return board["_id"], out, len(raw_jobs)

    async def scrape(self, session: aiohttp.ClientSession) -> List[Job]:
        boards = registry.get_active_boards(platform="greenhouse")
        if self.max_boards:
            boards = boards[: self.max_boards]
        if not boards:
            print("[greenhouse] No active boards in registry — run discovery.bootstrap first.")
            return []

        cutoff: Optional[datetime] = None
        if self.window_minutes > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.window_minutes)

        sem = asyncio.Semaphore(self.concurrency)
        results = await asyncio.gather(
            *(self._scrape_board(session, sem, b, cutoff) for b in boards)
        )

        jobs: List[Job] = []
        successes: List[Tuple[str, int]] = []
        failures: List[str] = []

        for key, board_jobs, total in results:
            if board_jobs is None:
                failures.append(key)
                continue
            successes.append((key, total))
            jobs.extend(board_jobs)

        registry.bulk_mark_success(successes)
        for key in failures[:100]:  # cap the write amplification on a bad cycle
            registry.mark_failure(key)

        print(
            f"[greenhouse] {len(boards)} boards | ok {len(successes)} | "
            f"failed {len(failures)} | jobs in window {len(jobs)}"
        )
        return jobs


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def _main() -> None:
        # window_minutes=0 disables the time filter (returns every open job).
        window = int(sys.argv[1]) if len(sys.argv) > 1 else 60
        scraper = GreenhouseScraper(window_minutes=window)
        async with aiohttp.ClientSession() as session:
            jobs = await scraper.scrape(session)

        print(f"\nWindow: last {window} min" if window else "\nWindow: all open jobs")
        by_company = Counter(j["company"] for j in jobs)
        print(f"Distinct companies with hits: {len(by_company)}")
        for j in jobs[:15]:
            when = j["posted_date"].isoformat() if j["posted_date"] else "?"
            print(f"  {when}  {j['company']:<22} {j['title'][:60]}")
        if len(jobs) > 15:
            print(f"  ... and {len(jobs) - 15} more")

    asyncio.run(_main())