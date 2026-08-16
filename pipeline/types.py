# pipeline/types.py
"""Shared type contracts. Every layer imports from here — do not redefine locally."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Protocol, TypedDict


class Job(TypedDict):
    id: str                          # f"{platform}:{slug}:{ats_job_id}" — stable across polls
    title: str
    company: str
    url: str
    location: str
    source: str                      # the ATS platform, never an aggregator
    posted_date: Optional[datetime]  # tz-aware UTC
    description: str                 # plain text; "" until enrich.py fills it in
    detail_ref: str                  # fetchable URL enrich.py hits to fill description; "" if not needed


class ScoredJob(TypedDict):
    job: Job
    score: float                     # 0.0 - 1.0
    matched_skills: List[str]
    gaps: List[str]
    reason: str


class Matcher(Protocol):
    async def score(self, jobs: List[Job], profile: str) -> List[ScoredJob]: ...


class Notifier(Protocol):
    async def send(self, jobs: List[ScoredJob]) -> None: ...


def as_scored(job: Job, score: float = 0.5, reason: str = "") -> ScoredJob:
    """Wrap an unscored Job so rule-based paths can use the same Notifier interface."""
    return ScoredJob(job=job, score=score, matched_skills=[], gaps=[], reason=reason)