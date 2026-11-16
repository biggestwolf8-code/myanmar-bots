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
- `/auction` — post a video auction to the group (live profile only)
- `/pool` — post a group-buy pool to the group (seller-set price 50,000–500,000 Ks, 1,000 Ks or more per person, live profile only)
- `/poolinfo <pool id>` — full contributor list for a pool
- `/sellers` — live sellers + their products
- `/balance` — your bot balance
- `/topup` — top up by Stars ($1/$2/$5/$10/$20), USDT, or KBZPay / WavePay / AYAPay (min 5,000 Ks)
- `/cashout` — cash out your balance as USDT (1 USDT = 4,500 Ks)
- `/sellusdt` — sell your USDT to Arkar (1 USDT = 4,500 Ks)
- `/id` — this chat's id (works in the group too)

Admin (HenryRealGood 7061620871, SirArkar 8028025915):
- `/newsession <topic> | <date/time>` — create + post a session card
- `/newsession` — interactive prompt for topic + date/time
- `/post <text>` — announcement with pack buttons
- `/announce` — post an announcement to the group (tap to choose: main intro, fundraiser pool, or both)
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
`/topup` offers Stars ($1/$2/$5/$10/$20 invoices), USDT (same
amounts, on-chain verify to the bot's address; what actually arrives
is credited), or KBZPay / WavePay / AYAPay (pay the admin, send the
receipt — min 5,000 Ks, admin approves and the balance is credited). Balances can be spent on any live seller's products,
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

## v6 — auction house + seller titles

**Auction house** — `/auction` (or pick "🔨 Auction" after choosing
a product in `/sell`) posts a video auction instead of a fixed-price
card. Same gates as `/sell`: a live profile and a linked group.
- **Flow** — `/auction` → pick a product → send the video → the
  seller picks the cover for this post — the video's own thumbnail
  or a photo of their own, **unblurred** (if the video has no
  thumbnail, the seller sends a cover photo, or `/skip` to post
  with no cover) → confirm the preview → the bot posts the auction
  card to the group.
- **Rules** — starting bid is fixed at **5,000 Ks**. The auction
  runs **24 hours only**. Auction videos must be **1 to 30 minutes**
  long (the bot refuses shorter/longer ones and asks for another
  video); the card shows the length as "⏱️ N min". A new bid must beat the current bid by
  at least **1,000 Ks** (quick bids: +1,000 / +5,000 / +10,000 over
  the current bid, or a typed amount). Bids come from the bidder's
  **bot balance only** — top up with `/topup` (Stars/USDT) first if
  short. A bid is escrowed: the bidder's balance is debited at once
  and the previous highest bidder is refunded immediately. The
  seller cannot bid on their own auction, and the current leader
  cannot bid again until someone outbids them.
- **Winning** — at the 24-hour deadline the escrowed bid goes to
  the seller's balance and the video is sent **privately to the
  winner's DM** (`protect_content`) — it is NOT revealed in the
  group. **Exception: if an admin wins, the video IS revealed in
  the whole group** (posted there with `protect_content`). The
  auction card is deleted at once when someone wins.
- **No bids** — the auction closes, the post stays up, and the
  24-hour sweep deletes it 24 hours after the auction ended.
  Fixed-price cards are never auto-deleted.
- **Removed mid-auction** — if the seller is removed (admin) the
  highest bidder is refunded and the card is deleted.
- **Sweeps** — the deadline + 24-hour sweeps run inside the
  polling loop (`sweep_auctions` every iteration) — no external
  cron. Auction sales are recorded in `purchases.json` (kind
  `auction`) and shown in `/sales`.

**Seller titles** — every seller gets a title from their completed
sales, computed live at render time from the sales records (market
sales + auction sales, both status `paid`; class session packs do
NOT count), so titles upgrade automatically — no stored title to
go stale:
- 0 sold: 🆕 New Seller · 1–4: 🛍️ Seller · 5–9: 🌟 Rising Star ·
  10–24: 🔥 Top Seller · 25–49: 👑 Star Seller · 50+: 💎 Legend
- Shown as "\<title\> • \<N\> sold" on the seller's profile card,
  `/myprofile`, every fixed-price card, every auction card, the
  `/sellers` list and the `/board` lines.

