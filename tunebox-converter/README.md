# TuneBox Converter

Telegram bot (owner-only): send it a YouTube link, a direct link to one
of your own videos, or send the video file itself, and it returns the
audio as an MP3.

This is a converter for videos you own. It does not search or fetch
from Spotify or any other streaming site.

## Setup

1. **Telegram bot** — talk to @BotFather: `/newbot`, pick a name and a
   username ending in `bot`. Copy the token.
2. **Railway** — new service from the `myanmar-bots` repo, root directory
   `tunebox-converter`. Set these variables:
   - `BOT_TOKEN` — the @BotFather token
   - `ADMIN_CHAT_ID` — your Telegram user id (default 8028025915)

## Use

- `/start` — welcome
- Paste a YouTube link (youtube.com/watch, youtu.be, Shorts) — the bot
  fetches the audio with yt-dlp, converts it to MP3 (128 kbps, 64 kbps
  if the file would exceed Telegram's 50 MB limit) and sends the MP3 back.
- Paste a direct video link (mp4/mov/webm/mkv/…) — the bot downloads it,
  converts the audio to MP3 and sends the MP3 back.
- Or send a video/audio file directly to the bot.

## Limits

- Owner-only: only the admin id may use it.
- Input files up to 400 MB; output MP3 must fit Telegram's 50 MB
  bot-upload limit.
- YouTube links are supported (single videos, no playlists); other
  streaming pages are not. YouTube may block datacenter IPs with its
  "Sign in to confirm you're not a bot" check, in which case the bot
  reports the failure instead of hanging. The bot tries the android,
  iOS, TV, then web player clients to get past that check; if they all
  fail, set the YOUTUBE_COOKIES env var to the contents of a Netscape
  cookies.txt exported from a browser signed in to YouTube, and the
  bot downloads with that signed-in session.
