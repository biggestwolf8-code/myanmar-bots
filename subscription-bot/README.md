# Biggest Seller Myanmar — Telegram catalog bot

Customers browse 80+ subscriptions by category (tap buttons) or type a
product name. Anything the bot can't match is forwarded to the admin, and
the admin's reply is relayed back to the customer.

## Step 1 — Create the bot (2 min, on your phone)

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Display name, e.g. `Biggest Seller Myanmar`.
3. Username ending in `bot`, e.g. `biggest_seller_mm_bot`.
4. BotFather gives you a **token** — keep it private, never paste it in chat.

## Step 2 — Get your Telegram user id

Open **@userinfobot**, send any message — your numeric id is `ADMIN_CHAT_ID`.

## Step 3 — Run it

```bash
cd subscription-bot
pip install -r requirements.txt
BOT_TOKEN=<token> ADMIN_CHAT_ID=<your-id> python bot.py
```

Optional: `CONTACT_USERNAME=@someone` overrides the order contact
(default `@biggestseller1`).

## Biggest VPN app (APK)

The bot ships the Android app, `biggest-vpn.apk` (v3 build, 17 MB), and
sends it two ways:

- **📱 Download the app (APK)** button on the Biggest VPN product page
  — sends the APK to anyone, before buying.
- **With every delivery** (paid order via ✅ Approve & Deliver, and the
  free 7-day trial) — the APK goes out together with the 4 `.conf`
  files, and the welcome message tells Android customers to install the
  app and enter their VPN code. iPhone / Windows / Mac customers use
  the WireGuard steps instead — the app is Android-only.

How the app works (important): it does NOT import `.conf` files and
does NOT scan QR codes. The customer enters their VPN code in the app,
and the app fetches the configs from the **vpn-api** service
(`/api/login`). The vpn-api keeps its own customer store, so the bot
registers every code it issues there right after provisioning
(`POST /api/admin/register` — peers are NOT re-created, the record is
just stored). Renewals and revocations are mirrored the same way.

Required env var on this bot service (in addition to `BOT_TOKEN` /
`ADMIN_CHAT_ID`):

- `VPN_API_ADMIN_SECRET` — must be the SAME value as the vpn-api
  service's `ADMIN_SECRET` env var. Without it, codes are not
  registered: the `.conf` delivery still works, but the app login fails
  and the admin gets a warning message for each affected delivery.
- `VPN_API_BASE` — optional, defaults to
  `https://vpn-api-production-30d3.up.railway.app`.

Note: the app is a WireGuard client for the same 4 servers, so it does
NOT fix the MPT situation — WireGuard is still DPI-blocked on MPT.

## Step 4 — Host it 24/7

Same options as the English bot: Railway/Render (connect repo, background
worker from `Procfile`, set env vars) or a VPS with systemd.

## Updating prices

All products live in `catalog.json` (one entry per plan):
`category / product / plan / price_ks / notes`.
Edit prices or add products there, restart the bot — no code changes needed.
The master spreadsheet is `../subscription-business/subscription-price-list.xlsx`;
`build_catalog.py` there regenerates `full-catalog.json`, which you can copy
over this `catalog.json`.

## How customers use it

- `/start` → category buttons → product buttons → plans & prices
- Or just type `spotify`, `netflix`, `canva`, `vpn`…
- Unknown questions → forwarded to you; reply to the forwarded message and
  the customer gets your answer.

## Receipts & delivery

A customer pays, then sends the receipt screenshot here.

- **Biggest VPN** (tapped Buy first): you get ✅ Approve & Deliver /
  ❌ Decline — approval auto-generates and sends the VPN configs.
- **Chat GPT Plus / Claude AI Pro** (tapped Buy first): approval
  auto-generates and sends the invite code.
- **Every other product**: there is no pending order, so you get
  📦 Deliver product / ❌ Decline with the forwarded receipt.
  Tap 📦 Deliver, type the product name (the bot matches it against
  the catalogue — several matches show as buttons), then send the
  delivery details (account, code, or login info) as your next message
  and the bot sends it to the customer as "Your <product> is ready!".
  `/cancel` aborts the delivery at any point. Pending deliveries live
  in `delivery_pending.json` (one at a time).