## v6.2 — Myanmar-payment balance top-up

- **Flow** — `/topup` → tap "🇲🇲 KBZPay / WavePay / AYAPay" → the
  bot shows Arkar's admin numbers (KBZPay `09403720481`, WavePay
  `09780695959`, AYAPay `09754926216`, as `<code>` so members can tap
  to copy) → member types the amount in Ks → member pays and sends
  the receipt photo here → both admins get the receipt with
  **✅ Approve — credit balance** / **❌ Decline**.
- **Minimum 5,000 Ks** — anything below is rejected and the member
  types again. Whole Ks only; commas/spaces accepted ("10,000").
- **Approve** (admin only) — the member's balance is credited by
  exactly the stated amount (`change_balance`), recorded with
  `record_topup` (method "Myanmar (KBZPay/WavePay/AYAPay)"), and the
  member is told their new balance. The receipt is marked approved
  before crediting, and a second Approve tap gets "Already handled"
  — a receipt can never credit twice.
- **Decline** — nothing is credited; the member is told to check the
  amount/payment and try again.
- Receipts use a new `pending_mm` kind `topup_mm` (the USDT-hash
  flow keeps its own `pending_usdt` "topup" kind) and a new receipt
  kind `topup_mm`; the receipt record carries the `ks` amount.
  `/topup`, `/help` and the `/start` welcome all mention the Myanmar
  option and the 5,000 Ks minimum.

## v7 — group-buy pool ("fundraiser pool")

**Pool** — `/pool` (or pick "🤝 Pool" after choosing a product in
`/sell`) posts a group-buy pool instead of a fixed-price card.
Same gates as `/sell`: a live profile and a linked group.
- **Flow** — `/pool` → pick a product → type the pool price
  (whole Ks, **50,000–500,000**) → send the video → the seller
  picks the cover for this post — the video's own thumbnail or a
  photo of their own, **unblurred** (if the video has no thumbnail,
  the seller sends a cover photo, or `/skip` to post with no cover)
  → confirm the preview → the bot posts the pool card to the group.
  The preview has a "💰 Change amount" button, and `/poolinfo`
  lets the seller change the amount on a live pool too (v7.10).
- **Rules** — the price is **seller-set, 50,000–500,000 Ks**.
  Each member puts in **1,000 Ks or more per contribution, as
  often as they like** — every top-up adds to their running total
  (one entry per member). The pool fills when the total raised
  hits the set price, however many people that takes. Joining
  comes from the member's **bot balance only** — top up with
  `/topup` first if short. The seller cannot join their own pool.
  Pool videos must be **1 to 30 minutes** long (same rule as
  auctions); the card shows the length as "⏱️ N min".
- **Contributor list** — the pool card shows a list under the
  meter ("the meter list"): one line per member with their
  running total, **highest first** (e.g. "@alice — 10,000 Ks").
  The card caption is limited to 1,024 characters, so it shows
  the **top 10** plus an "…and N more people (see /poolinfo
  \<id\>)" line when the list is cut. The **full list** is in
  `/poolinfo <pool id>` (or the 📋 Contributors button on the
  card), which lists every contributor with their total.
  On completion the video goes privately to each contributor
  **once**; on cancel/remove each member is refunded their
  **total**.
- **Capping** — the final contribution is capped at exactly what's
  left, so the pool always totals exactly the set price and the
  seller always gets exactly the set price. If less is left than
  the member offered, only what's needed is taken and the member
  is told so plainly.
- **Completion** — when the total raised hits the set price the
  seller gets the full price in their balance, the video is sent
  **privately to every contributor's DM** (`protect_content`), and
  the pool card is deleted at once. The video is NEVER revealed in
  the group.
- **Live meter** — the card shows a 10-segment money progress bar
  (`pool_meter`), refreshed on every join: e.g. on a 100,000 Ks
  pool with 32,000 raised,
  `▓▓▓░░░░░░░ 32,000 / 100,000 Ks • 68,000 Ks to go`, plus the
  contributor count on its own line. The same rendering is used on
  the group card, the seller preview and the join prompt.
