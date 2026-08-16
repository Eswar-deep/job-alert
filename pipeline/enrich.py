# pipeline/enrich.py
"""
Fills in Job.description for jobs whose scraper didn't return it inline
(Greenhouse, Workday) by fetching Job.detail_ref, the ready-to-fetch URL each
scraper already built for exactly this purpose. Lever/Ashby jobs already
carry a description and have detail_ref == "", so they're skipped here.

Runs only on post-dedup jobs, right before notification: enriching every job
seen this cycle would roughly double request volume for descriptions that
get thrown away the moment a job turns out to be a duplicate or irrelevant.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from pipeline.types import Job
from scrapers.base import strip_html

TIMEOUT = aiohttp.ClientTimeout(total=15)
CONCURRENCY = 10
RETRIES = 2


async def _fetch(session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
    for attempt in range(RETRIES + 1):
        try:
            async with session.get(url, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None  # gone/renamed: do not retry
                return await resp.json(content_type=None)
        except Exception:
            if attempt == RETRIES:
                return None
            await asyncio.sleep((2 ** attempt) * 0.5)
    return None


def _extract_description(source: str, data: Dict[str, Any]) -> str:
    if source == "greenhouse":
        return strip_html(data.get("content"))
    if source == "workday":
        info = data.get("jobPostingInfo") or {}
        return strip_html(info.get("jobDescription"))
    return ""


async def _enrich_one(session: aiohttp.ClientSession, sem: asyncio.Semaphore, job: Job) -> None:
    async with sem:
        data = await _fetch(session, job["detail_ref"])
    if data is not None:
        job["description"] = _extract_description(job["source"], data)


async def enrich_jobs(session: aiohttp.ClientSession, jobs: List[Job]) -> List[Job]:
    """Fills description in place for jobs that need it. Returns the same list
    (same dict objects) so callers can just keep using their existing reference."""
    needs_enrich = [j for j in jobs if not j["description"] and j["detail_ref"]]
    if not needs_enrich:
        return jobs

    sem = asyncio.Semaphore(CONCURRENCY)
    await asyncio.gather(*(_enrich_one(session, sem, j) for j in needs_enrich))

    filled = sum(1 for j in needs_enrich if j["description"])
    print(f"[enrich] filled description for {filled}/{len(needs_enrich)} jobs")
    return jobs
