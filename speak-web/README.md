# MasterClass Articulation

Bitesy-style English **articulation** practice web app for Myanmar learners —
bite-sized lessons, tap-to-speak practice with per-sound feedback, and a free-talk
voice mode. Mobile-first; works in any phone browser.

**Pipeline:** browser-recorded audio → Whisper transcription → gpt-4o-mini
articulation feedback (which *sounds* were off, with mouth/tongue/lip placement
tips, bilingual EN + မြန်မာ) → phone speech synthesis for tutor replies.
Phrase model audio is generated once via OpenAI TTS and cached.

## Run locally

```bash
cd speak-web
pip install -r requirements.txt
export OPENAI_API_KEY=...     # required for voice features
export ADMIN_PASSWORD=...     # required for /admin
export DATA_DIR=/data         # on Railway (volume); default "." locally
python app.py                 # http://localhost:5000
```

## Deploy (Railway)

New service from the `myanmar-bots` repo, root directory `speak-web`.
Mount a volume at `/data` and set env vars:

| Var | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI key (same one gpt-web / live-translate use) |
| `ADMIN_PASSWORD` | Password for `/admin` |
| `DATA_DIR` | `/data` (volume mount — codes, progress, cached TTS audio) |
| `APP_NAME` | Display name (default `MasterClass Articulation`) |
| `DAILY_LIMIT` | Voice turns per code per day (default 100) |
| `DAILY_COST_LIMIT` | $ per code per day (default 2.0) |
| `MODEL` | Chat model (default `gpt-4o-mini`) |

## Access

Invite codes only — no signup forms. Admin generates codes at `/admin`;
students open `https://<host>/i/<CODE>` (single-use; the link is the credential,
login lasts 90 days).

## Layout

- `app.py` — Flask app, SQLite storage (`speak.db` in `DATA_DIR`), all routes/APIs
- `brain.py` — OpenAI calls: Whisper, articulation feedback, free-talk tutor, TTS
- `lessons.json` — lesson library (A1/A2/B1 topics + Sounds drills); admin edits
  are stored as overrides in the DB
- `templates/` — mobile-first pages: home, lesson practice, free talk, admin
- `static/` — (empty; reserved)

## Honest bits

- Footer on every page: "Powered by OpenAI".
- No dark patterns: invite codes are the only gate, daily caps are disclosed in
  the admin panel, students can see nothing is charged silently.
- Burmese copy in `lessons.json` + UI strings: drafted by AI, **must be verified
  by a native speaker (Arkar) before students see it**.
