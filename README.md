# 🛎️ Job Alert Bot

A Python bot that monitors internship and entry-level job postings from several job boards and **notifies you instantly via Telegram**.

---

## ✅ Features

- Tracks jobs from:
  - 📘 [GitHub: Summer 2026 Internships Repo](https://github.com/vanshb03/Summer2026-Internships)
  - 🟡 [Simplify.jobs](https://simplify.jobs) *(work in progress)*
  - 🟢 [Notify.Careers](https://notify.careers) *(filter support in progress)*
- Sends job alerts through **Telegram**
- Prevents duplicate alerts with **SQLite cache**
- Supports **custom filters** for Notify jobs
- Runs headlessly via **Playwright**

---

## 📁 Project Structure

```plaintext
job-alert/
├── main.py                # Script entry point
├── scrapers/              # Scraper scripts
│   ├── github_scraper.py
│   ├── simplify_scraper.py     # In development
│   └── notify_scraper.py       # Filter handling in progress
├── notify/
│   └── telegram_bot.py    # Telegram notification logic
├── storage/
│   ├── db.py              # SQLite operations
│   └── jobs.db            # Job cache DB
├── notify_filters.json    # Custom filters for Notify
├── .env                   # Telegram credentials
├── requirements.txt       # Project dependencies
└── README.md              # Project documentation
```

---

## 🚀 Quick Start

### 1. Clone the Repo

```bash
git clone https://github.com/your-username/job-alert.git
cd job-alert
```

### 2. Set Up a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
playwright install
```

---

## 🔐 Telegram Bot Setup

Create a `.env` file:

```dotenv
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

To get your `TELEGRAM_CHAT_ID`, send a message to your bot and visit:

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

---

## 🧪 Running the Bot

```bash
python main.py
```

> ✅ All new jobs are automatically sent to your Telegram.

---

## 🎛️ Notify Filters (Optional)

To filter Notify.Careers jobs, customize `notify_filters.json`:

```json
{
  "fields": ["AI & Machine Learning", "Software Engineering"],
  "experience_levels": ["Internship", "Entry Level/New Grad"]
}
```

> ⚠️ Filters are still under testing — results may vary.

---

## 🗂️ Job Source Status

| Source         | Status         | Notes                              |
|----------------|----------------|-------------------------------------|
| GitHub         | ✅ Working     | Markdown parsed                     |
| Simplify.jobs  | 🚧 In Progress | Requires JS rendering improvements  |
| Notify.Careers | ⚙️ WIP         | Clicking filters needs tuning       |

---

## 📦 Dependencies

```txt
certifi==2025.6.15
charset-normalizer==3.4.2
idna==3.10
python-dotenv==1.0.1
requests==2.32.4
urllib3==2.2.3
playwright
```

Install Playwright browser binaries:

```bash
playwright install
```

---

## 💡 To Do

- [x] GitHub job parsing
- [ ] Fix Simplify dynamic scraping
- [ ] Finalize Notify filters
- [ ] Add Google Careers, LinkedIn, etc.
- [ ] Add scheduling via cron or GitHub Actions

---

## 🤝 Contribute

Found a bug or want to add more scrapers? PRs are welcome!

---

## 📄 License

MIT License. Free to use and modify. Give credit where due ✨
