# TuneBox — private music streaming web app

A Spotify-style player for your own audio files. Listeners join with
invite codes (`https://<host>/i/<CODE>`), browse the library, build
playlists, and stream. The admin uploads tracks and manages codes.

Only upload audio you own or have the rights to share.

## Deploy (Railway)

New service from the `myanmar-bots` repo, root directory `music-web`,
plus a volume mounted at `/data`.

| Env var | Required | Description |
|---|---|---|
| `ADMIN_PASSWORD` | ✅ | Password for the `/admin` panel |
| `DATA_DIR` | ✅ | `/data` (volume mount — tracks, codes, playlists survive redeploys) |
| `MAX_UPLOAD_MB` | — | Max upload size in MB (default: 300) |
| `PORT` | — | Listen port (Railway sets this automatically) |

## Features

- **Invite access** — single-use codes locked to a browser session; share
  links like `https://<host>/i/AB12CD34` (auto-redeem on open).
- **Player** — play/pause, next/previous, seek bar, volume, shuffle,
  repeat off/all/one, up-next queue, keyboard shortcuts (space, ←/→).
- **Library** — search across title/artist/album, play counts.
- **Playlists** — create, delete, add/remove tracks per listener.
- **Admin panel** (`/admin`) — upload MP3/M4A/OGG/WAV/FLAC with
  title/artist/album, delete tracks, generate invite codes with labels,
  revoke codes, top-tracks stats.
- **Mobile friendly** — responsive layout with collapsible sidebar.

## Local dev

```bash
pip install -r requirements.txt
ADMIN_PASSWORD=secret python app.py
# player: http://localhost:5000   admin: http://localhost:5000/admin
```
