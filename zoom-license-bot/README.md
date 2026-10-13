# Zoom License Monitor — Telegram bot

Watches the license status (Licensed vs Basic) of 15 Zoom accounts
(`onlineclass.22517+c53` … `c67@gmail.com`) and alerts the admin when a
license lapses.

## How it works

- One Zoom OAuth app (user-managed, scope `user:read`) is authorized once
  per Zoom account. The bot stores per-account **refresh tokens**
  (Fernet-encrypted) — never passwords.
- `/check` (or the daily auto-check at 09:00 Bangkok time) calls
  `GET /v2/users/me` for each token and reads the `type` field
  (1 = Basic, 2 = Licensed).
- Any change since the last check is reported to the admin.

## Setup

1. Create the Zoom OAuth app at https://marketplace.zoom.us → Develop →
   Build App → OAuth. Redirect URI:
   `https://<railway-service-url>/oauth/callback`, scope `user:read`.
2. Deploy this repo as a Railway web service (`Procfile: web: python bot.py`)
   with a volume mounted at `/data`.
3. Set env vars (see below). `ENCRYPTION_KEY`: generate with
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
4. Update the Zoom app's redirect URI to the real Railway URL.
5. For each Zoom account: sign in at zoom.us, open the authorize URL
   (get one per account via the bot's `/reauth <c62>` command), click
   Authorize. The bot captures and stores the token via `/oauth/callback`.
6. Run `/check` in Telegram to verify all 15.

## Env vars

| Var | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `ADMIN_CHAT_ID` | Telegram user id allowed to use the bot |
| `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` | Zoom OAuth app credentials |
| `ZOOM_REDIRECT_URI` | `https://<railway-url>/oauth/callback` |
| `ENCRYPTION_KEY` | Fernet key for token storage |
| `DATA_DIR` | `/data` on Railway (volume) |
| `CHECK_HOUR` | Daily check hour, Bangkok time (default 9) |
| `PORT` | Set by Railway |

## Commands (admin only)

- `/check` — check all licenses now
- `/status` — last known statuses
- `/accounts` — authorization coverage
- `/reauth <c62>` — authorize link for one account
- `/alerts on|off` — daily auto-check alerts
