# main.py
from scrapers.github_scraper import check_github_jobs
from scrapers.simplify_scraper import check_simplify_jobs
from scrapers.notify_scraper import check_notify_jobs
from scrapers.workday_scraper import check_workday_jobs

from notify.telegram_bot import send_telegram
from storage.db import init_db, store_job_if_new

def notify_if_new(job_id, source, title, company, url):
    if store_job_if_new(job_id, source, title, company, url):
        message = f"[{source}] {title} at {company} - {url}"
        send_telegram(message)

def run():
    print("[Job Alert] Starting job checks...")
    init_db()

    # Uncomment or comment sources as needed
    try:
        print("  → Checking GitHub...")
        for job in check_github_jobs():
            notify_if_new(job["id"], "GitHub", job["title"], job["company"], job["url"])
    except Exception as e:
        print(f"  [GitHub] Error: {e}")

    # try:
    #     print("  → Checking Notify.Careers...")
    #     for job in check_notify_jobs():
    #         notify_if_new(job["id"], "Notify", job["title"], job["company"], job["url"])
    # except Exception as e:
    #     print(f"  [Simplify] Error: {e}")

    try:
        print("  → Checking Notify.Careers...")
        for job in check_notify_jobs():
            notify_if_new(job["id"], "Notify", job["title"], job["company"], job["url"])
    except Exception as e:
        print(f"  [Notify] Error: {e}")

    try:
        print("  → Checking Workday...")
        for job in check_workday_jobs():
            notify_if_new(job["id"], "Workday", job["title"], job["company"], job["url"])
    except Exception as e:
        print(f"  [Workday] Error: {e}")


    print("[Job Alert] Done.\n")

if __name__ == "__main__":
    run()
