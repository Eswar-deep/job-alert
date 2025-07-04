import json
import os
from playwright.sync_api import sync_playwright
from datetime import datetime

COOKIE_PATH = "storage/notify_cookies.json"
NOTIFY_URL = "https://app.notify.careers/postings"

def check_notify_jobs():
    if not os.path.exists(COOKIE_PATH):
        print("[NotifyScraper] No cookies found. Run login_notify.py first.")
        return []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        with open(COOKIE_PATH, "r") as f:
            cookies = json.load(f)
            for cookie in cookies:
                cookie["domain"] = "app.notify.careers"
            context.add_cookies(cookies)

        page = context.new_page()
        print("[NotifyScraper] Loading job postings...")
        page.goto(NOTIFY_URL, timeout=30000)
        page.wait_for_timeout(5000)

        try:
            page.locator("h4:has-text('Fields') ~ button").click()
            page.wait_for_timeout(500)
            labels = page.locator("label").all_inner_texts()
            page.locator("div:has(label:has-text('AI & Machine Learning')) > button[role='checkbox']").click()
            page.locator("div:has(label:has-text('Software Engineering')) > button[role='checkbox']").click()
        except Exception as e:
            print(f"  [Notify] Warning: Could not set 'Fields' filter: {e}")

        try:
            page.locator("h4:has-text('Experience Levels') ~ button").click()
            page.wait_for_timeout(500)
            page.locator("div:has(label:has-text('Internship')) > button[role='checkbox']").click()
            page.locator("div:has(label:has-text('Entry Level/New Grad')) > button[role='checkbox']").click()
        except Exception as e:
            print(f"  [Notify] Warning: Could not set 'Experience Levels' filter: {e}")

        page.wait_for_timeout(3000)

        for _ in range(10):
            job_buttons = page.query_selector_all("a[target='_blank'] > button")
            if job_buttons:
                break
            page.wait_for_timeout(1000)
        else:
            print("  [Notify] Error: Job content not found.")
            browser.close()
            return []

        jobs = []
        job_cards = page.query_selector_all("div:has(a[target='_blank'])")
        now = datetime.utcnow()
        
        # More flexible date formats that Notify might use
        today_formats = [
            f"{now.month}/{now.day}/{now.year}",      # M/D/YYYY
            f"{now.month:02d}/{now.day:02d}/{now.year}", # MM/DD/YYYY
            f"{now.day}/{now.month}/{now.year}",      # D/M/YYYY
            f"{now.day:02d}/{now.month:02d}/{now.year}", # DD/MM/YYYY
            "Today",
            "Just posted",
            "Posted today"
        ]
        
        print(f"  [Notify] Looking for jobs with dates: {today_formats}")
        print(f"  [Notify] Found {len(job_cards)} job cards to check")
        
        jobs_found = 0
        jobs_today = 0
        
        for i, card in enumerate(job_cards):
            try:
                anchor = card.query_selector("a[target='_blank']")
                url = anchor.get_attribute("href")
                title = anchor.inner_text().strip()
                company_elem = card.query_selector("a[href^='https://'] > button")
                company = company_elem.inner_text().strip() if company_elem else "Notify"
                
                # Look for date in multiple possible selectors
                date_elem = None
                date_selectors = [
                    "span.text-muted-foreground.font-greycliff.font-medium.opacity-50",
                    "span.text-muted-foreground",
                    "span.opacity-50",
                    "span:has-text('/')",  # Any span containing a slash (date separator)
                ]
                
                for selector in date_selectors:
                    for span in card.query_selector_all(selector):
                        date_text = span.inner_text().strip()
                        if date_text and ("/" in date_text or date_text.lower() in ["today", "just posted", "posted today"]):
                            date_elem = date_text
                            break
                    if date_elem:
                        break
                
                jobs_found += 1
                
                if not date_elem:
                    print(f"    [Notify] Job {i+1}: No date found for '{title}' at {company}")
                    continue
                
                print(f"    [Notify] Job {i+1}: '{title}' at {company} - Date: '{date_elem}'")
                
                # Check if it's from today (case insensitive)
                is_today = False
                for today_format in today_formats:
                    if date_elem.lower() == today_format.lower():
                        is_today = True
                        break
                
                if is_today:
                    jobs_today += 1
                    jobs.append({
                        "id": url,
                        "title": title,
                        "company": company,
                        "url": url
                    })
                    print(f"      ✓ Added to today's jobs!")
                else:
                    print(f"      ✗ Not from today, skipping")
                    # Don't break here - continue checking other jobs
                    
            except Exception as e:
                print(f"  [Notify] Skipped a card due to parsing error: {e}")

        print(f"  [Notify] Summary: Checked {jobs_found} jobs, found {jobs_today} from today")
        browser.close()
        return jobs
