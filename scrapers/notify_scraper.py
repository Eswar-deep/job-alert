import json
import os
from playwright.sync_api import sync_playwright

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
        job_links = page.query_selector_all("a[target='_blank']")

        for anchor in job_links:
            url = anchor.get_attribute("href")
            title = anchor.inner_text().strip()
            job_id = url
            company = "Notify"

            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "url": url
            })

        browser.close()
        return jobs
