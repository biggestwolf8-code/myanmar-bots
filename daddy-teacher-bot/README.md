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
- `/profile` — make/edit your seller profile (guided steps)
- `/myprofile` — your profile + its status
- `/sellers` — live sellers + their products
- `/balance` — your bot balance
- `/topup` — top up by Stars ($1/$2/$5/$10/$20) or USDT
- `/cashout` — cash out your balance as USDT (1 USDT = 4,500 Ks)
- `/sellusdt` — sell your USDT to Arkar (1 USDT = 4,500 Ks)
- `/id` — this chat's id (works in the group too)

Admin (HenryRealGood 7061620871, SirArkar 8028025915):
- `/newsession <topic> | <date/time>` — create + post a session card
- `/newsession` — interactive prompt for topic + date/time
- `/post <text>` — announcement with pack buttons
- `/board` — post the live sellers board to the group
- `/setgroup <@group>` — where sessions go (or forward a group post
  / paste a copied `t.me/c/...` post link)
- `/sessions` — list posted sessions
- `/users` — buyers, credits, packs bought (+ live sellers)
- `/sales` — recent purchases (packs, top-ups, marketplace sales)
- `/id` — this chat's id
- `/help` — full help
- `/cancel` — cancel an interactive draft

## v2 — seller profiles + peer-to-peer market

The group is a live show on Zoom where members sell their own
products. Products (fixed list): milk, eggplant, peaches, donut, HD.
Each seller sets their own price per product, typed in Ks,
validated to 5,000–50,000 Ks.

**Seller profiles** — `/profile` runs a guided setup in DM: display
name → pick products (toggle buttons) → price per product → payment
details (KBZPay, WavePay, AYAPay, USDT on BSC, bank name + account
number; at least one required; `/skip` keeps the old value when
editing). These are the seller's OWN payment details — the bot's
class-pack details (above) stay separate and are Arkar's only.

**Approval gate (Zoom live)** — the bot cannot see Zoom attendance,
so a new or edited profile is PENDING until an admin approves it.
Both admins get the profile with Approve / Decline buttons; the
notification says to approve only after seeing the seller join the
Zoom live. A second admin tap says "Already handled". `/board`
posts only live sellers.

**Buying** — a buyer taps a seller (in `/sellers` or on the board),
then a product, and chooses how to pay:
- 💰 Balance — debit buyer, credit seller (no commission).
- ⭐ Stars now — native XTR invoice to the bot; the seller gets the
  amount in bot balance. (Stars are rounded to whole Stars:
  `round(price_Ks / 50)`; the seller is credited the exact price.)
- 💎 USDT now — pay the bot's USDT address, hash verified on-chain;
  the seller gets the amount in bot balance.
- 🇲🇲 Direct — pay the seller's own KBZPay / WavePay / AYAPay /
  bank (receipt photo, confirmed by the seller or an admin) or the
  seller's USDT address (hash verified on-chain to that address,
  auto-confirmed).

**Balances** — `/balance` shows the balance in Ks (and USD).
`/topup` offers Stars ($1/$2/$5/$10/$20 invoices) or USDT (same
amounts, on-chain verify to the bot's address; what actually arrives
is credited). Balances can be spent on any live seller's products,
or cashed out — see v3 below.

## v3 — cash-out + sell USDT (rate 1 USDT = 4,500 Ks)

**⚠️ Two different rates — do not mix them up:**
- Product prices, packs, Stars and top-ups: **1 USD = 5,000 Ks**.
- Cash-out and sell-USDT only: **1 USDT = 4,500 Ks**.

**`/cashout`** — a member cashes out bot balance as USDT at
1 USDT = 4,500 Ks. Minimum 4,500 Ks (1 USDT); whole USDT only —
47,000 Ks cashes out as 10 USDT (45,000 Ks) and the other 2,000 Ks
stays in the balance. Flow: `/cashout` → type the Ks amount →
confirm the USDT payout address (defaults to the address on the
seller's profile, `/keep` to use it, or type a new one) → request
goes to both admins with Approve / Decline. **Approve only after
the admin has sent the USDT from their own wallet** — approving
debits the seller's balance by the cashed-out Ks and tells the
seller "Paid: X USDT sent to <address>". Decline leaves the balance
untouched. A second admin tap says "Already handled". Cash-outs are
recorded in `state.json` (`cashouts`) and shown in `/sales`.

**`/sellusdt`** — a member sells USDT they already hold to Arkar at
1 USDT = 4,500 Ks. Flow: `/sellusdt` → type the USDT amount (whole
numbers) → bot shows Arkar's USDT address
(`0xffef0a1f5b075ed8763d7e0b13c9e3df04819222`, with the one-tap
"📋 Copy USDT address" button) and the MMK due (amount × 4,500) →
seller sends the USDT and pastes the transaction hash → bot
verifies it on-chain (same `verify_usdt_tx`, to Arkar's address;
already-used hashes are rejected) → on success both admins get the
amount, the MMK due, and the seller's profile payment details
(KBZPay / WavePay / AYAPay / bank) with a "Paid MMK" button →
admin taps it after paying the MMK and the seller is notified. If
the hash doesn't verify, the seller is told plainly and can retry.
Sales are recorded in `state.json` (`sellusdt`) and shown in `/sales`.

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
`state.json` (group, sessions, pending payments, receipts, profile
drafts, cashouts, sellusdt), `credits.json`, `purchases.json` (kinds:
`pack`, `market`, `topup`, `cashout`, `sellusdt`), `used_tx.json`,
`users.json`, `profiles.json` (seller profiles + status),
`balances.json` (user id → balance in Ks).
