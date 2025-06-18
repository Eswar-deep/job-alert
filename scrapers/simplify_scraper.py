from playwright.sync_api import sync_playwright

SIMPLIFY_URL = "https://simplify.jobs/jobs?state=United%20States&country=United%20States&experience=Internship%3BEntry%20Level%2FNew%20Grad&category=Applied%20Machine%20Learning%3BConversational%20AI%20%26%20Chatbots%3BRobotics%20%26%20Autonomous%20Systems%3BSpeech%20Recognition%3BDeep%20Learning%3BNatural%20Language%20Processing%20(NLP)%3BComputer%20Vision%3BAI%20Research%3BData%20Management%3BData%20Science%3BAI%20%26%20Machine%20Learning%3BAndroid%20Development%3BBackend%20Engineering%3BFinTech%20Engineering%3BFrontend%20Engineering%3BFull-Stack%20Engineering%3BGame%20Engineering%3BIOS%20Development%3BIT%20%26%20Support%3BMobile%20Engineering%3BWeb%20Development%3BData%20Analysis%3BData%20Engineering%3BDeveloper%20Relations%3BSoftware%20QA%20%26%20Testing%3BSoftware%20Engineering%3BData%20%26%20Analytics"

def check_simplify_jobs():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        print("  [Simplify] Loading page...")
        page.goto(SIMPLIFY_URL, timeout=30000)

        # Wait for job cards to load
        try:
            page.wait_for_selector("div.job-card", timeout=15000)
        except:
            print("  [Simplify] Error: Job cards not found.")
            browser.close()
            return []

        jobs = []
        job_cards = page.query_selector_all("div.job-card")

        for card in job_cards:
            try:
                title = card.query_selector("h2").inner_text().strip()
                company = card.query_selector("p.text-sm.text-gray-500").inner_text().strip()
                link = card.query_selector("a").get_attribute("href")
                job_url = f"https://simplify.jobs{link}" if link.startswith("/") else link

                jobs.append({
                    "id": job_url,
                    "title": title,
                    "company": company,
                    "url": job_url
                })
            except Exception as e:
                print(f"  [Simplify] Skipped a card due to parsing error: {e}")

        browser.close()
        return jobs
