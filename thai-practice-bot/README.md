# Thai Practice Tutor Bot

A Telegram bot that trains English speakers in Thai speaking like an
experienced professional teacher: short structured lessons, word-by-word
breakdowns, drilling, and the student produces their own sentences after
every lesson. Powered by the Claude API + OpenAI Whisper/TTS.

## How it works

- Lesson flow per turn: TEACH (one Thai sentence/pattern) → BREAK DOWN
  (word + transliteration + meaning) → DRILL (student says it) →
  PRODUCE (student makes their own sentence — mandatory) →
  CORRECT & ENCOURAGE.
- Students do NOT need to type Thai script — transliteration or English
  answers are fine. Thai script in lessons is for reading and listening.
- Voice: students speak Thai (Whisper, forced `th`) → the voice reply
  speaks the Thai-script lesson sentences (TTS onyx, male voice); the
  text carries transliteration, breakdowns, and instructions in English.
- Reply format: Thai-script block, then a `---` line, then the lesson
  content. The voice speaks only the Thai-script block.
- Male teacher persona. Starts from absolute beginner, builds up gradually.
- Per-user conversation history (last 10 exchanges) so lessons progress.
- `/start` — welcome, `/new` — restart the course from the beginning.
- Daily per-user message cap (`DAILY_LIMIT`, default 100).
- Private: single-use invite links (`/newcodes 20`, `/users`, `/revoke`).
- In groups it replies threaded under the student's message; DMs unthreaded.

## Deploy (Railway, 5th service in myanmar-bots)

Root directory: `thai-practice-bot` (Procfile: `worker: python bot.py`).
Attach a volume at `/data` and set `DATA_DIR=/data` for invite persistence.

Env vars: `BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (required);
`MODEL`, `TTS_VOICE`, `ADMIN_CHAT_ID`, `BOT_USERNAME`, `DATA_DIR`,
`DAILY_LIMIT` (optional).
