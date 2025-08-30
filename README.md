# Goethe Checker Bot

A Discord slash-command bot that verifies **Goethe exam portal login credentials** in bulk.  
Upload `.csv` or `.txt` files, paste inline credentials, or type directly — the bot will check them asynchronously and return success/failure results with detailed reasons.  
Results are summarized in Discord and can be exported as CSV for record-keeping.

---

## ✨ Features

- **Slash Commands** (`/verify`, `/export`)  
- **Bulk Verification** of `email|password` credentials  
- Accepts **inline text**, **file uploads**, or **interactive input**  
- **Smart detection** of login success/failure via Goethe CAS  
- **Summaries** (success/failure counts, rate)  
- **Detailed Results** inline (≤10 accounts) or CSV export (>10 accounts)  
- Automatically saves results to `final_verified_list.csv` (or custom file via `MASTER_FILE`)  

---

## 🚀 Getting Started

1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/goethe-checker-bot.git
cd goethe-checker-bot

2. Create .env

Inside the project folder:

DISCORD_TOKEN=your_discord_bot_token_here
# Optional: override default CSV filename
MASTER_FILE=final_verified_list.csv

3. Install dependencies
pip install -r requirements.txt

4. Run the bot
python bot.py

⚡ Commands
/verify

Upload a .csv or .txt file with lines like:

email1@example.com|password123
email2@example.com|mypassword


Or paste credentials directly as inline text.

Or, if left blank, the bot will prompt you to send them interactively.

Bot replies with:

✅ Success / ❌ Failure counts

📈 Success rate (%)

Inline details for ≤10 accounts

CSV file for >10 accounts

/export

Re-sends the most recent verification results as a CSV file.

📂 Project Structure
goethe_checker_bot/
├── bot.py        # Main Discord bot (commands, logic, exports)
├── checker.py    # Goethe login checking (async, aiohttp)
├── requirements.txt
├── .env          # Your secrets (not committed)
└── README.md

🛠 Tech Stack

Python 3.10+

discord.py
 (slash commands)

aiohttp
 (async HTTP requests)

pandas
 (data processing & CSV export)

🔒 Security Notes

Use only with accounts you own or have explicit permission to test.

Storing or sharing credentials without consent may violate privacy laws.

The developers assume no liability for misuse of this tool.

📜 License

This project is for educational and internal use only.
Not affiliated with or endorsed by Goethe-Institut.
