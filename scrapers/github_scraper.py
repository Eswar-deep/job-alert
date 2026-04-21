import requests
import re
from datetime import datetime

RAW_URLS = [
    "https://raw.githubusercontent.com/vanshb03/New-Grad-2026/refs/heads/dev/README.md"
]

TABLE_START_MARKER = "TABLE_START"
TABLE_END_MARKER = "TABLE_END"

def _today_md() -> str:
    """
    Repo uses dates like 'Mar 25' (no leading zero).
    On Windows, strftime doesn't support %-d, so we format then strip.
    """
    # Use local time to match what you expect when running.
    return datetime.now().strftime("%b %d").replace(" 0", " ")

def check_github_jobs():
    jobs = []
    today = _today_md()
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

                # Check if job is from today
                if url and date_posted == today:
                    jobs.append({
                        "id": url,
                        "title": title,
                        "company": company,
                        "url": url
                    })
                elif url and date_posted != today:
                    # Jobs are ordered by posting date, so stop once we hit an older job
                    break
    return jobs
