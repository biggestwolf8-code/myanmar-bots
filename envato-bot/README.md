# Envato Elements personal download bot

Private Telegram bot (@EnvatoElementsUnlimited_Bot) for the owner's own
Envato Elements unlimited subscription: search the library from Telegram,
download any item with its license certificate.

## Access

Invite-code gated, **no cap** on the number of accounts. The first user to
`/start` becomes the owner; the owner mints single-use invite links for
their other Telegram accounts:

- `/newcodes [n]` — generate n single-use invite links (default 5)
- `/users` — list activated accounts
- `/revoke CODE` — deactivate an account

## Commands

- `/search <keywords>` (or just type keywords) — search Elements
- `/recent` — recent downloads, re-issue links
- `/status` — Envato session health
- `/setcookie <cookie>` — refresh the Envato login session

Files ≤50 MB are sent directly in chat; larger files get a secure
24-hour download link served by the built-in web server (`/dl/<token>`).

## Env vars

- `BOT_TOKEN` — from @BotFather
- `DATA_DIR` — persistent dir (Railway volume): codes, session cookie, downloads
- `ADMIN_CHAT_ID` — optional pinned owner id
- `PUBLIC_URL` — public base URL for file links (Railway domain)

## Deploy

Railway service `envato-bot`, root dir `myanmar-bots/envato-bot`.
Needs a volume mounted at `DATA_DIR` and `PUBLIC_URL` set to the public domain.
