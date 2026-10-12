# Thai Practice Tutor Bot

A Telegram bot for English speakers to practice speaking Thai through free
conversation with gentle corrections. Powered by the Claude API + OpenAI
Whisper/TTS. Mirror of the English practice bot.

## How it works

- Students chat in Thai — type or voice. The bot replies in Thai (Thai script)
  with an English translation, corrects mistakes gently ("Small fix: ..."),
  and asks follow-up questions.
- Voice: transcribed as Thai (Whisper, forced `th` — reliable, unlike
  Burmese auto-detect) → tutor reply (Claude) → spoken Thai answer (TTS onyx,
  male voice). Text carries Thai + English.
- Male tutor persona. Corrections explained in English.
- Per-user conversation history (last 10 exchanges).
- `/start` — welcome, `/new` — fresh conversation.
- Daily per-user message cap (`DAILY_LIMIT`, default 100).
- Private: single-use invite links (`/newcodes 20`, `/users`, `/revoke`).
  See the English practice bot README for the invite flow.
- In groups it replies threaded under the student's message; DMs unthreaded.

## Deploy (Railway, 5th service in myanmar-bots)

Root directory: `thai-practice-bot` (Procfile: `worker: python bot.py`).
Attach a volume at `/data` and set `DATA_DIR=/data` for invite persistence.

Env vars: `BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (required);
`MODEL`, `TTS_VOICE`, `ADMIN_CHAT_ID`, `BOT_USERNAME`, `DATA_DIR`,
`DAILY_LIMIT` (optional).
