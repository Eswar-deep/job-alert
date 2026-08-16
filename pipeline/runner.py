# pipeline/runner.py
"""
Ties the pieces together: poll -> filter -> dedup -> latency -> notify.

    python -m pipeline.runner --seed        # populate Mongo, notify nothing
    python -m pipeline.runner --once        # one cycle
    python -m pipeline.runner               # loop forever at POLL_SECONDS

Notification is optional and off unless NTFY_TOPIC is set, so this runs today
without any notifier configured.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiohttp

from matching.rules import filter_jobs
from pipeline.enrich import enrich_jobs
from pipeline.types import Job, ScoredJob, as_scored
from scrapers.ats.ashby import AshbyScraper
from scrapers.ats.greenhouse import GreenhouseScraper
from scrapers.ats.lever import LeverScraper
from scrapers.ats.workday import WorkdayScraper
from scrapers.base import BaseScraper
from storage.db import store_job_if_new

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
WINDOW_MINUTES = int(os.getenv("WINDOW_MINUTES", "15"))
METRICS_PATH = Path("metrics") / "latency.jsonl"


def _record_latency(jobs: List[Job], detected_at: datetime) -> Optional[float]:
    """
    Append detected_at - posted_date per job. This is the project's headline
    metric (M3); without it "real-time" is an unsupported claim.
    Returns the median for this cycle, in seconds.
    """
    samples = []
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METRICS_PATH.open("a", encoding="utf-8") as f:
        for job in jobs:
            posted = job.get("posted_date")
            if not posted:
                continue
            lag = (detected_at - posted).total_seconds()
            if lag < 0:
                continue  # clock skew on the ATS side
            samples.append(lag)
            f.write(json.dumps({
                "job_id": job["id"],
                "source": job["source"],
                "posted_at": posted.isoformat(),
                "detected_at": detected_at.isoformat(),
                "lag_seconds": round(lag, 1),
            }) + "\n")
    return statistics.median(samples) if samples else None


async def _notify(scored: List[ScoredJob]) -> None:
    if not scored or not os.getenv("NTFY_TOPIC"):
        return
    try:
        from notify.ntfy import NtfyNotifier
    except ImportError:
        print("[runner] NTFY_TOPIC set but notify/ntfy.py missing; skipping.")
        return
    await NtfyNotifier().send(scored)


def _build_scrapers(window_minutes: int) -> List[BaseScraper]:
    return [
        GreenhouseScraper(window_minutes=window_minutes),
        LeverScraper(window_minutes=window_minutes),
        AshbyScraper(window_minutes=window_minutes),
        WorkdayScraper(window_minutes=window_minutes),
    ]


async def _scrape_all(session: aiohttp.ClientSession, scrapers: List[BaseScraper]) -> List[Job]:
    """Runs every scraper concurrently; one platform failing outright must not
    drop the others' results for this cycle."""
    results = await asyncio.gather(
        *(s.scrape(session) for s in scrapers), return_exceptions=True
    )

    jobs: List[Job] = []
    for scraper, result in zip(scrapers, results):
        if isinstance(result, BaseException):
            print(f"[runner] {scraper.name} scraper failed: {type(result).__name__}: {result}")
            continue
        jobs.extend(result)
    return jobs


async def run_cycle(session: aiohttp.ClientSession, seed: bool = False) -> int:
    scrapers = _build_scrapers(window_minutes=0 if seed else WINDOW_MINUTES)
    jobs = await _scrape_all(session, scrapers)
    if not jobs:
        return 0

    detected_at = datetime.now(timezone.utc)
    # strict=False: only strip obvious non-engineering/off-domain titles here.
    # Seniority judgment is deferred to the LLM matcher downstream, which has
    # the full job description to work with instead of just a title.
    relevant = filter_jobs(jobs, verbose=True, strict=False)

    median_lag = _record_latency(relevant, detected_at)
    if median_lag is not None:
        print(f"[runner] median detection lag this cycle: {median_lag / 60:.1f} min")

    fresh: List[Job] = []
    for job in relevant:
        if store_job_if_new(job["id"], job["source"], job["title"], job["company"], job["url"]):
            fresh.append(job)

    if seed:
        print(f"[runner] SEEDED {len(fresh)} jobs into Mongo. No notifications sent.")
        return len(fresh)

    print(f"[runner] {len(fresh)} genuinely new after dedup")
    if fresh:
        fresh = await enrich_jobs(session, fresh)
        for job in fresh:
            print(f"   -> {job['company']:<24} {job['title'][:60]}")
        await _notify([as_scored(j, reason="keyword match") for j in fresh])
    return len(fresh)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true",
                        help="store every open job without notifying")
    parser.add_argument("--once", action="store_true", help="single cycle then exit")
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        if args.seed or args.once:
            await run_cycle(session, seed=args.seed)
            return
        print(f"[runner] polling every {POLL_SECONDS}s, window {WINDOW_MINUTES}min")
        while True:
            try:
                await run_cycle(session)
            except Exception as e:
                print(f"[runner] cycle failed: {type(e).__name__}: {e}")
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())