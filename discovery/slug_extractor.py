# discovery/slug_extractor.py
"""
Pure-function extraction of ATS platform + company slug from arbitrary job URLs.

Every job URL flowing through the pipeline (from any source) can be passed to
`extract_slug()`. If it matches a known ATS pattern, we get back a candidate
company board that can be validated and polled directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs


@dataclass(frozen=True)
class ATSCandidate:
    platform: str                     # "greenhouse" | "lever" | "ashby" | "workday" | "smartrecruiters" | "recruitee" | "workable"
    slug: str                         # company identifier on that platform
    extra: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def key(self) -> str:
        # Workday needs tenant+site to be unique; others just slug.
        if self.platform == "workday":
            return f"workday:{self.slug}:{self.extra.get('site', '')}"
        return f"{self.platform}:{self.slug}"


_SLUG_RE = r"[A-Za-z0-9._\-]+"

_GREENHOUSE_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io")
_LEVER_HOSTS = ("jobs.lever.co", "jobs.eu.lever.co")

_WORKDAY_HOST_RE = re.compile(
    rf"^(?P<tenant>{_SLUG_RE})\.(?P<wd>wd\d+)\.myworkdayjobs\.com$", re.IGNORECASE
)
_RECRUITEE_HOST_RE = re.compile(
    rf"^(?P<slug>{_SLUG_RE})\.recruitee\.com$", re.IGNORECASE
)
_LOCALE_SEG_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")


def _first_path_segment(path: str) -> Optional[str]:
    segs = [s for s in path.split("/") if s]
    return segs[0] if segs else None


def extract_slug(url: str) -> Optional[ATSCandidate]:
    """Return an ATSCandidate if `url` points at a recognized ATS board, else None."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None

    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    segs = [s for s in path.split("/") if s]

    # --- Greenhouse ---------------------------------------------------------
    if host in _GREENHOUSE_HOSTS:
        region = "eu" if ".eu." in host else "us"
        if segs and segs[0].lower() == "embed":
            # boards.greenhouse.io/embed/job_board?for=<slug>
            qs = parse_qs(parsed.query)
            slug = (qs.get("for") or [None])[0]
            if slug:
                return ATSCandidate("greenhouse", slug.lower(), {"region": region})
            return None
        slug = _first_path_segment(path)
        if slug:
            return ATSCandidate("greenhouse", slug.lower(), {"region": region})
        return None

    # --- Lever --------------------------------------------------------------
    if host in _LEVER_HOSTS:
        region = "eu" if host.startswith("jobs.eu.") else "us"
        slug = _first_path_segment(path)
        if slug:
            return ATSCandidate("lever", slug.lower(), {"region": region})
        return None

    # --- Ashby --------------------------------------------------------------
    if host == "jobs.ashbyhq.com":
        slug = _first_path_segment(path)
        if slug and slug.lower() not in ("api",):
            return ATSCandidate("ashby", slug, {})  # Ashby slugs are case-sensitive
        return None

    # --- Workday ------------------------------------------------------------
    m = _WORKDAY_HOST_RE.match(host)
    if m:
        tenant = m.group("tenant").lower()
        wd = m.group("wd").lower()
        # Path is either /<site>/... or /<locale>/<site>/...
        site: Optional[str] = None
        if segs:
            if _LOCALE_SEG_RE.match(segs[0]) and len(segs) >= 2:
                site = segs[1]
            else:
                site = segs[0]
        if site and site.lower() not in ("wday",):
            return ATSCandidate("workday", tenant, {"site": site, "wd": wd})
        return None

    # --- SmartRecruiters ----------------------------------------------------
    if host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"):
        slug = _first_path_segment(path)
        if slug:
            return ATSCandidate("smartrecruiters", slug, {})
        return None

    # --- Recruitee ----------------------------------------------------------
    m = _RECRUITEE_HOST_RE.match(host)
    if m:
        return ATSCandidate("recruitee", m.group("slug").lower(), {})

    # --- Workable -----------------------------------------------------------
    if host == "apply.workable.com":
        slug = _first_path_segment(path)
        if slug and slug.lower() not in ("j", "api"):
            return ATSCandidate("workable", slug.lower(), {})
        return None

    return None


def extract_all_from_text(text: str) -> list[ATSCandidate]:
    """Scan an arbitrary blob (README, listings.json dump, HTML) for ATS URLs."""
    url_re = re.compile(r"""https?://[^\s"'<>)\]\\,]+""")
    seen: dict[str, ATSCandidate] = {}
    for raw in url_re.findall(text):
        cand = extract_slug(raw)
        if cand and cand.key not in seen:
            seen[cand.key] = cand
    return list(seen.values())
