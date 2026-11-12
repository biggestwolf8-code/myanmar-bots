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

All messages, photos and videos the bot sends carry `protect_content=True`, so
customers cannot forward or save them in the Telegram apps. Note: this
does not block screenshots or screen recording — no bot can do that.

Second layer (photos only): every photo a customer taps is watermarked
with their own Telegram identity (`@username | ID <id>`) — a faint
diagonal repeat plus a readable bottom bar — before it is sent, so a
leaked screenshot traces back to who took it. If watermarking ever
fails, the bot falls back to sending the original photo (still
protected) so a tap never breaks. Videos are NOT watermarked (that
would need a full re-encode per viewer); they rely on protect_content.

Paid video tabs: a video button costs 100 Telegram Stars or 1 USDT
(BSC/BEP20), one-time per user per video. Stars go through Telegram's
native invoice flow (XTR) and land in the bot's Stars balance
(withdrawable by the bot owner via Fragment). USDT is verified on-chain:
the user pastes their transaction hash, the bot checks a public BSC
node for a >= 1 USDT transfer to the address above; spent hashes are
recorded so one payment cannot unlock twice.

Revoking: every message the bot sends is logged in sent.json, and the
admin can delete it again — /revoke user <id>, /revoke board <id>,
/revoke all. Only messages sent after logging was added are revocable.
Deleting removes the message from the chat; it cannot undo a screenshot
or a screen recording. Forward any post from the channel to the bot and
it stores the channel's numeric id as the post target.

Developed by Arkar Myowin.
