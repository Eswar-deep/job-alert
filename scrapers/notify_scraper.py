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
    
    # Define search parameters exactly matching the website
    search_params = {
        "searches": [{
            "query_by": "company_name,headquarter_location,title,description",
            "per_page": 16,
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
                
                # Process only today's jobs (compare in UTC to match server-side timestamps)
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                jobs_today = []
                
                for hit in hits:
                    job = hit["document"]
                    posted_date = datetime.fromtimestamp(
                        job["posted"], tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                    
                    if posted_date == today:
                        jobs_today.append({
                            "id": job["id"],
                            "title": job["title"],
                            "company": job["company_name"],
                            "url": job["url"],
                            "posted": posted_date
                        })
                
                print(f"  [Notify] Found {len(jobs_today)} jobs from today")
                return jobs_today
            else:
                print("  [Notify] No results found")
        else:
            print(f"  [Notify] Error: {response.status_code} {response.text[:200]}")
        
        return []

    except Exception as e:
        print(f"  [Notify] Error: {str(e)}")
        return []
