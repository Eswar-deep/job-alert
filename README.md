# 🛎️ Job Alert Bot

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
- **Simplify.jobs:** Supported, but may require updates if site layout changes.
- **Notify.Careers:** Supported with custom filters. Edit `notify_filters.json` to filter by field or experience level:
  ```json
  {
    "fields": ["AI & Machine Learning", "Software Engineering"],
    "experience_levels": ["Internship", "Entry Level/New Grad"]
  }
  ```
- **Workday:** Supported for scraping jobs from Workday-powered job boards.
  > **Note:** Some Workday job postings are not visible in public job listings and are only accessible via direct application links ("applylinks"). This bot can only scrape jobs that are publicly listed on Workday-powered job boards. If a job is only accessible through a special link, it will not be detected by the scraper.

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

## 🧹 How to Clear the Job Cache

If you want to receive notifications for all jobs again:
- **MongoDB:**
  - Connect to your database and run:
    ```js
    db.jobs.deleteMany({})
    ```
- **SQLite:**
  - Delete the `storage/jobs.db` file.

---

## 🛠️ Troubleshooting & FAQ

**Q: I don't get any Telegram notifications!**
- Check that your `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` are correct and set as secrets.
- Check the Actions logs for errors like `[TelegramBot] Failed to send message: ...`.
- Make sure your bot is not blocked by your Telegram account.

**Q: The bot says jobs are "already sent" but I never got them!**
- This means the job URLs are already in the database. This can happen if:
  - The bot ran before with the same jobs.
  - Telegram credentials were wrong during the first run (jobs were marked as sent but not delivered).
- Clear the job cache to resend all jobs.

**Q: Scheduled runs don't happen in my forked repo!**
- This is a GitHub limitation. Scheduled workflows are not reliably triggered on forks. Use manual runs or set up the project as a standalone repo.

**Q: How do I test Telegram notifications?**
- Run the bot manually with `python main.py` after setting up your `.env` or repository secrets.
- You should receive a test message if there are new jobs.

**Q: How do I use my own MongoDB?**
- Set the `MONGO_URI` secret to your MongoDB connection string.
- The bot will use this database for deduplication.

**Q: Why are some Workday jobs missing from my notifications?**
- Some Workday job postings are only accessible via direct application links ("applylinks") and do not appear in the public Workday job listings. The bot can only scrape jobs that are publicly listed on Workday-powered job boards.

---

## 🤝 Contributing

Found a bug or want to add more scrapers? PRs are welcome! Please open an issue or pull request.

---

## 🤖 Want Job Alerts with My Filters?

If you want to receive job notifications with the same filters I use, you are welcome to contact me! I can set up the Telegram bot for you so you'll get the same notifications directly to your Telegram as well.

Feel free to open an issue or reach out via the contact information in my GitHub profile.

---

## 📄 License

MIT License. Free to use and modify. Give credit where due ✨

---

## 🗃️ Job Source Status

| Source         | Status         | Notes                              |
|----------------|----------------|-------------------------------------|
| GitHub         | ✅ Working     | Markdown parsed                     |
| Notify.Careers | ✅ Working     | Filter support available            |
| Workday        | ✅ Working     | Workday job board scraping          |

---

## �� Dependencies

```