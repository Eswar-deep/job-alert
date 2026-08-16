# discovery/bootstrap.py
"""
One-shot (re-runnable, idempotent) discovery bootstrap.

  1. Pull machine-readable job datasets that are dense with ATS apply-URLs
     (SimplifyJobs listings.json files contain thousands of historical entries).
  2. Extract (platform, slug) candidates via discovery.slug_extractor.
  3. Probe each candidate's public ATS API concurrently to confirm the board
     is live, and record its current job count.
  4. Upsert everything into the Mongo registry (`ats_companies`).

Run:  python -m discovery.bootstrap
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from typing import Optional

import aiohttp

from discovery.slug_extractor import ATSCandidate, extract_all_from_text, extract_slug
from discovery import registry

# Dense, machine-readable sources of ATS URLs. Add more freely — extraction
# is regex-over-text, so any blob containing apply links works.
SEED_SOURCES: list[str] = [
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
    "https://raw.githubusercontent.com/vanshb03/New-Grad-2026/refs/heads/dev/README.md",
]

FETCH_TIMEOUT = aiohttp.ClientTimeout(total=30)
PROBE_TIMEOUT = aiohttp.ClientTimeout(total=15)
CONCURRENCY = 20

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


# --------------------------------------------------------------------------- #
# Validation probes — one per platform. Return job count if live, else None.  #
# --------------------------------------------------------------------------- #

async def _probe_greenhouse(session: aiohttp.ClientSession, c: ATSCandidate) -> Optional[int]:
    base = "boards-api.eu.greenhouse.io" if c.extra.get("region") == "eu" else "boards-api.greenhouse.io"
    url = f"https://{base}/v1/boards/{c.slug}/jobs"
    async with session.get(url, timeout=PROBE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        return len(data.get("jobs", []))


async def _probe_lever(session: aiohttp.ClientSession, c: ATSCandidate) -> Optional[int]:
    base = "api.eu.lever.co" if c.extra.get("region") == "eu" else "api.lever.co"
    url = f"https://{base}/v0/postings/{c.slug}?mode=json"
    async with session.get(url, timeout=PROBE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        return len(data) if isinstance(data, list) else None


async def _probe_ashby(session: aiohttp.ClientSession, c: ATSCandidate) -> Optional[int]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{c.slug}"
    async with session.get(url, timeout=PROBE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        jobs = data.get("jobs")
        return len(jobs) if isinstance(jobs, list) else None


async def _probe_workday(session: aiohttp.ClientSession, c: ATSCandidate) -> Optional[int]:
    site = c.extra.get("site")
    wd = c.extra.get("wd", "wd1")
    if not site:
        return None
    url = f"https://{c.slug}.{wd}.myworkdayjobs.com/wday/cxs/{c.slug}/{site}/jobs"
    payload = {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}
    async with session.post(url, json=payload, timeout=PROBE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        total = data.get("total")
        return int(total) if isinstance(total, int) else None


async def _probe_smartrecruiters(session: aiohttp.ClientSession, c: ATSCandidate) -> Optional[int]:
    # SmartRecruiters returns HTTP 200 with totalFound=0 for a company slug that
    # doesn't exist at all (soft-404) — indistinguishable from a real company with
    # zero open postings, so treat 0 as "not live" rather than a valid board.
    url = f"https://api.smartrecruiters.com/v1/companies/{c.slug}/postings?limit=1"
    async with session.get(url, timeout=PROBE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        total = data.get("totalFound")
        if not isinstance(total, int) or total <= 0:
            return None
        return total


async def _probe_recruitee(session: aiohttp.ClientSession, c: ATSCandidate) -> Optional[int]:
    url = f"https://{c.slug}.recruitee.com/api/offers/"
    async with session.get(url, timeout=PROBE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        offers = data.get("offers")
        return len(offers) if isinstance(offers, list) else None


async def _probe_workable(session: aiohttp.ClientSession, c: ATSCandidate) -> Optional[int]:
    url = f"https://apply.workable.com/api/v1/widget/accounts/{c.slug}?details=false"
    async with session.get(url, timeout=PROBE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        jobs = data.get("jobs")
        return len(jobs) if isinstance(jobs, list) else None


PROBES = {
    "greenhouse": _probe_greenhouse,
    "lever": _probe_lever,
    "ashby": _probe_ashby,
    "workday": _probe_workday,
    "smartrecruiters": _probe_smartrecruiters,
    "recruitee": _probe_recruitee,
    "workable": _probe_workable,
}


async def validate_candidate(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    c: ATSCandidate,
) -> tuple[ATSCandidate, Optional[int]]:
    probe = PROBES.get(c.platform)
    if probe is None:
        return c, None
    async with sem:
        try:
            count = await probe(session, c)
            return c, count
        except Exception:
            return c, None


# --------------------------------------------------------------------------- #
# Harvesting                                                                   #
# --------------------------------------------------------------------------- #

async def fetch_seed_text(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=FETCH_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.text()
    except Exception as e:
        print(f"[Bootstrap] Failed to fetch {url}: {e}")
        return ""


def harvest_from_url(url: str) -> Optional[ATSCandidate]:
    """
    Continuous-discovery hook: call this with every job URL the pipeline sees
    (from Notify, GitHub repos, anywhere). New boards land in the registry
    inactive and get validated on the next bootstrap/validation pass.
    """
    cand = extract_slug(url)
    if cand is not None:
        registry.upsert_candidates([cand], validated=False)
    return cand


async def run_bootstrap() -> None:
    async with aiohttp.ClientSession(headers={"User-Agent": _UA}) as session:
        # 1. Harvest candidates from seed sources
        texts = await asyncio.gather(*(fetch_seed_text(session, u) for u in SEED_SOURCES))
        candidates: dict[str, ATSCandidate] = {}
        for text in texts:
            for cand in extract_all_from_text(text):
                candidates[cand.key] = cand

        # Also include anything previously harvested but never validated
        for doc in registry.get_unvalidated(limit=5000):
            cand = ATSCandidate(doc["platform"], doc["slug"], doc.get("extra", {}))
            candidates.setdefault(cand.key, cand)

        by_plat = Counter(c.platform for c in candidates.values())
        print(f"[Bootstrap] {len(candidates)} unique candidate boards extracted.")
        for plat, n in by_plat.most_common():
            print(f"             {plat:<16} {n}")
        if not candidates:
            print("[Bootstrap] Nothing extracted — seed fetch or parsing failed. Aborting.")
            return
        print("[Bootstrap] Probing live APIs...")

        # 2. Validate concurrently
        sem = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(
            *(validate_candidate(session, sem, c) for c in candidates.values())
        )

        live = [(c, n) for c, n in results if n is not None]
        dead = [c for c, n in results if n is None]

        # 3. Persist
        print(f"[Bootstrap] Probing done. Persisting {len(live)} live / {len(dead)} dead...")
        registry.upsert_candidates([c for c, _ in live], validated=True)
        registry.bulk_mark_success([(c.key, n) for c, n in live])
        registry.upsert_candidates(dead, validated=False)  # keep for retry/inspection

        by_platform: dict[str, int] = {}
        for c, _ in live:
            by_platform[c.platform] = by_platform.get(c.platform, 0) + 1
        print(f"[Bootstrap] {len(live)} live boards validated, {len(dead)} unreachable.")
        print(f"[Bootstrap] Live by platform: {json.dumps(by_platform, indent=2)}")


if __name__ == "__main__":
    # Windows ProactorEventLoop spams "Event loop is closed" on aiohttp teardown.
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_bootstrap())