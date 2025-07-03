from playwright.sync_api import sync_playwright
import time
from datetime import datetime

class WorkdayScraper:
    def __init__(self, filtered_url: str, company: str = "Workday"):
        self.filtered_url = filtered_url
        self.company = company

    def scrape_jobs(self):
        jobs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(self.filtered_url, wait_until="networkidle")
                page.wait_for_selector('[data-automation-id="jobTitle"]', timeout=10000)
                job_links = page.query_selector_all('[data-automation-id="jobTitle"]')
                if not job_links:
                    print("No job links found. Check if URL is a job listing page, not a detail page.")
                    return jobs
                seen = set()
                for i, link in enumerate(job_links):
                    try:
                        job_url = link.get_attribute("href")
                        if not job_url or job_url in seen:
                            continue
                        seen.add(job_url)
                        if job_url.startswith('/'):
                            base_url = "https://" + page.url.split('/')[2]
                            job_url = base_url + job_url
                        
                        # Find the parent li element to get the posting date
                        parent_li = link.evaluate_handle('element => element.closest("li")')
                        if parent_li:
                            # Look for the posted date within this job listing
                            posted_on_elem = parent_li.query_selector('[data-automation-id="postedOn"] dd')
                            if posted_on_elem:
                                posted_on_text = posted_on_elem.text_content().strip()
                                # Only process jobs posted today
                                if posted_on_text == "Posted Today":
                                    job_data = self._extract_job_from_listing(link, job_url)
                                    job_data.update(self._extract_job_from_detail(browser, job_url))
                                    jobs.append(job_data)
                                else:
                                    # Jobs are ordered by posting date, so stop once we hit an older job
                                    break
                            else:
                                # If we can't find the date, skip this job
                                continue
                    except Exception as e:
                        print(f"Error processing job {i+1}: {e}")
                        continue
            except Exception as e:
                print(f"Error loading page: {e}")
            finally:
                browser.close()
        return jobs

    def _extract_job_from_listing(self, link_element, job_url):
        try:
            title = link_element.text_content().strip()
            if not title:
                title = link_element.get_attribute("title") or "Unknown Title"
            job_id = job_url.split("/")[-1].split("?")[0]
            return {
                "id": job_id,
                "title": title,
                "company": self.company,
                "url": job_url
            }
        except:
            return {
                "id": job_url.split("/")[-1].split("?")[0],
                "title": "Unknown Title",
                "company": self.company,
                "url": job_url
            }

    def _extract_job_from_detail(self, browser, job_url):
        try:
            context = browser.new_context()
            detail_page = context.new_page()
            detail_page.goto(job_url, wait_until="networkidle")
            detail_page.wait_for_timeout(1000)
            details = {}
            location_selectors = [
                '[data-automation-id="job-location"]',
                '[data-automation-id="location"]',
                '.job-location',
                '[data-automation-id="jobLocation"]'
            ]
            for selector in location_selectors:
                location_elem = detail_page.query_selector(selector)
                if location_elem:
                    details["location"] = location_elem.text_content().strip()
                    break
            type_selectors = [
                '[data-automation-id="job-type"]',
                '[data-automation-id="level"]',
                '.job-type',
                '[data-automation-id="jobLevel"]'
            ]
            for selector in type_selectors:
                type_elem = detail_page.query_selector(selector)
                if type_elem:
                    details["job_type"] = type_elem.text_content().strip()
                    break
            desc_selectors = [
                '[data-automation-id="job-description"]',
                '[data-automation-id="description"]',
                '.job-description',
                '[data-automation-id="jobDescription"]'
            ]
            for selector in desc_selectors:
                desc_elem = detail_page.query_selector(selector)
                if desc_elem:
                    details["description"] = desc_elem.text_content().strip()[:500] + "..."
                    break
            detail_page.close()
            context.close()
            return details
        except Exception as e:
            print(f"Error extracting details from {job_url}: {e}")
            return {}

def check_workday_jobs():
    WORKDAY_LISTING_URL = "https://workday.wd5.myworkdayjobs.com/en-US/Workday/jobs?Location_Country=bc33aa3152ec42d4995f4791a106ed09&jobFamilyGroup=8c5ce7a1cffb43e0a819c249a49fcb00&jobFamilyGroup=a88cba90a00841e0b750341c541b9d56"
    scraper = WorkdayScraper(WORKDAY_LISTING_URL, company="Workday")
    return scraper.scrape_jobs() 