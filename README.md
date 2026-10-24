# LifeOps — Assignment Deadline Assistant (Phase 1)

LifeOps helps you capture assignments by voice, manually, or from uploaded assignment briefs; track submission status; and send Telegram deadline reminders.

## Features

- Manual assignment capture with course, deadline, priority, estimated effort, and notes.
- Voice capture using Sarvam Saaras v4 transcription and an OpenAI tool-calling agent.
- Upload PDF, DOCX, TXT, MD, CSV, or common image files. OpenAI extracts likely assignment details; the user reviews and confirms before saving.
- Assignment dashboard with overdue/today/upcoming states and `Not started` / `In progress` / `Submitted` status.
- Telegram reminders 3 days before, 1 day before, and on the deadline; reminder records prevent duplicate sends for the same assignment/deadline/offset.
- Optional Sarvam Bulbul text-to-speech replies.
- SQLite database with migrations for existing Phase 1 task databases.

## Local setup

Python 3.10+ recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env` locally. Never commit `.env`, API keys, Telegram bot token, or `lifeops.db`.

Start the dashboard:

```powershell
python -m streamlit run app.py
```

## Set up Telegram

1. In Telegram, open `@BotFather`, create a bot with `/newbot`, and copy its token into `TELEGRAM_BOT_TOKEN`.
2. Open the new bot and press **Start** (the bot cannot initiate a private chat until you start it).
3. Get your chat ID. One straightforward method is to send the bot a message, then open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and read `message.chat.id`. Keep the token private; do not share screenshots containing it.
4. Put the chat ID in `TELEGRAM_CHAT_ID`.
5. Test sending a message by running `python -c "from telegram_reminders import send_telegram_message; send_telegram_message('LifeOps Telegram test')"`.

## Run the reminder checker

The reminder checker is a separate process; it does not depend on the Streamlit page being open. It checks assignments due in 3 days, 1 day, or today, sends a Telegram message, and records successful sends so repeated runs do not duplicate them.

```powershell
python telegram_reminders.py
```

Schedule this command to run once per day using Windows Task Scheduler for local testing. Configure `LIFEOPS_TIMEZONE=Asia/Kolkata` for India. Run it daily in the morning (for example 8:00 AM local time). If the computer is asleep or off, that run will not happen until it wakes.

### Deployment architecture warning

**Do not run the reminder worker on a separate machine with its own copy of `lifeops.db`.** It would not see assignments saved by the web app. Both processes must access the same persistent database and filesystem.

For a reliable hosted deployment, run the Streamlit dashboard and scheduled reminder process on a host with a persistent disk and a way to run scheduled commands, sharing the same `lifeops.db`. Streamlit Community Cloud's local filesystem is not a durable shared database and a separate GitHub Actions runner will have a different database. If you want to keep the dashboard on Streamlit Community Cloud, the next architecture step is moving the data to a shared hosted database such as PostgreSQL/Supabase and configuring both the app and reminder worker to use it.

## Streamlit Community Cloud secrets

If deploying the dashboard to Streamlit Community Cloud, add the following in **App → Settings → Secrets**:

```toml
OPENAI_API_KEY = "your-openai-api-key"
OPENAI_MODEL = "gpt-4.1-mini"
SARVAM_API_KEY = "your-sarvam-api-key"
TELEGRAM_BOT_TOKEN = "your-telegram-bot-token"
TELEGRAM_CHAT_ID = "your-telegram-chat-id"
LIFEOPS_TIMEZONE = "Asia/Kolkata"
```

These secrets enable dashboard integrations, but **they do not by themselves schedule reminders**. The reminder worker still needs to run on a scheduler with access to the same persistent database.

## Notes and limitations

- Uploaded documents are parsed for extraction and are not saved as files by this MVP; only the filename and confirmed fields are stored.
- Scanned PDFs may not contain extractable text. Upload page images or a text-based PDF if extraction fails.
- AI-extracted deadlines can be wrong or ambiguous; review the date before saving. Missing dates are not invented.
- The reminder checker sends a reminder when it runs on one of the target dates. A failed Telegram send is not logged as sent and can be retried on the next run that day.
- SQLite is retained for a local MVP. For multiple deployed processes or durable hosted use, move to a shared persistent database before relying on reminders.
- Voice input is recorded audio, not continuous streaming.
