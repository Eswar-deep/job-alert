# scrapers/ats/workday.py
"""
Polls every active Workday board in the registry.

    POST https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

Paginated: keep incrementing offset by the page size until it reaches `total`.

Workday's list endpoint has no absolute posting timestamp, only a relative
string ("Posted Today" / "Posted 3 Days Ago" / "Posted 30+ Days Ago"), and no
job description. Both come from a separate per-job detail call
(.../wday/cxs/{tenant}/{site}{externalPath}), which is expensive to make for
every listing on every poll — so instead of fetching it here, this scraper
stores the ready-to-fetch detail URL in Job.detail_ref, and pipeline/enrich.py
fetches it lazily, only for jobs that survive filtering + dedup.
"""
from __future__ import annotations

import asyncio
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from discovery import registry
from pipeline.types import Job
from scrapers.base import BaseScraper

PAGE_SIZE = 20
MAX_PAGES_PER_BOARD = 25  # safety cap: 500 postings/board is generous for a single poll

_RELATIVE_DAYS_RE = re.compile(r"(\d+)\s*\+?\s*day", re.IGNORECASE)
_REQ_ID_RE = re.compile(r"_([A-Za-z0-9\-]+)$")


def _parse_posted_on(raw: Optional[str], now: datetime) -> Optional[datetime]:
    """
    Workday only gives day-granularity relative text, not a timestamp — this
    is inherently coarser than Greenhouse/Lever/Ashby's exact timestamps, so
    latency metrics for Workday jobs are best-effort, not precise.
    """
    if not raw:
        return None
    text = raw.lower()
    if "today" in text:
        return now
    if "yesterday" in text:
        return now - timedelta(days=1)
    m = _RELATIVE_DAYS_RE.search(text)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None


def _req_id(posting: Dict[str, Any]) -> Optional[str]:
    bullets = posting.get("bulletFields")
    if isinstance(bullets, list) and bullets:
        return str(bullets[0])
    m = _REQ_ID_RE.search(posting.get("externalPath") or "")
    return m.group(1) if m else None


class WorkdayScraper(BaseScraper):
    name = "workday"
    concurrency = 15  # each board may need several sequential page requests

    def __init__(self, window_minutes: int = 15, max_boards: Optional[int] = None) -> None:
        self.window_minutes = window_minutes
        self.max_boards = max_boards

    @staticmethod
    def _list_url(tenant: str, wd: str, site: str) -> str:
        return f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"

    @staticmethod
    def _careers_base(tenant: str, wd: str, site: str) -> str:
        return f"https://{tenant}.{wd}.myworkdayjobs.com/{site}"

    @staticmethod
    def _detail_url(tenant: str, wd: str, site: str, external_path: str) -> str:
        return f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}"

    async def _fetch_page(
        self, session: aiohttp.ClientSession, url: str, offset: int
    ) -> Optional[Dict[str, Any]]:
        body = {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""}
        return await self.fetch_json(session, url, method="POST", json_body=body)

    async def _scrape_board(
        self,
        session: aiohttp.ClientSession,
        sem: asyncio.Semaphore,
        board: Dict[str, Any],
        cutoff: Optional[datetime],
        now: datetime,
    ) -> Tuple[str, Optional[List[Job]], int]:
        """Returns (registry_key, jobs or None on failure, total postings on board)."""
        extra = board.get("extra") or {}
        tenant = board["slug"]
        site = extra.get("site")
        wd = extra.get("wd", "wd1")
        if not site:
            return board["_id"], None, 0

        list_url = self._list_url(tenant, wd, site)
        careers_base = self._careers_base(tenant, wd, site)

        async with sem:
            first = await self._fetch_page(session, list_url, 0)
        if first is None or not isinstance(first, dict):
            return board["_id"], None, 0

        total = first.get("total")
        total = int(total) if isinstance(total, int) else 0
        all_postings: List[Dict[str, Any]] = list(first.get("jobPostings") or [])

        offset = PAGE_SIZE
        pages = 1
        while offset < total and pages < MAX_PAGES_PER_BOARD:
            async with sem:
                page = await self._fetch_page(session, list_url, offset)
            if page is None:
                break  # partial results beat none; stop paginating this board on error
            postings = page.get("jobPostings") or []
            if not postings:
                break
            all_postings.extend(postings)
            offset += PAGE_SIZE
            pages += 1

        out: List[Job] = []
        for p in all_postings:
            title = (p.get("title") or "").strip()
            external_path = p.get("externalPath") or ""
            req_id = _req_id(p)
            if not title or not external_path or not req_id:
                continue

            posted = _parse_posted_on(p.get("postedOn"), now)
            if cutoff is not None and (posted is None or posted < cutoff):
                continue

            out.append(
                Job(
                    id=f"workday:{tenant}:{req_id}",
                    title=title,
                    company=tenant,
                    url=f"{careers_base}{external_path}",
                    location=(p.get("locationsText") or "").strip(),
                    source="workday",
                    posted_date=posted,
                    description="",
                    detail_ref=self._detail_url(tenant, wd, site, external_path),
                )
            )

        return board["_id"], out, total

    async def scrape(self, session: aiohttp.ClientSession) -> List[Job]:
        boards = registry.get_active_boards(platform="workday")
        if self.max_boards:
            boards = boards[: self.max_boards]
        if not boards:
            print("[workday] No active boards in registry — run discovery.bootstrap first.")
            return []

        now = datetime.now(timezone.utc)
        cutoff: Optional[datetime] = None
        if self.window_minutes > 0:
            cutoff = now - timedelta(minutes=self.window_minutes)

        sem = asyncio.Semaphore(self.concurrency)
        results = await asyncio.gather(
            *(self._scrape_board(session, sem, b, cutoff, now) for b in boards)
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
            f"[workday] {len(boards)} boards | ok {len(successes)} | "
            f"failed {len(failures)} | jobs in window {len(jobs)}"
        )
        return jobs


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def _main() -> None:
        # window_minutes=0 disables the time filter (returns every open job).
        window = int(sys.argv[1]) if len(sys.argv) > 1 else 60
        scraper = WorkdayScraper(window_minutes=window)
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
