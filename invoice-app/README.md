# Invoice Maker

Simple invoices, estimates & receipts — a mobile-first Flask web app.

Create invoices, estimates and receipts with line items, discounts, tax and
shipping; track clients, catalog items and expenses; download professional
PDFs (with Myanmar, Thai and Latin font support); share documents via public
links; and manage everything from a phone-friendly interface with Invoices,
Estimates, Expenses, Reports and More tabs.

## Features

- Email + password accounts, gated by single-use invite codes (`/i/<CODE>`
  auto-redeem links, like music-web)
- Documents: invoices, estimates, receipts — auto-numbered per type
  (`INV0001`, `EST0001`, `REC0001`; prefix + next number configurable)
- Document actions: edit, duplicate, convert estimate → invoice,
  mark sent/paid/accepted/declined, delete, public share link (`/s/<token>`)
  with WhatsApp + email share
- PDF download (fpdf2) with Noto Sans + Noto Sans Thai + Padauk fallback
  fonts and HarfBuzz text shaping — no tofu boxes for Myanmar/Thai text
- Clients, items catalog, expenses CRUD
- Recurring invoices: pick a template, auto-generate a monthly draft
- Reports: totals by month, paid vs outstanding
- Settings: business details + logo upload, 3 template colors,
  payment methods, default tax, default notes, numbering, email message
  template, region (currency MMK/THB/USD, date format DD-MM-YYYY),
  signature pad, CSV exports, JSON backup
- Admin panel at `/admin` (ADMIN_PASSWORD): create/revoke invite codes,
  list users with document counts, delete users

## Env vars

| Var | Required | Description |
|---|---|---|
| `ADMIN_PASSWORD` | yes | Password for the `/admin` panel |
| `DATA_DIR` | no | Storage dir (default `.`; use `/data` with a Railway volume) |
| `PORT` | no | Listen port (default `5000`) |

## Run locally

```bash
cd invoice-app
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ADMIN_PASSWORD=secret DATA_DIR=./data .venv/bin/python app.py
```

Then open http://localhost:5000 — create an invite code at `/admin`,
register via the `/i/<CODE>` link, and fill in business details under
Settings.

## Deploy (Railway)

New service from the repo, root directory `invoice-app`, plus a volume
mounted at `/data`, with `DATA_DIR=/data` and `ADMIN_PASSWORD` set.
`Procfile`: `web: python app.py`. Health check: `/healthz`.
