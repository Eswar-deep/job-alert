import json
import os
from datetime import datetime
import requests
import re  # Missing import for regular expressions

COOKIE_PATH = "storage/notify_cookies.json"
NOTIFY_SEARCH_URL = "https://search.notify.careers/multi_search"

def check_notify_jobs():
    print("[NotifyScraper] Fetching jobs from API...")
    
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
            "filter_by": "fields:=[`Software Engineering`, `AI & Machine Learning`] && experience_levels:=[`Internship`, `Entry Level/New Grad`]",

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
            "https://search.notify.careers/multi_search",
            params={"x-typesense-api-key": "EaynlHtIjnOzJ7CaJh4JG34Ot8vRCW05"},  # API key in URL params
            headers=headers,
            json=search_params  # Using json parameter to automatically handle JSON encoding
        )
        
        print(f"  [Notify] Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if "results" in data and len(data["results"]) > 0:
                hits = data["results"][0].get("hits", [])
                print(f"  [Notify] Found {len(hits)} jobs")
                
                # Process only today's jobs
                today = datetime.utcnow().strftime("%Y-%m-%d")
                jobs_today = []
                
                for hit in hits:
                    job = hit["document"]
                    posted_date = datetime.fromtimestamp(job["posted"]).strftime("%Y-%m-%d")
                    
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

check_notify_jobs()