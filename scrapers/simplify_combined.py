# scrapers/simplify_combined.py
import os
from typing import Optional, List, Dict, Set
import re
import requests

NEW_GRAD_URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"

SOURCE_NAME = "Simplify"
TABLE_START_MARKER = "TABLE_START"
TABLE_END_MARKER = "TABLE_END"

# LOOKBACK_DAYS = 1 means "today only" (age 0d).
# LOOKBACK_DAYS = 7 means "today + 6 prior days" (age up to 6d).
# Condition used below: parse_age_to_days(...) < LOOKBACK_DAYS
LOOKBACK_DAYS = max(1, int(os.getenv("LOOKBACK_DAYS", "1")))

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
    """Extract URL from HTML <a href="..."> (first link)."""
    m = re.search(r'href="([^"]+)"', cell)
    if m:
        return m.group(1)
    return None

_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(s: str) -> str:
    # Keep this conservative: strip tags and normalize whitespace.
    s = (s or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    s = _TAG_RE.sub("", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return " ".join(s.split())


def _fetch_text(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _extract_table_region(text: str) -> str:
    # Prefer markers (repo includes them). Fall back to full text.
    if TABLE_START_MARKER not in text or TABLE_END_MARKER not in text:
        return text

    start = text.find(TABLE_START_MARKER)
    end = text.find(TABLE_END_MARKER, start)
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start:end]


def _infer_category_from_header(line: str) -> Optional[str]:
    s = (line or "").lower()
    if not s.startswith("##"):
        return None
    if "software engineering" in s:
        return "Software Engineering"
    if "data science" in s or re.search(r"\bai\b", s) or "machine learning" in s:
        return "Data Science & AI"
    if "product management" in s:
        return "Product Management"
    if "quantitative finance" in s:
        return "Quantitative Finance"
    if "hardware engineering" in s:
        return "Hardware Engineering"
    if "other" in s:
        return "Other"
    return None


def _parse_html_tr(tr_html: str) -> Optional[Dict[str, str]]:
    # Expect <td>Company</td><td>Role</td><td>Location</td><td>Application</td><td>Age</td>
    tds = re.findall(r"<td\b[^>]*>(.*?)</td>", tr_html, flags=re.IGNORECASE | re.DOTALL)
    if len(tds) < 5:
        return None

    company_cell, role_cell, location_cell, app_cell, age_cell = tds[:5]

    company = _html_to_text(company_cell)
    role = _html_to_text(role_cell)
    location = _html_to_text(location_cell)
    age = _html_to_text(age_cell)

    # skip header-ish rows (just in case)
    if not company or company.lower() == "company" or not role or role.lower() == "role":
        return None

    # closed roles often show 🔒 instead of a link in "Application"
    if "🔒" in app_cell or "closed" in app_cell.lower():
        return None

    url = extract_url(app_cell) or ""

    return {
        "company": company,
        "role": role,
        "location": location,
        "application_url": url,
        "age": age,
    }

# ---------------- public API ----------------

def check_simplify_all() -> List[Dict[str, str]]:
    """
    Scrape Simplify New Grad Positions (single README URL),
    returning only today's postings. Output items include:
      id, title, company, url, location, age, category, source
    """
    print("  [Simplify] Loading GitHub page (New Grad Positions)...")

    all_jobs: List[Dict[str, str]] = []
    seen: Set[str] = set()

    try:
        text = _fetch_text(NEW_GRAD_URL)
    except requests.RequestException as e:
        print(f"  [Simplify] Failed to fetch {SOURCE_NAME}: {e}")
        return []

    region = _extract_table_region(text)

    # Exclude "Inactive roles" tables (they start at the first <details> in the active region)
    details_idx = region.lower().find("<details")
    if details_idx != -1:
        region = region[:details_idx]

    current_category: str = "Unknown"
    last_company: Optional[str] = None
    counts_by_category: Dict[str, int] = {}

    # We'll iterate line-by-line to keep category context, but parse <tr> blocks across lines.
    buf: List[str] = []
    in_tr = False

    for raw_line in region.splitlines():
        line = raw_line.strip()

        cat = _infer_category_from_header(line)
        if cat:
            current_category = cat
            last_company = None
            continue

        if "<tr" in line.lower():
            in_tr = True
            buf = [line]
            continue

        if in_tr:
            buf.append(line)
            if "</tr>" in line.lower():
                in_tr = False
                tr_html = "\n".join(buf)
                buf = []

                job = _parse_html_tr(tr_html)
                if not job:
                    continue

                # carry-forward for continuation rows
                if job["company"] in ("↳", "->", "→"):
                    if last_company:
                        job["company"] = last_company
                else:
                    last_company = job["company"]

                # keep jobs posted within the lookback window
                if parse_age_to_days(job["age"]) >= LOOKBACK_DAYS:
                    continue

                jid = (job.get("application_url") or "").strip()
                if not jid:
                    jid = "%s|%s|%s|%s" % (job["company"], job["role"], current_category, SOURCE_NAME)

                if jid in seen:
                    continue
                seen.add(jid)

                all_jobs.append(
                    {
                        "id": jid,
                        "title": job["role"],
                        "company": job["company"],
                        "url": job.get("application_url") or "#",
                        "location": job["location"],
                        "age": job["age"],
                        "category": current_category,
                        "source": SOURCE_NAME,
                    }
                )
                counts_by_category[current_category] = counts_by_category.get(current_category, 0) + 1

    window_label = "today" if LOOKBACK_DAYS == 1 else f"last {LOOKBACK_DAYS} days"
    for cat, n in sorted(counts_by_category.items(), key=lambda kv: kv[0]):
        print("  [Simplify] Found %d %s jobs from %s (%s)" % (n, cat, window_label, SOURCE_NAME))

    print("  [Simplify] Total: %d jobs from %s across all categories" % (len(all_jobs), window_label))
    return all_jobs
