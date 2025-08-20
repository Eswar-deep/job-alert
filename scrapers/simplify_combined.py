# scrapers/simplify_combined.py
from typing import Optional, List, Dict, Set, Tuple
import re
import requests

NEW_GRAD_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"
OFF_SEASON_URL = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README-Off-Season.md"

# Sources and their sections
SIMPLIFY_SOURCES: List[Dict[str, object]] = [
    {
        "source": "Simplify",
        "url": NEW_GRAD_URL,
        "sections": [
            ("Software Engineering", "Software Engineering New Grad Roles"),
            ("Data Science & AI", "Data Science, AI & Machine Learning New Grad Roles"),
        ],
    },
    {
        "source": "Simplify Off-Season",
        "url": OFF_SEASON_URL,
        "sections": [
            ("Software Engineering (Off-Season)", "Software Engineering Internship Roles"),
            ("Data Science & AI (Off-Season)", "Data Science, AI & Machine Learning Internship Roles"),
        ],
    },
]

# ---------------- helpers ----------------

def parse_age_to_days(age_str: str) -> int:
    """
    Convert age like '0d', '1d', '2d', '3mo', '12h', '45m' to days.
    Hours/minutes => treat as 0 (today).
    """
    s = (age_str or "").strip().lower()
    if s in ("0d", "0 d", "today", "0day"):
        return 0

    m = re.match(r"(\d+)\s*d", s)
    if m:
        return int(m.group(1))

    m = re.match(r"(\d+)\s*mo", s)
    if m:
        return int(m.group(1)) * 30  # coarse approx

    # hours/minutes => today
    if re.match(r"\d+\s*h", s) or re.match(r"\d+\s*m", s):
        return 0

    return 999  # unknown/old

def extract_url(cell: str) -> Optional[str]:
    """Extract URL from HTML <a href="..."> or Markdown [text](url)."""
    m = re.search(r'href="([^"]+)"', cell)
    if m:
        return m.group(1)
    m = re.search(r"\((https?://[^)]+)\)", cell)
    if m:
        return m.group(1)
    return None

def extract_job_from_row(parts: List[str]) -> Optional[Dict[str, str]]:
    """
    Parse a Markdown table row:
      | Company | Role | Location | Application | Age |
    Returns dict or None if header/invalid/closed.
    """
    if len(parts) < 6:
        return None

    company = parts[1].strip()
    role = parts[2].strip()
    location = parts[3].strip()
    app_cell = parts[4].strip()
    age_cell = parts[5].strip()

    # skip header/separator/blank
    if company.lower() in ("company", "-------", "") or role.lower() in ("role", "----", ""):
        return None

    url = extract_url(app_cell)
    is_closed = ("🔒" in app_cell) or ("closed" in app_cell.lower())

    if is_closed:
        return None

    return {
        "company": company,
        "role": role,
        "location": location,
        "application_url": url or "",
        "age": age_cell,
    }

def _fetch_lines(url: str) -> List[str]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text.splitlines()

def _iter_section_jobs(lines: List[str], section_header_text: str):
    """
    Yield jobs inside a section whose header contains `section_header_text`.
    Only yields rows from 'today' (0d/hours/minutes). Stops when hitting older rows.
    Carries forward company for '↳' continuation rows (if present).
    """
    in_section = False
    in_table = False
    last_company: Optional[str] = None

    for raw in lines:
        line = raw.strip()

        # enter section
        if line.startswith("## ") and section_header_text in line:
            in_section = True
            in_table = False
            last_company = None
            continue

        # leave section
        if in_section and line.startswith("## "):
            break

        if not in_section:
            continue

        # table header
        if line.startswith("|") and "Company" in line and "Role" in line and "Location" in line:
            in_table = True
            continue

        # separator
        if in_table and line.startswith("| ---"):
            continue

        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue

            parts = line.split("|")
            job = extract_job_from_row(parts)
            if not job:
                continue

            # carry-forward for continuation rows
            if job["company"] in ("↳", "->", "→"):
                if last_company:
                    job["company"] = last_company
            else:
                last_company = job["company"]

            # only today
            if parse_age_to_days(job["age"]) == 0:
                yield job
            else:
                # tables are newest-first; older => stop this section
                break

# ---------------- public API ----------------

def check_simplify_all() -> List[Dict[str, str]]:
    """
    Scrape both Simplify sources (New Grad + Off-Season) & categories (SE + DS/AI),
    returning only today's postings. Output items include:
      id, title, company, url, location, age, category, source
    """
    print("  [Simplify] Loading GitHub pages (New Grad + Off-Season; SE + DS/AI)...")

    all_jobs: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for src in SIMPLIFY_SOURCES:
        source_name = src["source"]  # type: ignore[assignment]
        url = src["url"]             # type: ignore[assignment]
        sections: List[Tuple[str, str]] = src["sections"]  # type: ignore[assignment]

        try:
            lines = _fetch_lines(url)  # type: ignore[arg-type]
        except requests.RequestException as e:
            print(f"  [Simplify] Failed to fetch {source_name}: {e}")
            continue

        for category_name, header_text in sections:
            section_rows = list(_iter_section_jobs(lines, header_text))
            cat_count = 0

            for job in section_rows:
                jid = (job.get("application_url") or "").strip()
                if not jid:
                    jid = "%s|%s|%s|%s" % (job["company"], job["role"], category_name, source_name)

                if jid in seen:
                    continue
                seen.add(jid)

                all_jobs.append({
                    "id": jid,
                    "title": job["role"],
                    "company": job["company"],
                    "url": job.get("application_url") or "#",
                    "location": job["location"],
                    "age": job["age"],
                    "category": category_name,
                    "source": source_name,  # type: ignore[assignment]
                })
                cat_count += 1

            print("  [Simplify] Found %d %s jobs from today (%s)" % (cat_count, category_name, source_name))

    print("  [Simplify] Total: %d jobs from today across all Simplify sources/categories" % len(all_jobs))
    return all_jobs
