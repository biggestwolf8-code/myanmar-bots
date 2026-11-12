# Daddy3.0 bot

Interactive game-board bot for Arkar's channel. A board is a post with
inline buttons; each button is tied to one photo. A user taps a button
in the channel and the photo is sent to their PRIVATE chat.

Admin is Arkar (HenryRealGood 7061620871 + SirArkar 8028025915).

## Admin design flow (bot DM)

1. `/newboard` — start a draft
2. Send the board title (plain text)
3. Send photos one by one — the CAPTION on each photo becomes its
   button label (e.g. "Show his balls", "Take off his clothes")
4. `/done` — save + preview
5. `/post <id>` — post the board to the channel

Other commands: `/boards`, `/delboard <id>`, `/setchannel <@channel>`,
`/cancel`, `/help`.

## Setup

Railway service `daddy-bot`, Root Directory `daddy-bot`.

Env vars:
- `BOT_TOKEN` — from BotFather (bot created by @HenryRealGood)
- `ADMIN_CHAT_IDS` — `7061620871,8028025915`
- `DATA_DIR` — `/data` (volume `daddy-bot-data`); boards.json lives there

The bot must be an admin in the target channel with post permission.
Photos are stored as Telegram file_ids only — Telegram hosts the images.

All messages and photos the bot sends carry `protect_content=True`, so
customers cannot forward or save them in the Telegram apps. Note: this
does not block screenshots or screen recording — no bot can do that.

Developed by Arkar Myowin.
