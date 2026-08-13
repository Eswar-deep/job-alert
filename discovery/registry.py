# discovery/registry.py
"""
Mongo-backed registry of ATS company boards.

Documents live in collection `ats_companies`:
{
  "_id": "greenhouse:stripe",
  "platform": "greenhouse",
  "slug": "stripe",
  "extra": {"region": "us"},          # workday: {"site": ..., "wd": "wd5"}
  "active": true,
  "first_seen": ISODate,
  "last_validated": ISODate,
  "consecutive_failures": 0,
  "job_count": 142                     # last observed board size, for monitoring
}

Writes are low-volume (discovery, not the hot path), so sync pymongo is fine.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection

from discovery.slug_extractor import ATSCandidate

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "job_alert")
REGISTRY_COLLECTION = os.getenv("MONGO_ATS_COLLECTION", "ats_companies")

# Retire a board after this many consecutive failed validations/polls.
MAX_CONSECUTIVE_FAILURES = 5

_collection: Optional[Collection] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_collection() -> Optional[Collection]:
    global _collection
    if _collection is not None:
        return _collection
    if not MONGO_URI:
        print("[Registry] MONGO_URI not set; registry disabled.")
        return None
    try:
        client = MongoClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
        )
        _collection = client[DB_NAME][REGISTRY_COLLECTION]
        return _collection
    except Exception as e:
        print(f"[Registry] Mongo connection failed: {e}")
        return None


def upsert_candidates(candidates: list[ATSCandidate], validated: bool = False) -> int:
    """
    Insert new boards / refresh existing ones. Returns number of *new* boards added.
    `validated=True` marks them active and stamps last_validated.
    """
    coll = get_collection()
    if coll is None or not candidates:
        return 0

    now = _now()
    ops: list[UpdateOne] = []
    for c in candidates:
        set_on_insert = {
            "platform": c.platform,
            "slug": c.slug,
            "extra": c.extra,
            "first_seen": now,
            "consecutive_failures": 0,
            "job_count": 0,
        }
        update: dict = {"$setOnInsert": set_on_insert}
        if validated:
            update["$set"] = {"active": True, "last_validated": now, "consecutive_failures": 0}
        else:
            # New, unvalidated boards start inactive until a probe succeeds.
            set_on_insert["active"] = False
            set_on_insert["last_validated"] = None
        ops.append(UpdateOne({"_id": c.key}, update, upsert=True))

    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count


def mark_success(key: str, job_count: int) -> None:
    coll = get_collection()
    if coll is None:
        return
    coll.update_one(
        {"_id": key},
        {"$set": {
            "active": True,
            "last_validated": _now(),
            "consecutive_failures": 0,
            "job_count": job_count,
        }},
    )


def mark_failure(key: str) -> None:
    """Increment failure counter; retire the board once it exceeds the threshold."""
    coll = get_collection()
    if coll is None:
        return
    doc = coll.find_one_and_update(
        {"_id": key},
        {"$inc": {"consecutive_failures": 1}},
        return_document=True,
    )
    if doc and doc.get("consecutive_failures", 0) >= MAX_CONSECUTIVE_FAILURES:
        coll.update_one({"_id": key}, {"$set": {"active": False}})
        print(f"[Registry] Retired board {key} after {MAX_CONSECUTIVE_FAILURES} consecutive failures.")


def get_active_boards(platform: Optional[str] = None) -> list[dict]:
    """All boards the pollers should hit. Optionally filter by platform."""
    coll = get_collection()
    if coll is None:
        return []
    query: dict = {"active": True}
    if platform:
        query["platform"] = platform
    return list(coll.find(query))


def get_unvalidated(limit: int = 500) -> list[dict]:
    """Boards harvested but never successfully probed — bootstrap/validator input."""
    coll = get_collection()
    if coll is None:
        return []
    return list(coll.find({"active": False, "last_validated": None}).limit(limit))
