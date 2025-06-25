# main.py
from scrapers.github_scraper import check_github_jobs
from scrapers.simplify_scraper import check_simplify_jobs
from scrapers.notify_scraper import check_notify_jobs
from scrapers.handshake_scraper import HandshakeScraper

from notify.telegram_bot import send_telegram
from storage.db import init_db, store_job_if_new

def notify_if_new(job_id, source, title, company, url):
    if store_job_if_new(job_id, source, title, company, url):
        message = f"[{source}] {title} at {company} - {url}"
        send_telegram(message)

def run():
    print("[Job Alert] Starting job checks...")
    init_db()

    try:
        print("  → Checking GitHub...")
        for job in check_github_jobs():
            notify_if_new(job["id"], "GitHub", job["title"], job["company"], job["url"])
    except Exception as e:
        print(f"  [GitHub] Error: {e}")

    # Uncomment these as they become stable
    # try:
    #     print("  → Checking Simplify.jobs...")
    #     for job in check_simplify_jobs():
    #         notify_if_new(job["id"], "Simplify", job["title"], job["company"], job["url"])
    # except Exception as e:
    #     print(f"  [Simplify] Error: {e}")

    try:
        print("  → Checking Notify.Careers...")
        for job in check_notify_jobs():
            notify_if_new(job["id"], "Notify", job["title"], job["company"], job["url"])
    except Exception as e:
        print(f"  [Notify] Error: {e}")

    # try:
    #     print("  → Checking Handshake...")
    #     # Replace with your actual credentials or load from env/config
    #     email = "your_email@example.com"
    #     password = "your_password"
    #     handshake_scraper = HandshakeScraper(email, password)
    #     for job in handshake_scraper.run():
    #         notify_if_new(job.get("id", ""), "Handshake", job.get("title", ""), job.get("company", ""), job.get("url", ""))
    # except Exception as e:
    #     print(f"  [Handshake] Error: {e}")

    print("[Job Alert] Done.\n")
if __name__ == "__main__":
    run()
