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
- `/sell` — post a product card to the group (live profile only)
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
name → age → role → pick products (toggle buttons) → price per
product → payment details (KBZPay, WavePay, AYAPay, USDT on BSC,
bank name + account number; at least one required; `/skip` keeps
the old value when editing) → 3 photos (required, see v5).
These are the seller's OWN payment details — the bot's class-pack
details (above) stay separate and are Arkar's only.

**Profiles go live immediately** — there is no approval gate. (The
Zoom-live approval gate was dropped 2026-11-16: members can start
posting without the Zoom class.) Both admins get an FYI notification
for each new profile, with a "Remove seller" button — moderation,
not a gate. Removing a seller takes their live cards down too, and
they must make a new profile to sell again. `/board` posts only live
sellers.

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

## v4 — member self-service product cards (`/sell`)

Any member with a live profile can post their own product to the
group as a shopping card — no admin step, no Zoom class needed.

**Flow** — `/sell` in DM (or the "📣 Post to group" button on
`/myprofile` and in the profile-live message):
1. Pick one of your own profile products (milk, eggplant, peaches,
   donut, HD).
2. Name your options — up to 4, seller types the names (like A, B,
   C, D, or a size/flavour), then a price for each, typed in Ks,
   validated 5,000–50,000 Ks. `/done` finishes early; the 4th option
   goes straight to the media step. Or tap "Use profile price" to post
   a single option at the product's profile price.
3. (v5) Send one product photo or video for the sneak peek, or
   `/skip` for a text-only card. A video also needs a preview photo.
4. Confirm the preview, and the bot posts the card to the group.

**The card** — "🛍️ \<name\>, \<age\> • \<role\> — \<product\>" (v5;
in v4 it was just "🛍️ \<seller\> — \<product\>") with one Buy button
per option ("\<name\> — \<price\> Ks"), a "👤 Seller profile"
button, and a "🗑️ Remove" button. The Buy buttons are deep links
into the bot (`/start card_<id>_<option>`), so they work even for
members who never started the bot — tapping one opens the normal
buy flow for that option at that price (balance / Stars / USDT /
pay seller directly + receipt), with the option name carried through
every payment path and into `/sales`. The seller (or an admin) can
remove their own card with the Remove button on it; removing a
seller (admin) takes their cards down too.

**Gate** — `/sell` needs only a live profile. If the group isn't
linked yet (`GROUP_CHAT_ID` / `/setgroup`), `/sell` says so plainly
instead of failing. Cards are recorded in `state.json` (`cards`,
with message id, seller, product, options and status) so sales can
be linked back to the card they came from.

## v5 — richer profiles + sneak-peek preview + reveal on purchase

**Profile** — `/profile` now collects age, role and 3 photos, in
that order after the display name (age → role → products → prices
→ payment details → photos → confirm):
- **Age** — typed as a number, validated numeric (no 18+ block).
- **Role** — buttons Top / Bottom / Verse, or "Something else…"
  for typed free text (1–30 chars). A typed role is also accepted
  directly at the role step.
- **3 photos** — the seller sends 3 photos of themselves, one by
  one. `/skip` is NOT allowed until all 3 are saved; profile
  creation cannot finish without them. (Editing with 3 already
  saved: `/skip` keeps them; sending a new photo swaps the oldest.)
- Profiles store `age`, `role`, `photos` (3 Telegram file_ids).
  Every profile card shows them: the seller card sends the 3 photos
  as a media group first, then the text card ("Age: 28 • Role:
  Top"). `/myprofile` does the same; `/sellers` and `/board` lines
  show "Name, 28 • Top".
- **Older profiles** (made in v2–v4, no age/role/photos) show "—"
  for the missing bits, and `/sell` prompts the seller to complete
  their profile first — a short flow that walks only the missing
  pieces (age → role → photos → confirm), instead of failing.

**Cards carry the profile** — every shopping card reads
"🛍️ \<name\>, \<age\> • \<role\> — \<product\>".

**Sneak peek** — `/sell` has a media step after the options: the
seller sends one product photo or video (the full version), or
`/skip` for a text-only card. A video also needs a preview photo.
The card posted to the group shows only a **blurred** preview
(Pillow `GaussianBlur` after a hard downscale — details are not
visible; the full media is never posted on the card). The blurred
preview is made once at preview time and its file_id stored on the
card; the card is posted with `sendPhoto` + caption when it has a
preview, plain text otherwise. Needs `Pillow` in requirements.txt
(the bot downloads the source photo via `getFile` + the Telegram
file URL, blurs it in memory/temp only, uploads the preview).

**Reveal on purchase** — the FIRST completed purchase of a card
posts the full media to the group for everyone to see:
"🔓 Revealed: \<seller\>'s \<product\> (\<option\>) — bought by
\<buyer\>". The card is then marked `revealed` so later purchases
do not re-post it. The reveal hooks into every completed-sale
path: balance buy, Stars (`successful_payment`), USDT now,
USDT-direct, and direct-receipt CONFIRM (only when the receipt is
approved, not when it is sent). Cards with no media have nothing
to reveal; old v4 cards (no media on record) are handled
gracefully.

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
drafts, cashouts, sellusdt, cards, card drafts), `credits.json`,
`purchases.json` (kinds: `pack`, `market`, `topup`, `cashout`,
`sellusdt`; market sales carry an `option` field when bought from a
card option), `used_tx.json`, `users.json`, `profiles.json` (seller
profiles + status; each profile also holds `age`, `role`, `photos`
— 3 file_ids), `balances.json` (user id → balance in Ks). Cards in
`state.json` also hold `age`/`role` (snapshot), `media_type`,
`media_file_id` (full version), `preview_file_id` (blurred) and
`revealed` (false until the first completed purchase).
