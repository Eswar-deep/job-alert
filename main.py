# main.py
from scrapers.github_scraper import check_github_jobs
from scrapers.simplify_combined import check_simplify_all
from scrapers.notify_scraper import check_notify_jobs
from scrapers.workday_scraper import check_workday_jobs

from notify.telegram_bot import send_telegram
from storage.db import store_job_if_new

def notify_if_new(job_id, source, title, company, url):
    result = store_job_if_new(job_id, source, title, company, url)
    if result is True:
        # This job is new - send notification to Telegram
        message = f"[{source}] {title} at {company} - {url}"
        print(f"  📱 SENDING TO TELEGRAM: {message}")
        send_telegram(message)
        return True
    elif result is False:
        # This job was already sent before - skip it
        print(f"  ⏭️  ALREADY SENT: {title} at {company}")
        return False
    else:
        # Some other MongoDB error occurred
        print(f"  ❌ [MongoDB] Error while processing: {title} at {company}")
        return False

def run():
    print("[Job Alert] Starting job checks...")
    
    total_new_jobs = 0

    # Check GitHub jobs (Summer 2026 Internships and New Grad 2025)
    try:
        print("  → Checking GitHub...")
        github_jobs = check_github_jobs()
        print(f"    Found {len(github_jobs)} GitHub jobs from today")
        
        for job in github_jobs:
            if notify_if_new(job["id"], "GitHub", job["title"], job["company"], job["url"]):
                total_new_jobs += 1
    except Exception as e:
        print(f"  ❌ [GitHub] Error: {e}")

    # Check SimplifyJobs GitHub repository
    try:
        print("  → Checking Simplify (New Grad + Off-Season)...")
        simplify_jobs = check_simplify_all()
        print(f"    Found {len(simplify_jobs)} Simplify jobs from today")

        for job in simplify_jobs:
            if notify_if_new(job["id"], job["source"], job["title"], job["company"], job["url"]):
                total_new_jobs += 1
    except Exception as e:
        print(f"  ❌ [Simplify] Error: {e}")

    # Check Notify.Careers jobs
    try:
        print("  → Checking Notify.Careers...")
        notify_jobs = check_notify_jobs()
        print(f"    Found {len(notify_jobs)} Notify jobs from today")
        
        for job in notify_jobs:
            if notify_if_new(job["id"], "Notify", job["title"], job["company"], job["url"]):
                total_new_jobs += 1
    except Exception as e:
        print(f"  ❌ [Notify] Error: {e}")

    # Check Workday jobs
    try:
        print("  → Checking Workday...")
        workday_jobs = check_workday_jobs()
        print(f"    Found {len(workday_jobs)} Workday jobs from today")
        
        for job in workday_jobs:
            if notify_if_new(job["id"], "Workday", job["title"], job["company"], job["url"]):
                total_new_jobs += 1
    except Exception as e:
        print(f"  ❌ [Workday] Error: {e}")

    print(f"[Job Alert] Done. Sent {total_new_jobs} new job notifications to Telegram.\n")

if __name__ == "__main__":
    run()
