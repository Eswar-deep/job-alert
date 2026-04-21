import os
import requests
import re
from datetime import datetime, date
from typing import Optional

RAW_URLS = [
    "https://raw.githubusercontent.com/vanshb03/New-Grad-2026/refs/heads/dev/README.md"
]

TABLE_START_MARKER = "TABLE_START"
TABLE_END_MARKER = "TABLE_END"

# LOOKBACK_DAYS = 1 means "today only" (0 days old).
# LOOKBACK_DAYS = 7 means "today + 6 prior days" (up to 6 days old).
# Condition used below: (today - posted_date).days < LOOKBACK_DAYS
LOOKBACK_DAYS = max(1, int(os.getenv("LOOKBACK_DAYS", "1")))


def _parse_md_date(date_str: str, today: date) -> Optional[date]:
    """
    Parse a repo-style date like 'Mar 25' (no year) into a date object.
    Assumes the current year; if that date is in the future relative to today,
    assume it was posted in the previous year.
    """
    s = (date_str or "").strip().replace("  ", " ")
    if not s:
        return None
    try:
        parsed = datetime.strptime(s, "%b %d").date().replace(year=today.year)
    except ValueError:
        return None
    if parsed > today:
        parsed = parsed.replace(year=today.year - 1)
    return parsed


def check_github_jobs():
    jobs = []
    today = datetime.now().date()
    for RAW_URL in RAW_URLS:
        try:
            response = requests.get(RAW_URL, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[GitHubScraper] Failed to fetch README: {e}")
            continue

        lines = response.text.splitlines()
        in_table_region = False
        in_table = False

        for line in lines:
            line = line.strip()

            if TABLE_START_MARKER in line:
                in_table_region = True
                continue

            if TABLE_END_MARKER in line:
                break

            if not in_table_region:
                continue

            if line.startswith("|") and "Company" in line and "Role" in line:
                in_table = True
                continue
            if in_table and line.startswith("| ---"):
                continue
            if in_table and line.startswith("|"):
                parts = line.split("|")
                if len(parts) < 6:
                    continue
                company = parts[1].strip()
                title = parts[2].strip()
                link_html = parts[4].strip()
                date_posted = parts[5].strip()

                match = re.search(r'href="([^"]+)"', link_html)
                url = match.group(1) if match else None

                if not url:
                    # Rows without a link (e.g., closed 🔒 rows) — skip without
                    # breaking, since they can appear between newer valid rows.
                    continue

                parsed_date = _parse_md_date(date_posted, today)
                if parsed_date is None:
                    continue

                days_old = (today - parsed_date).days
                if days_old < 0:
                    # Future date (shouldn't happen) — skip.
                    continue
                if days_old < LOOKBACK_DAYS:
                    jobs.append({
                        "id": url,
                        "title": title,
                        "company": company,
                        "url": url
                    })
                else:
                    # Table is ordered newest-first; once we see an entry
                    # older than the lookback window, nothing further will qualify.
                    break
    return jobs
