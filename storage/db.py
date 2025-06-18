import sqlite3
import os
from datetime import datetime

DB_PATH = "storage/jobs.db"

def init_db():
    os.makedirs("storage", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT,
            company TEXT,
            url TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def store_job_if_new(job_id, source, title, company, url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT 1 FROM jobs WHERE id = ?', (job_id,))
    exists = c.fetchone()
    if exists:
        conn.close()
        return False

    c.execute('''
        INSERT INTO jobs (id, source, title, company, url, seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (job_id, source, title, company, url, datetime.utcnow()))
    conn.commit()
    conn.close()
    return True
