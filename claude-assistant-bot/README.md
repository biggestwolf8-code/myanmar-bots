# Claude Assistant Bot for Telegram

A general-purpose AI assistant on Telegram, powered by the Claude API.
Each user chats 1-on-1: questions, homework, writing help, translations,
ideas — in English, Myanmar, or Thai.

**Private by design.** Strangers can't use it. Each person gets a
single-use invite link (`t.me/<bot>?start=CODE`); the first Telegram
account to open it locks to that code. This keeps Claude API costs
under control.

## Deploy (Railway)

Root directory: `claude-assistant-bot` · start command: `python bot.py`

| Env var | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | From @BotFather |
| `ANTHROPIC_API_KEY` | ✅ | Claude API key (console.anthropic.com) |
| `BOT_USERNAME` | ✅ | Bot username without @ (for invite links) |
| `ADMIN_CHAT_ID` | ✅ | Your Telegram user id — full access + admin commands |
| `DATA_DIR` | ✅ | `/data` with a Railway volume mounted there (invites survive redeploys) |
| `MODEL` | — | Claude model id (default: `claude-haiku-4-5-20251001`) |
| `DAILY_LIMIT` | — | Max messages per user per day (default: 100) |

## Admin commands

- `/newcodes 20` — generate 20 single-use invite links (send one per person, privately)
- `/users` — list activated users + unused invites
- `/revoke CODE` (or `/revoke <telegram user id>`) — deactivate access

## File creation

Ask the bot for an Excel spreadsheet or a PDF document and it builds the file
and sends it as an attachment. Excel comes from CSV data (via openpyxl);
PDFs are rendered with the embedded Padauk font so Myanmar text displays
correctly (via fpdf2 + HarfBuzz shaping).

## Notes

- Per-user conversation history (last 10 exchanges) for natural follow-ups.
- `/new` starts a fresh conversation.
- Daily per-user message cap protects against runaway API spend.
- Text-only (no voice) — cheap and simple; voice could be added later.
