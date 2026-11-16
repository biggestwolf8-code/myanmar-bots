# DaddyTeacher bot (@DaddyTeacherBot)

English class bot for gay learners. 1-hour sessions, each teaching one
topic + 10 new phrases. Students buy session packs; the admin posts
sessions to the teaching group (t.me/DaddyTeachEnglish).

Based on the Daddy3.0 bot (`../daddy-bot/bot.py`) — same Telegram API
helpers, Stars invoicing, USDT (BSC) on-chain verification and
receipt-photo admin approval patterns.

## Session packs (anchor 1 USD = 5,000 Ks)

| Pack | Price | Stars | USDT |
| ---- | ----- | ----- | ---- |
| 1 session  | 15,000 Ks ($3) | 300 | 3 |
| 2 sessions | 20,000 Ks ($4) | 400 | 4 |
| 4 sessions | 30,000 Ks ($6) | 600 | 6 |

## Payment methods

- **Telegram Stars** — native Stars invoice (XTR).
- **USDT on BSC (BEP20)** — student pastes the transaction hash; the
  bot verifies it on-chain via a public BSC node. Address is shown
  with a one-tap "📋 Copy USDT address" button (standing rule).
  Address: `0xffef0a1f5b075ed8763d7e0b13c9e3df04819222`
- **Myanmar pay** — KBZPay 09403720481, WavePay 09780695959,
  AYAPay 09754926216 (Arkar Myo Win). Student sends a receipt
  screenshot; it is forwarded to every admin with Approve / Decline
  buttons. Approve adds the session credits.
- **Thai QR / PromptPay** — student messages @SirArkar, then sends
  the receipt here; same admin approve flow.

## Commands

Students:
- `/start` — welcome + the three packs
- `/mysessions` — sessions left
- `/id` — this chat's id (works in the group too)

Admin (HenryRealGood 7061620871, SirArkar 8028025915):
- `/newsession <topic> | <date/time>` — create + post a session card
- `/newsession` — interactive prompt for topic + date/time
- `/post <text>` — announcement with pack buttons
- `/setgroup <@group>` — where sessions go (or forward a group post
  / paste a copied `t.me/c/...` post link)
- `/sessions` — list posted sessions
- `/users` — buyers, credits, packs bought
- `/sales` — recent purchases (method + status)
- `/id` — this chat's id
- `/help` — full help
- `/cancel` — cancel an interactive /newsession draft

## Setup (Railway)

Service type: worker. Start command: `python bot.py`.

Environment variables:

| Variable | Required | Value |
| -------- | -------- | ----- |
| `BOT_TOKEN` | yes | BotFather token for @DaddyTeacherBot |
| `ADMIN_CHAT_IDS` | no | default `7061620871,8028025915` |
| `GROUP_CHAT_ID` | no | leave unset at first — see below |
| `USDT_ADDRESS` | no | default is Arkar's BSC address above |
| `BOT_USERNAME` | no | default `DaddyTeacherBot` |
| `DATA_DIR` | no | defaults to the app directory |

## First run — finding the group chat id

`GROUP_CHAT_ID` is intentionally unset at first. To set it:

1. Add @DaddyTeacherBot to the teaching group (t.me/DaddyTeachEnglish)
   and make it an admin (needed to post).
2. In the group, send `/id` — the bot replies with the group's
   numeric id (e.g. `-100...`).
3. Set `GROUP_CHAT_ID` to that id in Railway (or send
   `/setgroup` from an admin DM — the bot also accepts a forwarded
   group message or a copied `t.me/c/...` post link to learn the id).
4. Restart the service, then send `/newsession` from an admin DM to
   test a post.

## State

JSON files in `DATA_DIR` (same pattern as daddy-bot):
`state.json` (group, sessions, pending payments, receipts),
`credits.json`, `purchases.json`, `used_tx.json`, `users.json`.
