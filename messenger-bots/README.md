# Messenger bots

Webhook versions of the two Telegram bots, for Facebook Pages:

| Webhook path            | Business                | Brain (same as Telegram twin)              |
|-------------------------|-------------------------|--------------------------------------------|
| `/webhook/english`      | MasterClass English     | FAQ answers (`data/faq.json`)              |
| `/webhook/subscription` | Biggest Seller Myanmar  | Catalog search (`data/catalog.json`) + FAQ |

Features: quick-reply buttons (categories / products / FAQ topics), product
search, payment/warranty/reseller answers, receipt-photo forwarding to the
admin, and admin reply-back relay (admin uses Messenger's reply/quote on the
forwarded message).

`data/` is a copy of the Telegram bots' data — after any price/FAQ change,
run `python3 sync_data.py` to re-sync.

## What you need from Meta

1. **A Facebook Page you admin** (one per bot).
2. **Meta developer app**: https://developers.facebook.com → *Create App* →
   add the **Messenger** product.
3. **Page access token**: in the Messenger settings, connect the Page and
   generate a token. Set it as `PAGE_TOKEN_ENGLISH` / `PAGE_TOKEN_SUBSCRIPTION`.
4. **Webhook**: callback URL `https://<your-host>/webhook/english` (and
   `/webhook/subscription`), verify token = the value you set in
   `VERIFY_TOKEN_ENGLISH` / `VERIFY_TOKEN_SUBSCRIPTION` (any random string).
   Subscribe to the `messages` field.
5. **Admin PSID**: message the Page once from the admin's Facebook account,
   then find their page-scoped ID (it appears in the webhook log as the
   sender id). Set `ADMIN_PSID_ENGLISH` / `ADMIN_PSID_SUBSCRIPTION`.
6. **App review**: to reply to the public (not just testers), request the
   `pages_messaging` permission — Meta reviews it, takes a few days, and
   requires a privacy policy URL.

## Run

```bash
pip install -r requirements.txt
export VERIFY_TOKEN_ENGLISH=...  PAGE_TOKEN_ENGLISH=...  ADMIN_PSID_ENGLISH=...
export VERIFY_TOKEN_SUBSCRIPTION=...  PAGE_TOKEN_SUBSCRIPTION=...  ADMIN_PSID_SUBSCRIPTION=...
python app.py   # listens on $PORT (default 5000)
```

Needs a public HTTPS URL (Railway/Render/VPS) — Meta won't call webhooks on
localhost. The same host that runs the Telegram bots can run this.
