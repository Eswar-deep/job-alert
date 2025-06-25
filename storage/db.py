from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["job_alert"]  # You can use any database name you like
jobs_collection = db["jobs"]

def init_db():
    # Create a unique index on 'id' to prevent duplicates
    jobs_collection.create_index("id", unique=True)

def store_job_if_new(job_id, source, title, company, url):
    if jobs_collection.find_one({"id": job_id}):
        return False
    jobs_collection.insert_one({
        "id": job_id,
        "source": source,
        "title": title,
        "company": company,
        "url": url
    })
    return True
