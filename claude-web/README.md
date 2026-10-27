# Claude Coworker — Web App

Private 1-on-1 Claude chat in the browser. Users get in with single-use
invite links (`https://<host>/i/<CODE>`), chat with Claude (Sonnet by default),
and can download Excel/PDF files the assistant builds. On a MacBook the site
can be added to the Dock (Safari → Add to Dock) so it feels like a native app.

## Deploy (Railway)

New service from the `myanmar-bots` repo, root directory `claude-web`,
plus a volume mounted at `/data`.

| Env var | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `ADMIN_PASSWORD` | ✅ | Password for the `/admin` panel |
| `DATA_DIR` | ✅ | `/data` (volume mount — codes, sessions, usage survive redeploys) |
| `MODEL` | — | Claude model id (default: `claude-sonnet-5-5`) |
| `DAILY_LIMIT` | — | Max chat messages per invite code per day (default: 100) |
| `PORT` | — | Listen port (Railway sets this automatically) |

## Features

- **Invite access** — each code works once, then locks to that browser session.
  Share links like `https://<host>/i/AB12CD34` (auto-redeem on open).
- **Chat** — per-session history (last 10 exchanges), typing indicator,
  `/new` fresh starts, Markdown-ish rendering, Myanmar/Thai/English.
- **Files** — ask for a spreadsheet, PDF, or PowerPoint; the assistant builds it and the
  chat shows a download button (Excel via openpyxl, PDF via fpdf2 with an
  embedded Myanmar font, PowerPoint via python-pptx — first line is the presentation
  title, then each slide starts with `## Slide title` followed by `- ` bullets).
- **Cost control** — per-code daily message cap; per-code token + cost tracking.
- **Admin panel** (`/admin`) — generate invite codes, copy invite links,
  see per-code usage and total API cost, revoke access.

## Local dev

```bash
pip install -r requirements.txt
ADMIN_PASSWORD=secret ANTHROPIC_API_KEY=... python app.py
```
