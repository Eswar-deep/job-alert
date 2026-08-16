# discovery/registry.py
"""
Registry of ATS company boards.

Primary store is MongoDB (`ats_companies`). If Mongo is unavailable, everything
falls back to a local JSON file so discovery is never blocked by a dead cluster.

Document shape:
{
  "_id": "greenhouse:stripe",
  "platform": "greenhouse",
  "slug": "stripe",
  "extra": {"region": "us"},
  "active": true,
  "first_seen": ISODate,
  "last_validated": ISODate,
  "consecutive_failures": 0,
  "job_count": 142
}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection

from discovery.slug_extractor import ATSCandidate

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "job_alert")
REGISTRY_COLLECTION = os.getenv("MONGO_ATS_COLLECTION", "ats_companies")

MAX_CONSECUTIVE_FAILURES = 5
LOCAL_PATH = Path("discovery") / "boards.json"

_collection: Optional[Collection] = None
_mongo_unavailable = False  # cache the failure; do not retry on every call


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_collection() -> Optional[Collection]:
    global _collection, _mongo_unavailable
    if _collection is not None:
        return _collection
    if _mongo_unavailable:
        return None
    if not MONGO_URI:
        print("[Registry] MONGO_URI not set — using local file store.")
        _mongo_unavailable = True
        return None
    try:
        client = MongoClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
        )
        client.admin.command("ping")
        _collection = client[DB_NAME][REGISTRY_COLLECTION]
        return _collection
    except Exception as e:
        print(f"[Registry] Mongo unavailable ({type(e).__name__}) — using local file store.")
        _mongo_unavailable = True
        return None


# --------------------------------------------------------------------------- #
# Local JSON fallback                                                          #
# --------------------------------------------------------------------------- #

def _load_local() -> Dict[str, dict]:
    if not LOCAL_PATH.exists():
        return {}
    try:
        with LOCAL_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local(data: Dict[str, dict]) -> None:
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def upsert_candidates(candidates: List[ATSCandidate], validated: bool = False) -> int:
    if not candidates:
        return 0
    coll = get_collection()
    now = _now()

    if coll is None:
        data = _load_local()
        added = 0
        for c in candidates:
            if c.key not in data:
                data[c.key] = {
                    "platform": c.platform,
                    "slug": c.slug,
                    "extra": c.extra,
                    "active": validated,
                    "first_seen": now.isoformat(),
                    "last_validated": now.isoformat() if validated else None,
                    "consecutive_failures": 0,
                    "job_count": 0,
                }
                added += 1
            elif validated:
                data[c.key]["active"] = True
                data[c.key]["last_validated"] = now.isoformat()
                data[c.key]["consecutive_failures"] = 0
        _save_local(data)
        return added

    ops: List[UpdateOne] = []
    for c in candidates:
        # A field may appear in $setOnInsert OR $set, never both — Mongo raises
        # "would create a conflict at <path>" (code 40) and the whole batch fails.
        set_on_insert = {
            "platform": c.platform,
            "slug": c.slug,
            "extra": c.extra,
            "first_seen": now,
            "job_count": 0,
        }
        if validated:
            update: dict = {
                "$setOnInsert": set_on_insert,
                "$set": {
                    "active": True,
                    "last_validated": now,
                    "consecutive_failures": 0,
                },
            }
        else:
            set_on_insert["active"] = False
            set_on_insert["last_validated"] = None
            set_on_insert["consecutive_failures"] = 0
            update = {"$setOnInsert": set_on_insert}
        ops.append(UpdateOne({"_id": c.key}, update, upsert=True))

    return get_collection().bulk_write(ops, ordered=False).upserted_count


def mark_success(key: str, job_count: int) -> None:
    coll = get_collection()
    if coll is None:
        data = _load_local()
        if key in data:
            data[key].update({
                "active": True,
                "last_validated": _now().isoformat(),
                "consecutive_failures": 0,
                "job_count": job_count,
            })
            _save_local(data)
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


def bulk_mark_success(results: List[tuple]) -> None:
    """Batch equivalent of mark_success. `results` is a list of (key, job_count)."""
    if not results:
        return
    coll = get_collection()
    now = _now()
    if coll is None:
        data = _load_local()
        for key, count in results:
            if key in data:
                data[key].update({
                    "active": True,
                    "last_validated": now.isoformat(),
                    "consecutive_failures": 0,
                    "job_count": count,
                })
        _save_local(data)
        return
    ops = [
        UpdateOne(
            {"_id": key},
            {"$set": {
                "active": True,
                "last_validated": now,
                "consecutive_failures": 0,
                "job_count": count,
            }},
        )
        for key, count in results
    ]
    for i in range(0, len(ops), 500):
        coll.bulk_write(ops[i:i + 500], ordered=False)


def mark_failure(key: str) -> None:
    coll = get_collection()
    if coll is None:
        data = _load_local()
        if key in data:
            data[key]["consecutive_failures"] = data[key].get("consecutive_failures", 0) + 1
            if data[key]["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
                data[key]["active"] = False
            _save_local(data)
        return
    doc = coll.find_one_and_update(
        {"_id": key}, {"$inc": {"consecutive_failures": 1}}, return_document=True
    )
    if doc and doc.get("consecutive_failures", 0) >= MAX_CONSECUTIVE_FAILURES:
        coll.update_one({"_id": key}, {"$set": {"active": False}})
        print(f"[Registry] Retired {key} after {MAX_CONSECUTIVE_FAILURES} failures.")


def get_active_boards(platform: Optional[str] = None) -> List[dict]:
    coll = get_collection()
    if coll is None:
        data = _load_local()
        out = []
        for key, doc in data.items():
            if not doc.get("active"):
                continue
            if platform and doc.get("platform") != platform:
                continue
            out.append({"_id": key, **doc})
        return out
    query: dict = {"active": True}
    if platform:
        query["platform"] = platform
    return list(coll.find(query))


def get_unvalidated(limit: int = 500) -> List[dict]:
    coll = get_collection()
    if coll is None:
        data = _load_local()
        return [
            {"_id": k, **v}
            for k, v in data.items()
            if not v.get("active") and v.get("last_validated") is None
        ][:limit]
    return list(coll.find({"active": False, "last_validated": None}).limit(limit))