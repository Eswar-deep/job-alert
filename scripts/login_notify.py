# scripts/login_notify.py
from playwright.sync_api import sync_playwright
import os
import json

COOKIE_PATH = "storage/notify_cookies.json"
LOGIN_URL = "https://app.notify.careers/postings"

def save_cookies(context):
    cookies = context.cookies()
    os.makedirs("storage", exist_ok=True)
    with open(COOKIE_PATH, "w") as f:
        json.dump(cookies, f)
    print(f"[Notify] Saved cookies to {COOKIE_PATH}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    print("[Notify] Opening login page...")
    page.goto(LOGIN_URL)

    print("Please log in manually, then press Enter here.")
    input("...")

    save_cookies(context)
    browser.close()
