# English Practice Tutor Bot

A Telegram bot for MasterClass English students to practice English through
free conversation with gentle corrections. Powered by the Claude API.

## How it works

- Students just chat in English — the bot replies like a friendly tutor,
  corrects mistakes gently ("Small fix: ..."), and asks follow-up questions.
- Per-user conversation history (last 10 exchanges) for natural dialogue.
- `/start` — welcome message, `/new` — fresh conversation.
- Daily per-user message cap (`DAILY_LIMIT`, default 100) to bound API costs.
- In groups it replies threaded under the student's message; DMs unthreaded.
- Shows "typing..." while the AI thinks.

## Deploy (Railway, 4th service in myanmar-bots)

Root directory: `english-practice-bot` (Procfile: `worker: python bot.py`).

Env vars:

| Var | Required | Notes |
|---|---|---|
| `BOT_TOKEN` | yes | from @BotFather (`/newbot`) |
| `ANTHROPIC_API_KEY` | yes | from console.anthropic.com |
| `MODEL` | no | default `claude-haiku-4-5-20251001` (cheap + fast) |
| `ADMIN_CHAT_ID` | no | gets error alerts |
| `DAILY_LIMIT` | no | default 100 msgs/user/day |

## Cost note

Every student message calls the Claude API (Haiku is the cheapest model).
The daily cap keeps costs predictable — roughly a few dollars/month for
normal class use, depending on volume.
