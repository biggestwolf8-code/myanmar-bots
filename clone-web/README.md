# Clone Studio Web

Let people create their own AI clone and generate talking-head videos from a script.

**Flow:** invite code → upload photo + voice sample → "Create My Clone"
(clones voice via ElevenLabs) → type script → "Generate Video"
(TTS now, GPU render queued).

## Setup

```bash
cd clone-web
pip install -r requirements.txt   # flask
export ELEVENLABS_API_KEY="sk_..."       # required — never commit this
export ELEVENLABS_BURMESE_VOICE_ID="..." # optional fallback Burmese voice
export ADMIN_PASSWORD="..."              # required for /admin
export DATA_DIR="/data"                  # Railway volume (default ".")
export PORT=5000
python app.py
```

Railway: set the env vars in the service, add a volume mounted at `/data`,
`DATA_DIR=/data`, Procfile `web: python app.py`.

## How it works

- **Auth:** same invite-code pattern as the other web apps. Admin creates
  codes at `/admin`; users sign in via `/i/<CODE>` auto-redeem links
  (single-use, 90-day session cookie). No signup forms.
- **Clone:** `POST /api/clone` (multipart: `photo`, `voice_en` required,
  `voice_mm` optional, `name`). Calls ElevenLabs `POST /v1/voices/add`
  (Instant Voice Clone) for each sample. Stored per invite code in
  `userclones.json`; uploads under `uploads/<CODE>/`.
- **Video:** `POST /api/video` `{script, voice_id}` → ElevenLabs TTS
  (`eleven_multilingual_v2`) saves `audio_<jobid>.mp3`, then a job is
  appended to `videojobs.json` with status `queued`.
- **Jobs:** `GET /api/jobs` lists the user's jobs; audio downloads at
  `/api/jobs/<id>/audio`; video at `/api/jobs/<id>/video` once done.

## GPU rendering (STUBBED)

`POST /api/video` only does the TTS and queues the job. The actual
talking-head render (EchoMimicV3 on a RunPod GPU pod) is **not wired yet**.
Each queued job in `videojobs.json` carries everything a worker needs:

```json
{ "photo_path": "uploads/<CODE>/photo.png",
  "audio_path": "uploads/<CODE>/audio_<jobid>.mp3",
  "script": "...", "voice_id": "...", "status": "queued" }
```

The worker should: pick up `queued` jobs → flip to `rendering` →
render MP4 (see `../clone-studio/render_job.py` for the pipeline) →
save under `uploads/<CODE>/video_<jobid>.mp4`, set `video_path` +
status `done` (or `failed` + `error`).

## Admin

`/admin` → password login → create/revoke invite codes, see totals
(codes used, clones created, jobs queued).

## Files

- `app.py` — the whole backend (auth, clone, TTS, jobs, admin)
- `templates/index.html` — mobile-friendly user UI
- `templates/admin.html` — admin panel
- `requirements.txt` — flask
- `.env.example` — env var template (no secrets)
