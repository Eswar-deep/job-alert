# notify/ntfy.py
"""
Push notifications via ntfy (https://ntfy.sh or a self-hosted instance).

Set NTFY_TOPIC to enable; pipeline/runner.py no-ops without it. NTFY_SERVER
defaults to the public ntfy.sh instance.
"""
from __future__ import annotations

import os
from typing import List

import aiohttp
from dotenv import load_dotenv

from pipeline.types import ScoredJob

load_dotenv()

NTFY_TOPIC = os.getenv("NTFY_TOPIC")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


class NtfyNotifier:
    async def send(self, jobs: List[ScoredJob]) -> None:
        if not jobs or not NTFY_TOPIC:
            return
        url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"

        async with aiohttp.ClientSession() as session:
            for scored in jobs:
                job = scored["job"]
                body = f"{job['title']} @ {job['company']}\n{job['url']}"
                if scored.get("reason"):
                    body += f"\n\n{scored['reason']}"
                headers = {
                    "Title": "New job match",
                    "Click": job["url"],
                    "Tags": "briefcase",
                }
                try:
                    async with session.post(
                        url, data=body.encode("utf-8"), headers=headers, timeout=REQUEST_TIMEOUT
                    ) as resp:
                        if resp.status >= 300:
                            print(f"[ntfy] push failed ({resp.status}) for {job['id']}")
                except Exception as e:
                    print(f"[ntfy] push failed for {job['id']}: {type(e).__name__}: {e}")
