import requests
import re

RAW_URLS = [
    "https://raw.githubusercontent.com/vanshb03/Summer2026-Internships/dev/OFFSEASON_README.md",
    "https://raw.githubusercontent.com/vanshb03/New-Grad-2025/dev/README.md"
]
def check_github_jobs():
    jobs = []
    for RAW_URL in RAW_URLS:
        try:
            response = requests.get(RAW_URL, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[GitHubScraper] Failed to fetch README: {e}")
            continue

        lines = response.text.splitlines()
        in_table = False

        for line in lines:
            line = line.strip()
            if line.startswith("|") and "Company" in line and "Role" in line:
                in_table = True
                continue
            if in_table and line.startswith("| ---"):
                continue
            if in_table and line.startswith("|"):
                parts = line.split("|")
                if len(parts) < 5:
                    continue
                company = parts[1].strip()
                title = parts[2].strip()
                link_html = parts[4].strip()

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
