# Chat GPT Plus API — Web App

Private 1-on-1 GPT chat in the browser, powered by OpenAI. Users get in with
single-use invite links (`https://<host>/i/<CODE>`), chat with the AI co-worker,
and can download Excel/PDF files it builds. On a MacBook the site can be added
to the Dock (Safari → Add to Dock) so it feels like a native app.

## Deploy (Railway)

New service from the `myanmar-bots` repo, root directory `gpt-web`,
plus a volume mounted at `/data`.

| Env var | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `ADMIN_PASSWORD` | ✅ | Password for the `/admin` panel |
| `DATA_DIR` | ✅ | `/data` (volume mount — codes, sessions, usage survive redeploys) |
| `MODEL` | — | OpenAI model id (default: `gpt-6.1-sol`) |
| `INPUT_RATE` | — | $ per 1M input tokens for cost estimates (default: 2.0) |
| `OUTPUT_RATE` | — | $ per 1M output tokens for cost estimates (default: 10.0) |
| `DAILY_LIMIT` | — | Max chat messages per invite code per day (default: 100) |
| `PORT` | — | Listen port (Railway sets this automatically) |

## Features

- **Invite access** — each code works once, then locks to that browser session.
  Share links like `https://<host>/i/AB12CD34` (auto-redeem on open).
- **Chat** — per-session history (last 10 exchanges), typing indicator,
  `/new` fresh starts, Markdown-ish rendering, Myanmar/Thai/English.
- **Files** — ask for a spreadsheet or PDF; the assistant builds it and the
  chat shows a download button (Excel via openpyxl, PDF via fpdf2 with an
  embedded Myanmar font).
- **Image generation** — ask for a picture, logo, or illustration; it appears
  right in the chat with a download button (OpenAI image API, ~$0.04/image,
  tracked per code in the admin panel).
- **File uploads** — attach a photo or document (PDF, TXT, Markdown, CSV);
  the AI reads it and discusses it with you (📎 button in the chat).
- **Cost control** — per-code daily message cap; per-code token + cost tracking.
- **Admin panel** (`/admin`) — generate invite codes, copy invite links,
  see per-code usage and total API cost, revoke access.

## Local dev

```bash
pip install -r requirements.txt
ADMIN_PASSWORD=secret OPENAI_API_KEY=... python app.py
```
