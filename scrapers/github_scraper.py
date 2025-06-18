import requests
import re

RAW_URL = "https://raw.githubusercontent.com/vanshb03/Summer2026-Internships/dev/OFFSEASON_README.md"

def check_github_jobs():
    try:
        response = requests.get(RAW_URL, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[GitHubScraper] Failed to fetch README: {e}")
        return []

    lines = response.text.splitlines()
    jobs = []

    in_table = False

    for line in lines:
        line = line.strip()
        if line.startswith("|") and "Company" in line and "Role" in line:
            in_table = True  # found header
            continue
        if in_table and line.startswith("| ---"):
            continue  # skip separator
        if in_table and line.startswith("|"):
            parts = line.split("|")
            if len(parts) < 5:
                continue
            company = parts[1].strip()
            title = parts[2].strip()
            link_html = parts[4].strip()

            # Extract actual href
            match = re.search(r'href="([^"]+)"', link_html)
            url = match.group(1) if match else None

            if url:
                jobs.append({
                    "id": url,
                    "title": title,
                    "company": company,
                    "url": url
                })

    return jobs
