# 🛎️ Job Alert Bot

**How to use this README like a cheat code**  
1. **Fork this repo** so you have your own copy.  
2. **Copy this entire README** (yes, all of it).  
3. **Paste it into ChatGPT** and say:  
   > Help me set this up step-by-step  
4. Follow along — you’ll get a personalized walk-through for installing, configuring, and running your own bot.

---

A Python bot that monitors internship and entry-level job postings from several job boards and **notifies you instantly via Telegram**. Supports custom filters, deduplication, and can run locally or via GitHub Actions.

---

## 🚀 Features

- Tracks jobs from:
  - 📘 **GitHub:** Scrapes two curated internship/entry-level job listing repositories:
    - [Summer 2026 Internships Repo](https://github.com/vanshb03/Summer2026-Internships)
    - [New Grad 2025 Repo](https://github.com/vanshb03/New-Grad-2025)
  - 🟢 [Notify.Careers](https://notify.careers)
  - 🟣 Workday job boards
- Sends job alerts through **Telegram**
- Prevents duplicate alerts with **MongoDB** (default) or SQLite (local)
- Supports **custom filters** for Notify jobs
- Runs headlessly via **Playwright**
- Can be scheduled via **GitHub Actions** or run manually

---

## ⚡ Quick Start

1. **Clone the Repo**
   ```bash
   git clone https://github.com/your-username/job-alert.git
   cd job-alert
   ```
2. **Set Up a Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate     # Windows: venv\Scripts\activate
   ```
3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```
4. **Set Up Secrets**
   - Create a `.env` file **or** set GitHub Actions secrets:
     ```dotenv
     TELEGRAM_BOT_TOKEN=your_telegram_bot_token
     TELEGRAM_CHAT_ID=your_chat_id
     MONGO_URI=your_mongodb_connection_string  # Optional for local, required for Actions
     ```
   - To get your `TELEGRAM_CHAT_ID`, send a message to your bot and visit:
     `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
5. **Run the Bot Locally**
   ```bash
   python main.py
   ```
   > ✅ All new jobs are automatically sent to your Telegram.

---

## 🤖 Telegram Bot Setup
- Create a bot with [@BotFather](https://t.me/BotFather) and get your token.
- Add your bot to your Telegram group or chat.
- Use the `.env` file or GitHub secrets as shown above.

---

## 🎛️ Job Sources & Filter Support

- **GitHub:** Fully supported, parses markdown tables for new jobs from both the Summer Internships and New Grad repositories.
- **Simplify.jobs:** Under progress
- **Notify.Careers:** Supported with custom filters. Edit `notify_filters.json` to filter by field or experience level:
  ```json
  {
    "fields": ["AI & Machine Learning", "Software Engineering"],
    "experience_levels": ["Internship", "Entry Level/New Grad"]
  }
  ```
- **Workday:** Supported for scraping jobs from Workday-powered job boards.
  > **Note:** Some Workday job postings are not visible in public job listings and are only accessible via direct application links ("applylinks"). This bot can only scrape jobs that are publicly listed on Workday-powered job boards.

---

## 🛠️ How It Works

- **Scraping:** The bot scrapes job boards for new postings.
- **Deduplication:** Each job's URL is stored in MongoDB (or SQLite for local runs). If a job is already in the DB, it is skipped.
- **Notification:** New jobs are sent to your Telegram via the bot.
- **Filters:** For Notify.Careers, jobs are filtered according to your `notify_filters.json` settings.

---

## ⏰ GitHub Actions: Manual & Scheduled Runs

- **Manual Run:** Use the "Run workflow" button in the Actions tab to trigger the bot at any time.
- **Scheduled Run:** The workflow can run automatically (e.g., every 10 minutes) using a cron schedule in `.github/workflows/job-alert.yml`.
- **Secrets Required:** Set `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, and `MONGO_URI` as repository secrets.
- **Fork Limitation:**
  - Scheduled workflows (`on: schedule`) only run automatically on the default branch of the **original repository**.
  - **Forks:** Scheduled runs are disabled by default and unreliable even if enabled. Manual runs always work.

---

## 📦 Dependencies

All required Python packages are listed in `requirements.txt`.
Install them with:

```bash
pip install -r requirements.txt
```

After installing Python dependencies, you must also install Playwright browser binaries:

```bash
playwright install
```

**Key dependencies:**
- `pymongo` — Required for MongoDB support (deduplication)
- `playwright` — For headless browser scraping
- `requests`, `python-dotenv`, etc. — For HTTP requests and environment variable management
- If you run locally and want to use SQLite, no extra package is needed (it's built into Python)

> See `requirements.txt` for the full list and versions.

---

## 🛠️ Troubleshooting & FAQ

**Q: I don't get any Telegram notifications!**
- Check that your `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` are correct and set as secrets.
- Check the Actions logs for errors like `[TelegramBot] Failed to send message: ...`.
- Make sure your bot is not blocked by your Telegram account.
- You may have already gotten the notification for the job applications.

**Q: Scheduled runs don't happen in my forked repo!**
- This is a GitHub limitation. Scheduled workflows are not reliably triggered on forks. Use manual runs or set up the project as a standalone repo.

**Q: How do I test Telegram notifications?**
- Run the bot manually with `python main.py` after setting up your `.env` or repository secrets.
- You should receive a test message if there are new jobs.

**Q: Why are some Workday jobs missing from my notifications?**
- Some Workday job postings are only accessible via direct application links ("applylinks") and are not in public listings. The bot can only scrape publicly listed jobs.

---

## 🤝 Contributing

Found a bug or want to add more scrapers? PRs are welcome! Please open an issue or pull request.

---

## 🤖 Want Job Alerts with My Filters?

If you want to receive job notifications with the same filters I use, you are welcome to contact me! I can set up the Telegram bot for you so you'll get the same notifications directly to your Telegram as well.

---

## 📄 License

MIT License. Free to use and modify. Give credit where due ✨

---

## 🗃️ Job Source Status

| Source         | Status           | Notes                                 |
|----------------|------------------|---------------------------------------|
| GitHub         | ✅ Working       | Markdown parsed from two repos        |
| Notify.Careers | ✅ Working       | Filter support available              |
| Workday        | ✅ Working       | Workday job board scraping            |
| Simplify.jobs  | In Progress      | Dynamic page, takes too long to scrape|
| LinkedIn       | Not Yet Supported| Scraping is difficult                 |
