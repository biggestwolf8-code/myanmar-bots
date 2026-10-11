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
