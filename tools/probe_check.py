# tools/probe_check.py
"""
Diagnostic + re-validation tool for the ATS registry's probe functions.

  python -m tools.probe_check                       # audit: pass-rate per platform, no network
  python -m tools.probe_check --revalidate smartrecruiters workable
                                                      # re-probe active boards for these
                                                      # platforms, update job_count, retire
                                                      # boards that no longer respond

Background: discovery/bootstrap.py validates a candidate board by calling that
platform's probe and treating "not None" as live. Greenhouse/Lever/Ashby/Workable
all return HTTP 404 for a nonexistent company slug, so their probes correctly
return None. SmartRecruiters instead returns HTTP 200 with {"totalFound": 0}
for a nonexistent slug (soft-404), so a candidate that doesn't exist at all
still validates with job_count=0. That's why smartrecruiters/workable showed a
100% pass rate in the registry (0 dead candidates) while every other platform
sees realistic 3-8% dead links from historical churn.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from typing import List

import aiohttp

from discovery import registry
from discovery.bootstrap import PROBES
from discovery.slug_extractor import ATSCandidate

PROBE_TIMEOUT = aiohttp.ClientTimeout(total=15)
CONCURRENCY = 20


def audit() -> None:
    """Read-only: pass-rate per platform from what's already in the registry."""
    coll = registry.get_collection()
    if coll is None:
        print("[probe_check] No Mongo connection — audit needs the registry, aborting.")
        return

    active: Counter = Counter()
    inactive: Counter = Counter()
    zero_job_count: Counter = Counter()
    for doc in coll.find({}):
        plat = doc.get("platform")
        if doc.get("active"):
            active[plat] += 1
            if doc.get("job_count", 0) == 0:
                zero_job_count[plat] += 1
        else:
            inactive[plat] += 1

    print(f"{'platform':<16}{'active':<8}{'dead':<8}{'total':<8}{'pass_rate':<11}{'zero_job_count'}")
    for plat in sorted(set(active) | set(inactive)):
        a, d = active[plat], inactive[plat]
        total = a + d
        rate = f"{a / total * 100:.1f}%" if total else "n/a"
        print(f"{plat:<16}{a:<8}{d:<8}{total:<8}{rate:<11}{zero_job_count[plat]}")


async def revalidate(platforms: List[str]) -> None:
    """Re-probe currently-active boards for the given platforms against the live APIs."""
    boards = []
    for plat in platforms:
        boards.extend(registry.get_active_boards(plat))
    if not boards:
        print(f"[probe_check] No active boards found for {platforms}.")
        return

    print(f"[probe_check] Re-probing {len(boards)} boards across {platforms}...")
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _check(session: aiohttp.ClientSession, doc: dict):
        probe = PROBES.get(doc["platform"])
        if probe is None:
            return doc, None
        cand = ATSCandidate(doc["platform"], doc["slug"], doc.get("extra", {}))
        async with sem:
            try:
                count = await probe(session, cand)
                return doc, count
            except Exception:
                return doc, None

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*(_check(session, doc) for doc in boards))

    alive = [(doc, n) for doc, n in results if n is not None and n > 0]
    zero = [(doc, n) for doc, n in results if n == 0]
    dead = [doc for doc, n in results if n is None]

    registry.bulk_mark_success([(doc["_id"], n) for doc, n in alive])
    for doc in dead:
        registry.mark_failure(doc["_id"])
    for doc, _ in zero:
        registry.mark_failure(doc["_id"])  # 0 postings is indistinguishable from soft-404; retire on repeated 0s

    print(f"[probe_check] {len(alive)} confirmed live, {len(zero)} returned 0 postings, {len(dead)} unreachable.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--revalidate", nargs="+", metavar="PLATFORM",
        help="re-probe active boards for these platforms and update the registry",
    )
    args = parser.parse_args()

    if args.revalidate:
        asyncio.run(revalidate(args.revalidate))
    else:
        audit()


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
