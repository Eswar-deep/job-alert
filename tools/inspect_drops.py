# tools/inspect_drops.py
"""
Shows exactly which titles the filter rejected and why, so the regexes get
tuned against real postings instead of guesses.

    python -m tools.inspect_drops 240

Read the "no domain match" list closely — that is where false negatives live.
"""
from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from typing import Dict, List

import aiohttp

from matching.rules import is_relevant
from scrapers.ats.greenhouse import GreenhouseScraper


async def main() -> None:
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 240
    async with aiohttp.ClientSession() as session:
        jobs = await GreenhouseScraper(window_minutes=window).scrape(session)

    kept: List[str] = []
    dropped: Dict[str, List[str]] = defaultdict(list)

    for job in jobs:
        ok, reason = is_relevant(job)
        label = f"{job['company'][:20]:<20} {job['title'][:70]}"
        if ok:
            kept.append(label)
        else:
            dropped[reason].append(label)

    print(f"\n=== KEPT ({len(kept)}) ===")
    for line in kept:
        print("  " + line)

    for reason in sorted(dropped, key=lambda r: -len(dropped[r])):
        print(f"\n=== DROPPED: {reason} ({len(dropped[reason])}) ===")
        for line in dropped[reason][:60]:
            print("  " + line)
        if len(dropped[reason]) > 60:
            print(f"  ... {len(dropped[reason]) - 60} more")


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())