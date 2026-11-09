# TuneBox Converter

Telegram bot (owner-only): send it a YouTube, Facebook or Instagram
link, a direct link to one of your own videos, or send the video
file itself, and it returns the audio as an MP3 — or the video as
an MP4.

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
- `/mp3` — audio mode (default): links come back as an MP3
- `/mp4` — video mode: links come back as an MP4 (720p). Sticks
  until you send /mp3 again; resets to MP3 on a restart/redeploy.
- Paste a YouTube link (youtube.com/watch, youtu.be, Shorts) — the bot
  fetches the audio with yt-dlp, converts it to MP3 (128 kbps, 64 kbps
  if the file would exceed Telegram's 50 MB limit) and sends the MP3 back.
  In /mp4 mode it fetches the video at 720p instead, merged to MP4.
- Paste a Facebook link (facebook.com/watch, fb.watch) or an
  Instagram link (instagram.com/reel, /p, /reels) — same, one yt-dlp
  pass. Public Facebook videos usually need no sign-in; Instagram
  usually asks for one even for public reels, so INSTAGRAM_COOKIES
  (same Netscape cookies.txt export as YouTube, from instagram.com)
  is normally needed there. FACEBOOK_COOKIES is the same for
  facebook.com, for videos that ask for a sign-in.
- Paste a direct video link (mp4/mov/webm/mkv/…) — the bot downloads it,
  converts the audio to MP3 and sends the MP3 back (in /mp4 mode a
  video file is sent back as video instead).
- Or send a video/audio file directly to the bot.

## Limits

- Owner-only: only the admin id may use it.
- Input files up to 400 MB; output must fit Telegram's 50 MB
  bot-upload limit. MP4 is fetched at 720p and re-encoded smaller
  once if it is still too big; longer clips may still not fit.
- YouTube links are supported (single videos, no playlists); Facebook
  and Instagram links are supported the same way (single posts/reels,
  no feeds or stories). YouTube may block datacenter IPs with its
  "Sign in to confirm you're not a bot" check, in which case the bot
  reports the failure instead of hanging. The bot tries the android,
  iOS, then TV player clients without cookies first (web cookies can
  trip those up), then the web, Safari-web, mobile-web and embedded
  players with the signed-in cookies if YOUTUBE_COOKIES is set to the
  contents of a Netscape cookies.txt exported from a browser signed
  in to YouTube, plus the YouTube Music players for music videos.
  Plain web often answers a signed-in request with "Requested format
  is not available" — its formats need a Proof-of-Origin token, which
  is why the other players are tried. GOOGLE_COOKIES holds the same
  export from google.com (the session cookies live there); the web
  players may withhold formats without them. The tokens themselves
  come from a bgutil provider server (Docker image
  brainicism/bgutil-ytdlp-pot-provider, port 4416, run as its own
  Railway service with NO public domain — the bot reaches it over
  Railway private networking at
  http://bgutil-pot-provider.railway.internal:4416 via the
  POT_PROVIDER_URL variable); the bgutil-ytdlp-pot-provider plugin
  in requirements.txt asks it to mint each token. NOTE: yt-dlp ships
  no built-in token minter — its own debug output says "PO Token
  Providers: none" even with Deno installed — so a JS runtime in
  this image alone does not fix the web players. Deno IS still in
  the image, because yt-dlp's signature and "n" challenge solving
  needs a JS runtime too ("Signature solving failed" without one).
  The provider URL is passed as a one-element list: yt-dlp splits a
  bare string into characters and would read just "h" as the URL.
  Failed passes log the yt-dlp warnings they collected, so the
  Railway logs show the real reason (e.g. a missing token input)
  instead of just the final error.
- The bot only answers its owner (ADMIN_CHAT_ID); everyone else gets
  "Sorry — this bot is private, for its owner only."
