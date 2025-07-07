import os
from pymongo import MongoClient
from datetime import datetime
import certifi
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError
import ssl



load_dotenv()  # This loads variables from .en
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "job_alert")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION", "jobs")

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where()
)
#print("[MongoDB] Connected to MongoDB!")
db = client[DB_NAME]
jobs_collection = db[COLLECTION_NAME]


def store_job_if_new(job_id, source, title, company, url):
    # Use the job URL as the MongoDB _id for deduplication
    try:
        jobs_collection.insert_one({
            "_id": url,
            "source": source,
            "title": title,
            "company": company,
            "url": url,
            "seen_at": datetime.utcnow()
        })
        return True  # New job, inserted successfully
    except DuplicateKeyError:
        return False  # Job already exists
    except Exception as e:
        print(f"[MongoDB] Insert failed (not duplicate): {e}")
        return None  # Other MongoDB error
