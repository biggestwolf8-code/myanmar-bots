# MasterClass English — Telegram auto-reply bot

Fixed FAQ answers (English + Burmese). Anything it can't answer is forwarded
to you, and your reply is relayed back to the student.

## Step 1 — Create the bot (2 min, on your phone)

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Pick a display name, e.g. `MasterClass English`.
3. Pick a username ending in `bot`, e.g. `masterclass_english_bot`.
4. BotFather gives you a **token** — that's the bot's password. Keep it private.

## Step 2 — Get your Telegram user id

1. In Telegram, open **@userinfobot** and send any message.
2. It replies with your numeric id — that's `ADMIN_CHAT_ID`.

## Step 3 — Fill in the FAQ

Edit `faq.json` — replace every `[FILL IN]` answer with your real info
(course fees, how to enroll, payment methods/account numbers).
Keywords are substring-matched; keep them specific to avoid wrong answers.

## Step 4 — Test it on a computer

```bash
cd telegram-bot
pip install -r requirements.txt
BOT_TOKEN=<paste-token> ADMIN_CHAT_ID=<your-id> python bot.py
```

Open your bot in Telegram, send `/start`, and try some questions.

## Step 5 — Host it 24/7

Long polling needs an always-on machine. Options:

**Railway / Render (easiest)** — connect this folder as a repo, add a
background worker using the `Procfile`, set `BOT_TOKEN` and `ADMIN_CHAT_ID`
as environment variables. (Free tiers may sleep; a ~$5/mo plan stays awake.)

**Cheap VPS** — copy the folder to the server, then a systemd service:

```ini
[Unit]
Description=MasterClass English Telegram bot
After=network.target

[Service]
WorkingDirectory=/opt/mce-bot
EnvironmentFile=/opt/mce-bot/.env   # contains BOT_TOKEN=... and ADMIN_CHAT_ID=...
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## How the admin reply-back works

- Student asks something the FAQ can't answer → bot forwards it to you.
- You **reply** to that forwarded message → the bot sends your reply to the student.
