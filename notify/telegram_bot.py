import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("[TelegramBot] Missing TELEGRAM_TOKEN or CHAT_ID.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print("[TelegramBot] Message sent.")
    except Exception as e:
        print(f"[TelegramBot] Failed to send message: {e}")

