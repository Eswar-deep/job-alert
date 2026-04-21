import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests

NOTIFY_SEARCH_URL = "https://search.notify.careers/multi_search"
NOTIFY_TYPESENSE_KEY = os.getenv(
    "NOTIFY_TYPESENSE_KEY", "EaynlHtIjnOzJ7CaJh4JG34Ot8vRCW05"
)
NOTIFY_REQUEST_TIMEOUT = 15

# LOOKBACK_DAYS = 1 means "today only" (0 days old).
# LOOKBACK_DAYS = 7 means "today + 6 prior days" (up to 6 days old).
# Condition used below: (today_utc - posted_date_utc).days < LOOKBACK_DAYS
LOOKBACK_DAYS = max(1, int(os.getenv("LOOKBACK_DAYS", "1")))

FILTERS_PATH = Path("notify_filters.json")


def _escape_typesense_value(v: str) -> str:
    # We wrap facet values in backticks; ensure we don't break the syntax.
    return (v or "").replace("`", "").strip()


def _load_notify_filters() -> dict:
    """
    Loads filters from `notify_filters.json` in the repo root.
    Expected shape:
      { "fields": [...], "experience_levels": [...] }
    Returns empty dict if missing/invalid.
    """
    try:
        if not FILTERS_PATH.exists():
            return {}
        with FILTERS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _build_filter_by(filters: dict) -> str:
    fields = [_escape_typesense_value(x) for x in (filters.get("fields") or []) if str(x).strip()]
    exp = [_escape_typesense_value(x) for x in (filters.get("experience_levels") or []) if str(x).strip()]

    clauses = []
    if fields:
        fields_list = ", ".join(f"`{x}`" for x in fields)
        clauses.append(f"fields:=[{fields_list}]")
    if exp:
        exp_list = ", ".join(f"`{x}`" for x in exp)
        clauses.append(f"experience_levels:=[{exp_list}]")

    return " && ".join(clauses) if clauses else ""


def check_notify_jobs():
    print("[NotifyScraper] Fetching jobs from API...")
    filters = _load_notify_filters()
    filter_by = _build_filter_by(filters)
    
    # Scale page size with the lookback window (default 20/day, capped at 250).
    per_page = min(250, max(16, LOOKBACK_DAYS * 20))

    # Define search parameters exactly matching the website
    search_params = {
        "searches": [{
            "query_by": "company_name,headquarter_location,title,description",
            "per_page": per_page,
            "sort_by": "posted:desc",
            "highlight_full_fields": "company_name,headquarter_location,title,description",
            "collection": "postings",
            "q": "*",
            "facet_by": "countries,employee_count,experience_levels,fields,industries,ipo_status,last_funding_type,locations,workplace_type",
            **({"filter_by": filter_by} if filter_by else {}),

            "max_facet_values": 40,
            "page": 1
        }]
    }
    
    # Headers matching the actual request
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "text/plain",  # Note: Different from previous
        "origin": "https://app.notify.careers",
        "referer": "https://app.notify.careers/",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }

    try:
        print("  [Notify] Making API request...")
        response = requests.post(
            NOTIFY_SEARCH_URL,
            params={"x-typesense-api-key": NOTIFY_TYPESENSE_KEY},
            headers=headers,
            json=search_params,
            timeout=NOTIFY_REQUEST_TIMEOUT,
        )
        
        print(f"  [Notify] Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if "results" in data and len(data["results"]) > 0:
                hits = data["results"][0].get("hits", [])
                print(f"  [Notify] Found {len(hits)} jobs")
                
                # Keep jobs posted within LOOKBACK_DAYS (compare in UTC to match server-side timestamps)
                today_utc = datetime.now(timezone.utc).date()
                jobs_in_window = []

                for hit in hits:
                    job = hit["document"]
                    posted_dt = datetime.fromtimestamp(
                        job["posted"], tz=timezone.utc
                    )
                    days_old = (today_utc - posted_dt.date()).days
                    if days_old < 0 or days_old >= LOOKBACK_DAYS:
                        continue

                    jobs_in_window.append({
                        "id": job["id"],
                        "title": job["title"],
                        "company": job["company_name"],
                        "url": job["url"],
                        "posted": posted_dt.strftime("%Y-%m-%d"),
                    })

                window_label = "today" if LOOKBACK_DAYS == 1 else f"last {LOOKBACK_DAYS} days"
                print(f"  [Notify] Found {len(jobs_in_window)} jobs from {window_label}")
                return jobs_in_window
            else:
                print("  [Notify] No results found")
        else:
            print(f"  [Notify] Error: {response.status_code} {response.text[:200]}")
        
        return []

    except Exception as e:
        print(f"  [Notify] Error: {str(e)}")
        return []
