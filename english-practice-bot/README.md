# English Practice Tutor Bot

A Telegram bot for MasterClass English students to practice English through
free conversation with gentle corrections. Powered by the Claude API.
Students can type **or send voice messages** — the bot transcribes with
Whisper, replies as the tutor, and answers back with a voice message (plus
the text, so corrections can be re-read).

## How it works

- Students just chat in English — the bot replies like a friendly tutor,
  corrects mistakes gently ("Small fix: ..."), and asks follow-up questions.
- Voice messages: transcribed with auto language detection (English, Myanmar, or a mix)
  → tutor reply (Claude) → spoken English answer (TTS) sent as a voice message,
  with the full bilingual reply (English + 🇲🇲 Myanmar subtitle) as text.
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
| `MODEL` | no | default `claude-haiku-5-5` (cheapest + fastest) |
| `TTS_VOICE` | no | default `nova` |
| `ADMIN_CHAT_ID` | no | gets error alerts |
| `DAILY_LIMIT` | no | default 100 msgs/user/day |

## Cost note

Every student message calls the Claude API (Haiku is the cheapest model).
The daily cap keeps costs predictable — roughly a few dollars/month for
normal class use, depending on volume.
