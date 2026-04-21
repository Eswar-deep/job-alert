import os
from pymongo import MongoClient
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
import certifi
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError




load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "job_alert")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION", "jobs")

_mongo_collection = None
_sqlite_path = Path("storage") / "jobs.db"


def _get_mongo_collection():
    global _mongo_collection
    if _mongo_collection is not None:
        return _mongo_collection
    if not MONGO_URI:
        return None

    try:
        client = MongoClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
        )
        db = client[DB_NAME]
        _mongo_collection = db[COLLECTION_NAME]
        return _mongo_collection
    except Exception as e:
        print(f"[MongoDB] Connection failed, falling back to SQLite: {e}")
        return None


def _ensure_sqlite():
    _sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                company TEXT,
                url TEXT,
                seen_at TEXT
            )
            """
        )
        conn.commit()


def store_job_if_new(job_id, source, title, company, url):
    # Use the caller-provided job_id for deduplication (Mongo _id / SQLite primary key).
    mongo = _get_mongo_collection()
    now_utc = datetime.now(timezone.utc)
    if mongo is not None:
        try:
            mongo.insert_one(
                {
                    "_id": job_id,
                    "source": source,
                    "title": title,
                    "company": company,
                    "url": url,
                    "seen_at": now_utc,
                }
            )
            return True
        except DuplicateKeyError:
            return False
        except Exception as e:
            print(f"[MongoDB] Insert failed (not duplicate), falling back to SQLite: {e}")

    try:
        _ensure_sqlite()
        with sqlite3.connect(_sqlite_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO jobs (id, source, title, company, url, seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (job_id, source, title, company, url, now_utc.isoformat()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    except Exception as e:
        print(f"[SQLite] Insert failed: {e}")
        return None
