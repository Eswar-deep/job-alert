# scrapers/ats/lever.py
"""
Polls every active Lever board in the registry.

    GET https://api.lever.co/v0/postings/{slug}?mode=json

No auth. Unlike Greenhouse, Lever's postings endpoint returns the full job
description inline (descriptionPlain / description), so no enrich step is
needed for Lever jobs.

Lever has no updatedAt field on a posting, only createdAt (epoch ms), so
that's the only signal available for the time window.
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
from scrapers.base import BaseScraper, strip_html

US_HOST = "api.lever.co"
EU_HOST = "api.eu.lever.co"


def _parse_epoch_ms(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
    except Exception:
        return None


class LeverScraper(BaseScraper):
    name = "lever"
    concurrency = 25

    def __init__(self, window_minutes: int = 15, max_boards: Optional[int] = None) -> None:
        self.window_minutes = window_minutes
        self.max_boards = max_boards

    def _url(self, board: Dict[str, Any]) -> str:
        host = EU_HOST if (board.get("extra") or {}).get("region") == "eu" else US_HOST
        return f"https://{host}/v0/postings/{board['slug']}?mode=json"

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

        if data is None or not isinstance(data, list):
            return board["_id"], None, 0

        slug = board["slug"]
        out: List[Job] = []

        for j in data:
            job_id = j.get("id")
            title = (j.get("text") or "").strip()
            url = j.get("hostedUrl") or j.get("applyUrl") or ""
            if not job_id or not title or not url:
                continue

            posted = _parse_epoch_ms(j.get("createdAt"))
            if cutoff is not None and (posted is None or posted < cutoff):
                continue

            categories = j.get("categories") or {}
            location = (categories.get("location") or "").strip()
            if not location:
                all_locs = categories.get("allLocations")
                if isinstance(all_locs, list) and all_locs:
                    location = ", ".join(all_locs)

            description = (j.get("descriptionPlain") or "").strip()
            if not description:
                description = strip_html(j.get("description"))

            out.append(
                Job(
                    id=f"lever:{slug}:{job_id}",
                    title=title,
                    company=slug,
                    url=url,
                    location=location,
                    source="lever",
                    posted_date=posted,
                    description=description,
                    detail_ref="",  # full description already inline; no enrich needed
                )
            )

        return board["_id"], out, len(data)

    async def scrape(self, session: aiohttp.ClientSession) -> List[Job]:
        boards = registry.get_active_boards(platform="lever")
        if self.max_boards:
            boards = boards[: self.max_boards]
        if not boards:
            print("[lever] No active boards in registry — run discovery.bootstrap first.")
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
            f"[lever] {len(boards)} boards | ok {len(successes)} | "
            f"failed {len(failures)} | jobs in window {len(jobs)}"
        )
        return jobs


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def _main() -> None:
        # window_minutes=0 disables the time filter (returns every open job).
        window = int(sys.argv[1]) if len(sys.argv) > 1 else 60
        scraper = LeverScraper(window_minutes=window)
        async with aiohttp.ClientSession() as session:
            jobs = await scraper.scrape(session)

        print(f"\nWindow: last {window} min" if window else "\nWindow: all open jobs")
        by_company = Counter(j["company"] for j in jobs)
        print(f"Distinct companies with hits: {len(by_company)}")
        with_desc = sum(1 for j in jobs if j["description"])
        print(f"Jobs with a description inline: {with_desc}/{len(jobs)}")
        for j in jobs[:15]:
            when = j["posted_date"].isoformat() if j["posted_date"] else "?"
            print(f"  {when}  {j['company']:<22} {j['title'][:60]}")
        if len(jobs) > 15:
            print(f"  ... and {len(jobs) - 15} more")

    asyncio.run(_main())
