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
        page.wait_for_timeout(5000)  # Allow JS to render content

        # --- Apply Filters ---
        # Open the 'Fields' dropdown and select 'Software Engineering'
        try:
            page.locator("h4:has-text('Fields') ~ button").click()
            page.wait_for_timeout(500)  # Wait for options to appear
            labels = page.locator("label").all_inner_texts()
            # Click the checkbox buttons for the desired fields
            page.locator("div:has(label:has-text('AI & Machine Learning')) > button[role='checkbox']").click()
            page.locator("div:has(label:has-text('Software Engineering')) > button[role='checkbox']").click()
        except Exception as e:
            print(f"  [Notify] Warning: Could not set 'Fields' filter: {e}")

        # Open the 'Experience Levels' dropdown and select 'Internship' and 'Entry Level/New Grad'
        try:
            page.locator("h4:has-text('Experience Levels') ~ button").click()
            page.wait_for_timeout(500)  # Wait for options to appear
            # Click the checkbox buttons for the desired experience levels
            page.locator("div:has(label:has-text('Internship')) > button[role='checkbox']").click()
            page.locator("div:has(label:has-text('Entry Level/New Grad')) > button[role='checkbox']").click()
        except Exception as e:
            print(f"  [Notify] Warning: Could not set 'Experience Levels' filter: {e}")

        page.wait_for_timeout(3000)  # Wait for jobs to update
        # --- End Apply Filters ---

        # Wait for job listings to appear
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
        today = datetime.utcnow().strftime('%-m/%-d/%Y')  # e.g., '7/2/2025'
        today_alt = datetime.utcnow().strftime('%#m/%#d/%Y')  # Windows compatibility
        for card in job_cards:
            try:
                anchor = card.query_selector("a[target='_blank']")
                url = anchor.get_attribute("href")
                title = anchor.inner_text().strip()
                company_elem = card.query_selector("a[href^='https://'] > button")
                company = company_elem.inner_text().strip() if company_elem else "Notify"
                # Find all muted spans, pick the one that matches date format
                date_elem = None
                for span in card.query_selector_all("span.text-muted-foreground.font-greycliff.font-medium.opacity-50"):
                    date_text = span.inner_text().strip()
                    if "/" in date_text and len(date_text.split("/")) == 3:
                        date_elem = date_text
                        break
                if not date_elem:
                    continue
                # Check if job is from today
                if date_elem == today or date_elem == today_alt:
                    jobs.append({
                        "id": url,
                        "title": title,
                        "company": company,
                        "url": url
                    })
                else:
                    # Jobs are ordered by posting date, so stop once we hit an older job
                    break
            except Exception as e:
                print(f"  [Notify] Skipped a card due to parsing error: {e}")

        browser.close()
        return jobs
