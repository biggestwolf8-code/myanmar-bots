# English Practice Tutor Bot

A Telegram bot for MasterClass English students to practice English through
free conversation with gentle corrections. Powered by the Claude API.
Students can type **or send voice messages** — the bot transcribes with
Whisper, replies as the tutor, and answers back with a voice message (plus
the text, so corrections can be re-read).

## How it works

- Students just chat in English — the bot replies like a friendly tutor,
  corrects mistakes gently ("Small fix: ..."), and asks follow-up questions.
- Voice messages: transcribed with auto language detection (English, Myanmar, or a mix —
  a bilingual prompt plus a Myanmar-forced retry help short Myanmar utterances)
  → tutor reply (Claude) → spoken English answer in a male voice (TTS onyx),
  with the full bilingual reply (English + 🇲🇲 Myanmar subtitle, using ကျွန်တော်) as text.
- Per-user conversation history (last 10 exchanges) for natural dialogue.
- `/start` — welcome message, `/new` — fresh conversation.
- Daily per-user message cap (`DAILY_LIMIT`, default 100) to bound API costs.
- In groups it replies threaded under the student's message; DMs unthreaded.
- Shows "typing..." / "recording voice..." while working.

## Deploy (Railway, 4th service in myanmar-bots)

Root directory: `english-practice-bot` (Procfile: `worker: python bot.py`).

Env vars:

| Var | Required | Notes |
|---|---|---|
| `BOT_TOKEN` | yes | from @BotFather (`/newbot`) |
| `ANTHROPIC_API_KEY` | yes | from console.anthropic.com |
| `OPENAI_API_KEY` | for voice | from platform.openai.com (Whisper + TTS) |
| `MODEL` | no | default `claude-haiku-4-5-20251001` |
| `TTS_VOICE` | no | default `onyx` (male voice) |
| `ADMIN_CHAT_ID` | no | gets error alerts |
| `DAILY_LIMIT` | no | default 100 msgs/user/day |

## Access control (invite links)

The bot is private — strangers can't run up your API bill:
- Message the bot `/newcodes 20` → it replies with 20 single-use invite links.
- Send **one link per student, privately** (DM, not a group).
- The first Telegram account to open a link is locked to it; the link can't be
  reused or shared. Anyone else gets a "ask Sayar Arkar" notice — no API cost.
- `/users` lists activated students, `/revoke CODE` deactivates one.

Invite state lives in `codes.json` under `DATA_DIR` — on Railway, attach a
volume at `/data` and set `DATA_DIR=/data` so invites survive redeploys.
