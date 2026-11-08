# TuneBox Converter

Telegram bot (owner-only): send it a direct link to one of your own
videos, or send the video file itself, and it returns the audio as an MP3.

This is a converter for videos you own. It does not search, rip, or fetch
from YouTube, Spotify, or any streaming site.

## Setup

1. **Telegram bot** — talk to @BotFather: `/newbot`, pick a name and a
   username ending in `bot`. Copy the token.
2. **Railway** — new service from the `myanmar-bots` repo, root directory
   `tunebox-converter`. Set these variables:
   - `BOT_TOKEN` — the @BotFather token
   - `ADMIN_CHAT_ID` — your Telegram user id (default 8028025915)

## Use

- `/start` — welcome
- Paste a direct video link (mp4/mov/webm/mkv/…) — the bot downloads it,
  converts the audio to MP3 (128 kbps, 64 kbps if the file would exceed
  Telegram's 50 MB limit) and sends the MP3 back.
- Or send a video/audio file directly to the bot.

## Limits

- Owner-only: only the admin id may use it.
- Input files up to 400 MB; output MP3 must fit Telegram's 50 MB
  bot-upload limit.
- Only direct file links — no YouTube, Spotify, or streaming pages.
