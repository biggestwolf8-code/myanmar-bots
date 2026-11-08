# Spotify Links Bot

Telegram bot: type a song name, get the top Spotify matches with a button
that opens each song in Spotify. Telegram unfurls the top link into a
playable Spotify card. The bot only shares links — it never downloads music.

## Setup

1. **Telegram bot** — talk to @BotFather: `/newbot`, pick a name and a
   username ending in `bot`. Copy the token.
2. **Spotify app** — at developer.spotify.com, create an app (any name),
   copy its Client ID and Client Secret. Search uses the
   client-credentials flow, so no user login is needed.
3. **Railway** — new service from the `myanmar-bots` repo, root directory
   `spotify-links-bot`. Set these variables:
   - `BOT_TOKEN` — the @BotFather token
   - `SPOTIFY_CLIENT_ID` — from the Spotify app
   - `SPOTIFY_CLIENT_SECRET` — from the Spotify app
   - `ADMIN_CHAT_ID` — optional, for error reports

## Use

- `/start` — welcome
- `/help` — how to use it
- Type any song name, or `/search <song name>`

Replies list the top 5 tracks (title, artist, album) with one tap-to-open
button per track.

## Limits (Spotify's, not ours)

- Development-mode Spotify apps return at most 10 results per search
  (this bot asks for 5).
- The Web API offers no preview audio for new apps — links only, by design.
- Full playback happens in Spotify itself (Premium + logged in, per
  Spotify's rules). This bot never charges for Spotify content.
