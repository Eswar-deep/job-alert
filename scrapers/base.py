# scrapers/base.py
"""
Contract every scraper implements. See 02-CONTRACTS.md.

Rules enforced here so individual scrapers don't have to repeat them:
  - aiohttp only, never `requests`
  - 15s timeout, 2 retries with backoff
  - a single failing board never kills the whole scrape
Proxy rotation is the runner's job, not the scraper's.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup

from pipeline.types import Job

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def strip_html(html: Optional[str]) -> str:
    """Plain text for match/LLM input. Empty string in, empty string out."""
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


class BaseScraper:
    name: str = "base"
    timeout_seconds: int = 15
    retries: int = 2
    concurrency: int = 20

    async def scrape(self, session: aiohttp.ClientSession) -> List[Job]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Shared HTTP helper                                                  #
    # ------------------------------------------------------------------ #

    async def fetch_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        method: str = "GET",
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Any]:
        """
        Returns parsed JSON, or None on any failure after retries.
        Never raises — callers treat None as "board failed this cycle".
        """
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        merged = {"User-Agent": DEFAULT_UA}
        if headers:
            merged.update(headers)

        for attempt in range(self.retries + 1):
            try:
                async with session.request(
                    method, url, json=json_body, headers=merged, timeout=timeout
                ) as resp:
                    if resp.status == 429 or resp.status >= 500:
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status
                        )
                    if resp.status != 200:
                        return None  # 404 etc: board is gone, do not retry
                    return await resp.json(content_type=None)
            except Exception:
                if attempt == self.retries:
                    return None
                # jittered backoff: 0.5s, 1.5s
                await asyncio.sleep((2 ** attempt) * 0.5 + random.random() * 0.3)
        return None