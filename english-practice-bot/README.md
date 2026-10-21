# English Practice Tutor Bot

A Telegram bot for MasterClass English students to practice English through
free conversation with gentle corrections. Powered by the Claude API.
Students can type **or send voice messages** — the bot transcribes with
Whisper, replies as the tutor, and answers back with a voice message (plus
the text, so corrections can be re-read).

## How it works

- Students just chat in English — the bot replies like a friendly tutor,
  corrects mistakes gently ("Small fix: ..."), and asks follow-up questions.
- Voice messages: transcribed as English (Whisper, language forced to English for
  reliability) → tutor reply (Claude) → spoken English answer in a male voice
  (TTS onyx), with the reply text sent after so corrections can be re-read.
  Students can still write in Myanmar via text — only voice is English-only. The admin gets a "👂 Heard: ..." line showing
  the raw transcript for testing.
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
| `MODEL` | no | default `claude-haiku-4-5-20251001` (English chat) |
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

## Video course (2026-10-21)

`/course` opens the **Pre-Intermediate Level Speaking Topics** course: 100 sets
as tappable options (10 per page, starting from Set 1 at the top). Tapping a
set sends its speaking video + worksheet PDF.

- Videos and worksheets are sent with `protect_content` — students can't save
  or forward them in Telegram (screen recording can't be blocked).
- Media is served by Telegram `file_id` (see `course_file_ids.json`) — no
  media hosting needed on the server.
- `course.py` holds the 100 set titles + keyboard builder; `bot.py` handles
  `/course` and the `course:p:` / `course:s:` callbacks (students allowed).
- Seeding: `python3 upload_course_media.py` with `BOT_TOKEN` + `ADMIN_CHAT_ID`
  set — uploads all 200 files once and writes `course_file_ids.json`.