- **No deadline** — a pool stays open until it fills. If the seller
  or an admin removes it (card Remove button, or admin Remove-seller
  flow), every contributor is refunded the exact amount they put
  in, at once.
- **Sales + titles** — a completed pool is recorded in
  `purchases.json` (kind `pool`, with the contributor count) and
  shown in `/sales`; it counts as ONE sale for the seller's title.

## v7.1 — cash out by Myanmar payment

**Cash-out** — `/cashout` now offers two methods:
- **💵 USDT** (unchanged from v3) — 1 USDT = 4,500 Ks, minimum
  4,500 Ks, whole USDT only; leftovers stay in the balance.
- **🇲🇲 KBZPay / WavePay / AYAPay** — the admin sends the Ks to
  the member's own account, **1:1, no conversion, no fee**,
  minimum **5,000 Ks** (same as the Myanmar top-up minimum).
- **Flow** — pick Myanmar → choose one of the saved accounts from
  the member's profile (buttons, e.g. "KBZPay 0940…") or "⌨️ Type
  a different number" → type the amount (whole Ks, min 5,000, at
  most the balance) → both admins get the request ("💸 Myanmar
  cash-out request coN — N Ks → KBZPay 0940…") with "✅ Paid — Ks
  sent" / "❌ Decline" buttons. A member with no saved Myanmar
  account types the service and number instead (e.g. "WavePay
  09780695959").
- **Approve means the admin has ALREADY sent the Ks** (mirrors the
  USDT wording). Approving marks the request handled + saves
  BEFORE debiting, so a second Approve answers "Already handled."
  and debits nothing — the same guard as the Myanmar top-up
  approve. Declining debits nothing and tells the member to check
  their account details or message @HenryRealGood.
- **Records** — Myanmar cash-outs are recorded in
  `purchases.json` (kind `cashout`, status `paid` / `declined`,
  method "Myanmar (KBZPay/WavePay/AYAPay)", address "KBZPay
  0940…") and shown in `/sales` as "cash-out N Ks → KBZPay
  0940…". The draft lives in `cashout_mm_draft` (separate from
  the USDT `cashout_draft`); requests live in `cashouts` with
  `method: "mm"` and are decided only by the `cmmok:` / `cmmno:`
  buttons — the USDT `cook:` / `cono:` buttons refuse them.

## v7.3 — admin announcement list + repeat pool contributions

**Announcements** — `/announce` (admin DM only) shows a short
list message with three tappable buttons:
- **📢 Main intro** — posts the main DaddyTeacher intro
  announcement to the group.
- **🤝 Fundraiser pool** — posts the pool announcement to the
  group.
- **📢🤝 Both** — posts the main intro first, then the pool
  announcement.
- The list message itself is never posted — only the chosen
  announcement(s) go to the group. If no group is linked,
  tapping any option posts nothing and tells the admin to set it
  with `/setgroup` first. After posting, the admin gets a DM
  confirmation ("✅ Posted to the group: Main intro + Fundraiser
  pool").
- The texts live as `MAIN_ANNOUNCEMENT` and `POOL_ANNOUNCEMENT`
  constants in `bot.py` — Arkar's drafts, still awaiting his
  Burmese corrections; edit the constants to change the wording,
  the posting logic stays the same.

**Repeat pool contributions** — members can now put money into
the same pool **more than once**. Every top-up is at least
1,000 Ks and adds to their running total (one contributor entry
per member, `ks` = total across all their contributions). The
join prompt shows a returning contributor their total
("You've put in 6,000 Ks so far — add more?"). The capping rule
still applies to every top-up. On completion the video goes
privately to each contributor **once**; on cancel/remove each
member is refunded their **total**.

## v7.4 — /start answers in the group

Group messages are still silently ignored, except `/id` — but
`/start` in a group now answers with a short pointer instead of
nothing: "👋 Hi! I work in private chat — tap @DaddyTeacherBot
and press Start to make your profile, sell, and join pools."
Matches `/start`, `/start@DaddyTeacherBot`, and `/start` with
arguments; a `/start` addressed to a different bot is still
ignored. All flows still run in the DM only.

## v7.5 — the bot remembers payment details

`/profile` no longer re-asks payment questions when the answer is
already known. Admins get their known accounts (KBZPay, WavePay,
AYAPay, USDT from the bot's constants) filled in automatically and
jump straight to the photos step. Other members reuse the payment
details saved on their profile and also jump straight to photos.
Only a brand-new member with nothing saved is asked. A draft
already sitting in the payment questions is rescued the same way
on the next message. The confirm screen has a fourth button,
"✏️ Change payment details", which re-opens the questions
(`/skip` on a step keeps the saved value).

## v7.6 — reselect profile photos

A saved photo can now be removed mid-flow: at the photos step,
`/clearphotos` clears the draft's saved photos and the set starts
over ("Saved photos cleared — send 3 photos of you, one by one.").
It works with 1, 2 or 3 photos saved and is harmless with 0. The
photos prompts mention the command. The confirm screen has a
"📷 Change photos" button, which goes back to the photos step
with the saved photos still in place — new photos swap the oldest
out once 3 are saved. Appending while fewer than 3 are saved,
the oldest-out swap at 3, and `/skip` at the photos step are all
unchanged.

## v7.7 — edit your profile + 30-minute videos

**Edit profile** — sellers can now change one thing without redoing
the whole flow. `/myprofile` has an "✏️ Edit profile" button, and
`/profile` on an existing profile opens a menu — "What do you want
to change?" — with Name, Age, Role, Products & prices, Payment
details, Photos, and "✅ Done — review profile". Each section jumps
straight there and returns to the menu when finished; Done goes to
the usual confirm screen. Prices show the saved price ("currently
5,000 Ks") and `/skip` keeps it; `/skip` on a product with no price
yet is refused. The age prompt says `/skip` keeps the saved age
when editing. Brand-new profiles keep the exact linear flow as
before, and "✏️ Start over" on the confirm screen still restarts
from the name step.

**Videos up to 30 minutes** — auction and pool videos may now be
1 to 30 minutes long (was 1 to 5). The 1-minute minimum stays, and
the card still shows the length as "⏱️ N min". The auction bidding
window is 24 hours (changed from 15 minutes in v7.10).
Fixed-price `/sell` cards never had a duration limit and are
untouched.

## v7.8 — preview fallback + no more silent videos (bug fix)

**The bug** — in a `/pool` flow, a seller sent a video and the bot
answered nothing: no preview, no error, no log line, and no pool
card in the group. The preview was sent with the video's thumbnail
as a photo, and if Telegram rejected that `sendPhoto`, the failure
was thrown away unnoticed and the draft sat at the confirm step
forever. A re-sent video did not help either.

**The fix** — three changes, all in `bot.py`:
- `api()` now logs every Telegram refusal (`api <method> failed:
  <error_code> <description>`), so a failed call leaves a trace
  in the deploy logs instead of vanishing.
- `send_pool_preview` and `send_auction_preview` check the
  `sendPhoto` result: if it fails, they fall back to the same
  preview as a plain text message with the same Post / Cancel
  buttons. The seller always gets the preview.
- `handle_message` no longer goes silent on a photo, video or
  file that no flow claimed: the sender gets a plain reply
  ("Got your video — but I'm not waiting for one right now.
  Start a pool with /pool, an auction with /auction, or a card
  with /sell."). The net sits after every draft handler, so a
  live draft still answers first, and non-admin receipt photos
  still go to the receipt flow with no double reply.

Nothing else changed: prices, ranges, the 1–30 minute video rule,
profiles, and the announcements are untouched.

## v7.9 — video thumbnails are not photos (bug fix)

**The bug** — v7.8 fixed the silent preview, but tapping "✅ Post
pool" still failed. Telegram said it plainly: "Bad Request: can't
use file of type Thumbnail as Photo". A video's thumbnail file_id
cannot be used as a photo in `sendPhoto` — so every pool and
auction card whose cover was a video thumbnail was rejected at
posting time. (The no-thumb path, where the seller sends a real
cover photo, was never affected, and neither were `/sell` cards,
whose preview photo is a real photo the seller sent.)

**The fix** — one new helper, `send_photo_with_fallback`, used by
`post_pool_to_group`, `post_auction_to_group`,
`send_pool_preview` and `send_auction_preview`:
- try the file_id directly in `sendPhoto` (real photos still post
  on the first attempt, no download);
- if Telegram refuses it, download the file with the existing
  `download_file_bytes` (`getFile` + the file download URL) and
  re-upload the bytes as `cover.jpg`;
- if that fails too, send the caption as a plain text message with
  the same buttons. Only if all three fail does the caller report
  an error — never silence.

The seller now sees the real cover in the preview too, not just a
text fallback. `api()` failure logging and the anti-silence net
from v7.8 are untouched.

Nothing else changed: prices, ranges, the 1–30 minute video rule,
profiles, and the announcements are untouched.

## v7.10 — cover choice per post + adjustable pool amount + 24-hour auctions

**Cover choice at posting** — pools and auctions no longer always
use the video's thumbnail as the cover. After a video with a
thumbnail, the bot asks: "🖼️ Use video thumbnail" or "📷 Send my
own cover photo". The choice is per post, not per product — a
seller can use the thumbnail for one pool and their own photo for
the next. Tapping "Send my own" asks for a cover photo (`/skip`
goes back to the thumbnail); sending a photo straight away without
tapping counts as their own cover too. A video with no thumbnail
still asks for a cover photo, but `/skip` there now posts a text
card with no cover instead of blocking. The preview and the group
post use whatever cover was chosen (thumbnail / own photo / none)
through the v7.9 `send_photo_with_fallback` helper. Fixed-price
`/sell` cards are unchanged — the seller already picks media per
card there.

**Pool amount on the preview** — the pool preview gains a
"💰 Change amount" button. Tapping it asks for the new pool price
(same 50,000–500,000 Ks rule); a valid price updates the draft and
the preview is edited in place (caption for a photo preview, text
for a text preview — a fresh preview is sent if the edit fails).
The preview now shows the draft's real price (it previously always
showed 50,000 Ks). "✅ Post pool" then posts with the new price.

**Pool amount on a live pool** — `/poolinfo <id>` shows a
"💰 Change amount" button, but only to the pool's seller (nobody
else sees it, and a non-seller tap is refused). A valid new price
updates the pool and the group card in place, and the `/poolinfo`
view is refreshed. Lowering the price below what's already raised
fills the pool immediately: the seller is credited the new price,
the video goes privately to every contributor once, and the card
is marked filled — exactly the normal completion flow. Raising the
price just moves the goal further out and updates the meter. A
filled, cancelled or removed pool refuses the change.

**Auctions run 24 hours** (was 15 minutes) — `AUCTION_DURATION_S`
is now 24 hours. The "Ends in" countdown shows hours once an hour
or more is left ("23h 59m", "mm:ss" under an hour). The sweep still
deletes an unsold auction card 24 hours after the auction ended —
`_close_auction` now stamps `ended_at`, and the sweep counts from
that (falling back to the deadline for older records), so the card
is no longer deleted the moment a 24-hour auction ends. All
user-facing "15 minutes" texts (help, prompts, post confirmation)
now say 24 hours.

Nothing else changed: the 50,000–500,000 Ks pool range, the 1,000
Ks minimum contribution, the 1–30 minute video rule, the 5,000 Ks
starting bid, profiles, balances, cash-out, and the announcements
are untouched.

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
drafts, cashouts, sellusdt, cards, card drafts, auctions, auction
drafts, bid drafts), `credits.json`,
`purchases.json` (kinds: `pack`, `market`, `topup`, `cashout`,
`sellusdt`, `auction`; market sales carry an `option` field when bought from a
card option), `used_tx.json`, `users.json`, `profiles.json` (seller
profiles + status; each profile also holds `age`, `role`, `photos`
— 3 file_ids), `balances.json` (user id → balance in Ks). Cards in
`state.json` also hold `age`/`role` (snapshot), `media_type`,
`media_file_id` (full version), `preview_file_id` (blurred) and
`revealed` (false until the first completed purchase). Auctions in
`state.json` hold `video_file_id`, `cover_file_id` (seller-chosen
cover: video thumbnail or own photo, unblurred), `start` (5,000),
`current_bid` / `current_bidder`, `ends_at`, `ended_at`, `posted_at`,
`message_id` and `status`
(`live` / `ended` / `sold` / `expired` / `removed`).
