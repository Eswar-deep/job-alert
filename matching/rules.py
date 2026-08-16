# matching/rules.py
"""
Deterministic filter. No LLM, no network, no cost.

This is both the V1 filter and the control condition for evaluating the
match engine later (see 05-V2-PIPELINE.md, M6). Every stage reports how many
jobs it dropped so the thresholds can be tuned against real output instead
of guessed at.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Tuple

from pipeline.types import Job

# --------------------------------------------------------------------------- #
# Vocabulary — edit these, not the logic                                       #
# --------------------------------------------------------------------------- #

# A title must hit one of these to be considered relevant at all.
DOMAIN = re.compile(
    r"\b("
    r"software|swe|sde|developer|programmer|"
    r"backend|back[- ]end|frontend|front[- ]end|full[- ]?stack|"
    r"data (engineer|scientist|analyst)|analytics|"
    r"machine learning|ml|ai|deep learning|nlp|computer vision|"
    r"devops|site reliability|sre|platform|infrastructure|cloud|"
    r"systems? engineer|embedded|distributed"
    r")\b",
    re.IGNORECASE,
)

# Seniority disqualifiers.
SENIOR = re.compile(
    r"\b("
    r"senior|sr\.?|staff|principal|lead|architect|"
    r"manager|director|head of|vp|vice president|chief|"
    r"ii+|iv|v|3|4|5"          # Engineer II / III / IV / L4 style
    r")\b",
    re.IGNORECASE,
)

# Explicit entry-level markers — a hit here overrides a weak domain signal.
ENTRY = re.compile(
    r"\b("
    r"new ?grad|graduate|entry[- ]level|junior|jr\.?|"
    r"associate|university|campus|early career|"
    r"intern|internship|co[- ]?op|apprentice|"
    r"i\b|level 1|l1"
    r")\b",
    re.IGNORECASE,
)

# Years-of-experience gate: "5+ years", "minimum 7 years"
YOE = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?year", re.IGNORECASE)
MAX_YOE = 2

# Non-engineering roles that sneak past DOMAIN via words like "platform".
NEGATIVE = re.compile(
    r"\b("
    r"sales|account executive|recruiter|recruiting|marketing|"
    r"customer success|support specialist|technician|"
    r"nurse|clinical|physician|therapist|scientist, |liaison|"
    r"attorney|paralegal|accountant|controller"
    r")\b",
    re.IGNORECASE,
)

# Optional location gate. Empty list = allow everything.
ALLOWED_LOCATION = re.compile(
    r"(united states|usa|u\.s\.|remote|"
    r"texas|dallas|austin|houston|"
    r"california|san francisco|bay area|seattle|new york|nyc|boston|chicago|"
    r"atlanta|denver|los angeles|san jose|san diego)",
    re.IGNORECASE,
)
ENFORCE_LOCATION = False  # flip to True once you trust the other stages


def content_hash(job: Job) -> str:
    """
    Collapses the same role posted across many locations into one key.
    Deliberately excludes location and job id.
    """
    basis = f"{job['company'].lower()}|{re.sub(r'[^a-z0-9 ]', '', job['title'].lower())}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def is_relevant(job: Job, strict: bool = True) -> Tuple[bool, str]:
    """
    Returns (keep, reason). Reason explains the rejection when keep is False.

    strict=True is the full V1 filter (also seniority/YOE). strict=False only
    strips obvious non-engineering roles and off-domain titles; the SENIOR and
    YOE gates are skipped so a downstream LLM can make the seniority call with
    more context (description, not just title) than this regex has.
    """
    title = job["title"]

    if NEGATIVE.search(title):
        return False, "non-engineering role"

    domain_hit = bool(DOMAIN.search(title))
    entry_hit = bool(ENTRY.search(title))

    if not domain_hit and not entry_hit:
        return False, "no domain match"

    if strict:
        # "Senior" kills it unless the title also explicitly says intern/new grad
        # (e.g. some boards post "Senior Intern" nonsense; entry wins).
        if SENIOR.search(title) and not entry_hit:
            return False, "senior-level"

        m = YOE.search(title)
        if m and int(m.group(1)) > MAX_YOE:
            return False, f"{m.group(1)}+ years required"

    if ENFORCE_LOCATION and job.get("location"):
        if not ALLOWED_LOCATION.search(job["location"]):
            return False, "location out of scope"

    return True, "match"


def filter_jobs(jobs: List[Job], verbose: bool = True, strict: bool = True) -> List[Job]:
    """Filter plus per-reason drop counts, then collapse duplicate roles."""
    kept: List[Job] = []
    reasons: Dict[str, int] = {}

    for job in jobs:
        ok, reason = is_relevant(job, strict=strict)
        if ok:
            kept.append(job)
        else:
            reasons[reason] = reasons.get(reason, 0) + 1

    # Collapse multi-location / bulk-edit duplicates of the same role.
    seen: Dict[str, Job] = {}
    for job in kept:
        seen.setdefault(content_hash(job), job)
    deduped = list(seen.values())

    if verbose:
        print(f"[rules] {len(jobs)} in -> {len(kept)} relevant -> {len(deduped)} after dedup")
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"        dropped {n:>5}  {reason}")

    return deduped