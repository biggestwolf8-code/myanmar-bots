"""Clone Studio Web — let people create their own AI clone and generate
talking-head videos from a script.

Flow:
  1. Sign in with an invite code (/i/<CODE> auto-redeem links).
  2. Onboarding: upload a front-facing photo + a ~30s voice sample
     (English and/or Burmese). "Create My Clone" clones the voice(s)
     via the ElevenLabs API.
  3. Type a script, pick a voice, hit "Generate Video":
       a. Script -> speech MP3 via ElevenLabs TTS (user's cloned voice).
       b. Video render job queued (EchoMimicV3 on RunPod GPU).
         STUB: the GPU renderer is not wired yet — jobs are persisted in
         jobs.json with status "queued" so the renderer can pick them up.

Env vars:
  ELEVENLABS_API_KEY          ElevenLabs API key (required for clone + TTS)
  ELEVENLABS_BURMESE_VOICE_ID Fallback Burmese voice id (optional; used when
                              the user has no Burmese clone of their own)
  ADMIN_PASSWORD              Password for the /admin panel (required)
  DATA_DIR                    Storage dir (default "."; use "/data" with a
                              Railway volume so uploads/codes survive redeploys)
  PORT                        Listen port (default: 5000)

Invite links look like: https://<host>/i/<CODE>  (single use)
Admin panel: https://<host>/admin
"""
import datetime
import io
import json
import mimetypes
import os
import secrets
import urllib.error
import urllib.request
import uuid

from flask import Flask, jsonify, redirect, request, send_file, session, url_for

DATA_DIR = os.environ.get("DATA_DIR", ".")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PORT = int(os.environ.get("PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_BURMESE_VOICE_ID = os.environ.get("ELEVENLABS_BURMESE_VOICE_ID", "").strip()
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".mp4", ".aac", ".flac"}

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))


# ---------- storage ----------

def _load_json(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(name, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = os.path.join(DATA_DIR, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(DATA_DIR, name))


def get_secret_key():
    path = os.path.join(DATA_DIR, "secret.key")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = secrets.token_hex(32)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
        return key


app.secret_key = get_secret_key()
# Invite codes are single-use: keep logins alive 90 days across restarts.
app.permanent_session_lifetime = datetime.timedelta(days=90)

codes = _load_json("clonecodes.json", {})
sessions = _load_json("clonesessions.json", {})
clones = _load_json("userclones.json", {})
jobs = _load_json("videojobs.json", {})

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def save_all():
    _save_json("clonecodes.json", codes)
    _save_json("clonesessions.json", sessions)
    _save_json("userclones.json", clones)
    _save_json("videojobs.json", jobs)


def make_code():
    while True:
        c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        if c not in codes:
            return c


def invite_link(code):
    return request.host_url.rstrip("/") + "/i/" + code


def current_sid():
    sid = session.get("sid")
    if sid and sid in sessions:
        return sid
    return None


def code_for_sid(sid):
    return sessions[sid]["code"]


def is_admin():
    return session.get("admin") is True and ADMIN_PASSWORD


def user_dir(code):
    d = os.path.join(DATA_DIR, "uploads", code)
    os.makedirs(d, exist_ok=True)
    return d


# ---------- ElevenLabs (urllib only, key never logged) ----------

def _api_key():
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY env var is not set.")
    return ELEVENLABS_API_KEY


def _multipart_body(fields, files):
    """fields: {name: str}, files: {name: (filename, bytes, mimetype)}."""
    boundary = "----cloneweb" + secrets.token_hex(16)
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(str(value).encode())
        buf.write(b"\r\n")
    for name, (filename, data, mtype) in files.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        buf.write(f"Content-Type: {mtype}\r\n\r\n".encode())
        buf.write(data)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def elevenlabs_clone_voice(audio_bytes, filename, mimetype, name):
    """Create an Instant Voice Clone. Returns the new voice_id."""
    body, boundary = _multipart_body(
        {"name": name, "description": f"Clone Studio Web clone of {name}"},
        {"files": (filename, audio_bytes, mimetype)},
    )
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices/add",
        data=body,
        headers={
            "xi-api-key": _api_key(),  # header value never logged
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"ElevenLabs clone failed ({e.code}): {detail}")
    vid = data.get("voice_id")
    if not vid:
        raise RuntimeError("ElevenLabs clone failed: no voice_id returned.")
    return vid


def elevenlabs_tts(text, voice_id, out_path):
    """Synthesize text to MP3. Returns out_path."""
    text = (text or "").strip()
    if not text:
        raise RuntimeError("Script text is empty.")
    payload = json.dumps({
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=payload,
        headers={
            "xi-api-key": _api_key(),  # header value never logged
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"ElevenLabs TTS failed ({e.code}): {detail}")
    if not audio or len(audio) < 1024:
        raise RuntimeError("ElevenLabs returned empty/short audio.")
    with open(out_path, "wb") as f:
        f.write(audio)
    return out_path


def available_voices_for(code):
    """Voice options for this user: their clones + fallback Burmese."""
    clone = clones.get(code) or {}
    opts = []
    if clone.get("voice_id_en"):
        opts.append({"id": clone["voice_id_en"], "label": "My English voice 🎙️"})
    if clone.get("voice_id_mm"):
        opts.append({"id": clone["voice_id_mm"], "label": "My Burmese voice 🎙️"})
    elif ELEVENLABS_BURMESE_VOICE_ID:
        opts.append({"id": ELEVENLABS_BURMESE_VOICE_ID, "label": "Burmese voice"})
    return opts


# ---------- pages ----------

@app.route("/")
def index():
    from flask import render_template
    return render_template("index.html", logged_in=bool(current_sid()))


@app.route("/i/<code>")
def redeem_link(code):
    code = (code or "").strip().upper()
    e = codes.get(code)
    if not e or e.get("used_by"):
        from flask import render_template
        return render_template("index.html", logged_in=False,
                               error="This invite link is invalid or already used."), 410
    sid = secrets.token_hex(16)
    e["used_by"] = sid
    e["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    sessions[sid] = {"code": code, "created": e["used_at"]}
    save_all()
    session["sid"] = sid
    session.permanent = True
    return redirect(url_for("index"))


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "clone-web",
                    "elevenlabs": bool(ELEVENLABS_API_KEY)})


@app.route("/api/redeem", methods=["POST"])
def api_redeem():
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    e = codes.get(code)
    if not e:
        return jsonify({"ok": False, "error": "Invalid invite code."}), 404
    if e.get("used_by"):
        return jsonify({"ok": False,
                        "error": "This invite code was already used."}), 410
    sid = secrets.token_hex(16)
    e["used_by"] = sid
    e["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    sessions[sid] = {"code": code, "created": e["used_at"]}
    save_all()
    session["sid"] = sid
    session.permanent = True
    return jsonify({"ok": True})


# ---------- clone API ----------

@app.route("/api/clone", methods=["GET"])
def api_clone_get():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    c = clones.get(code)
    return jsonify({"ok": True, "clone": c,
                    "voices": available_voices_for(code)})


@app.route("/api/clone", methods=["POST"])
def api_clone_create():
    """Multipart: photo (image), voice_en (audio, required), voice_mm
    (audio, optional), name (text). Clones voice(s) via ElevenLabs."""
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    name = (request.form.get("name") or "").strip()[:60] or "My Clone"

    photo = request.files.get("photo")
    if not photo:
        return jsonify({"ok": False, "error": "Upload a front-facing photo."}), 400
    pext = os.path.splitext(photo.filename or "")[1].lower()
    if pext not in PHOTO_EXTS:
        return jsonify({"ok": False,
                        "error": "Photo must be PNG/JPG/WebP."}), 400

    voice_en = request.files.get("voice_en")
    if not voice_en:
        return jsonify({"ok": False,
                        "error": "Upload a ~30s English voice sample."}), 400
    vext = os.path.splitext(voice_en.filename or "")[1].lower()
    if vext not in AUDIO_EXTS:
        return jsonify({"ok": False,
                        "error": "Voice sample must be an audio file (mp3/m4a/wav/ogg)."}), 400

    voice_mm = request.files.get("voice_mm")
    mm_bytes = None
    if voice_mm and voice_mm.filename:
        mext = os.path.splitext(voice_mm.filename or "")[1].lower()
        if mext not in AUDIO_EXTS:
            return jsonify({"ok": False,
                            "error": "Burmese sample must be an audio file."}), 400
        mm_bytes = voice_mm.read(MAX_UPLOAD_BYTES + 1)

    photo_bytes = photo.read(MAX_UPLOAD_BYTES + 1)
    en_bytes = voice_en.read(MAX_UPLOAD_BYTES + 1)
    if len(photo_bytes) > MAX_UPLOAD_BYTES or len(en_bytes) > MAX_UPLOAD_BYTES \
            or (mm_bytes and len(mm_bytes) > MAX_UPLOAD_BYTES):
        return jsonify({"ok": False, "error": "A file is over the 15 MB limit."}), 400

    try:
        vid_en = elevenlabs_clone_voice(
            en_bytes, f"voice_en{vext}",
            mimetypes.guess_type(f"x{vext}")[0] or "audio/mpeg",
            f"{name} (English)")
        vid_mm = None
        if mm_bytes:
            vid_mm = elevenlabs_clone_voice(
                mm_bytes, f"voice_mm{os.path.splitext(voice_mm.filename or '')[1].lower()}",
                mimetypes.guess_type("x" + os.path.splitext(voice_mm.filename or "")[1].lower())[0]
                or "audio/mpeg",
                f"{name} (Burmese)")
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    udir = user_dir(code)
    with open(os.path.join(udir, "photo" + pext), "wb") as f:
        f.write(photo_bytes)
    clones[code] = {
        "name": name,
        "photo_path": os.path.join("uploads", code, "photo" + pext),
        "voice_id_en": vid_en,
        "voice_id_mm": vid_mm,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    save_all()
    return jsonify({"ok": True, "clone": clones[code],
                    "voices": available_voices_for(code)})


@app.route("/api/clone/reset", methods=["POST"])
def api_clone_reset():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    clones.pop(code, None)
    save_all()
    return jsonify({"ok": True})


# ---------- video jobs (GPU render STUBBED) ----------

@app.route("/api/video", methods=["POST"])
def api_video_generate():
    """JSON: {script, voice_id}. TTS now, queue the GPU render job."""
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    clone = clones.get(code)
    if not clone:
        return jsonify({"ok": False,
                        "error": "Create your clone first."}), 400
    data = request.get_json(force=True, silent=True) or {}
    script = (data.get("script") or "").strip()
    voice_id = (data.get("voice_id") or "").strip()
    if not script:
        return jsonify({"ok": False, "error": "Type a script first."}), 400
    allowed = {v["id"] for v in available_voices_for(code)}
    if voice_id not in allowed:
        return jsonify({"ok": False, "error": "Pick one of your voices."}), 400
    if len(script) > 5000:
        return jsonify({"ok": False,
                        "error": "Script is too long (max 5000 characters)."}), 400

    job_id = uuid.uuid4().hex[:12]
    udir = user_dir(code)
    audio_rel = os.path.join("uploads", code, f"audio_{job_id}.mp3")
    audio_abs = os.path.join(DATA_DIR, audio_rel)
    try:
        elevenlabs_tts(script, voice_id, audio_abs)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    # STUB: the RunPod/EchoMimicV3 renderer is not wired yet. The job is
    # persisted with everything the renderer needs (photo + audio + script);
    # a worker will flip status to rendering/done later.
    jobs[job_id] = {
        "id": job_id,
        "code": code,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "script": script[:500],
        "voice_id": voice_id,
        "photo_path": clone["photo_path"],
        "audio_path": audio_rel,
        "video_path": None,
        "status": "queued",
        "note": "GPU renderer not wired yet — job queued for RunPod worker.",
        "error": None,
    }
    save_all()
    return jsonify({"ok": True, "job": jobs[job_id]})


@app.route("/api/jobs", methods=["GET"])
def api_jobs_list():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    mine = [j for j in jobs.values() if j.get("code") == code]
    mine.sort(key=lambda j: j.get("created", ""), reverse=True)
    return jsonify({"ok": True, "jobs": mine})


@app.route("/api/jobs/<job_id>/audio")
def api_job_audio(job_id):
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    j = jobs.get(job_id)
    if not j or j.get("code") != code:
        return jsonify({"ok": False, "error": "Job not found."}), 404
    path = os.path.join(DATA_DIR, j["audio_path"])
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "Audio missing."}), 404
    return send_file(path, mimetype="audio/mpeg",
                     download_name=f"clone-audio-{job_id}.mp3")


@app.route("/api/jobs/<job_id>/video")
def api_job_video(job_id):
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    j = jobs.get(job_id)
    if not j or j.get("code") != code:
        return jsonify({"ok": False, "error": "Job not found."}), 404
    if j.get("status") != "done" or not j.get("video_path"):
        return jsonify({"ok": False,
                        "error": "Video not ready yet — render job is queued."}), 409
    path = os.path.join(DATA_DIR, j["video_path"])
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "Video missing."}), 404
    return send_file(path, mimetype="video/mp4",
                     download_name=f"clone-video-{job_id}.mp4")


@app.route("/api/photo")
def api_photo():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    c = clones.get(code)
    if not c:
        return jsonify({"ok": False, "error": "No clone yet."}), 404
    path = os.path.join(DATA_DIR, c["photo_path"])
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "Photo missing."}), 404
    ext = os.path.splitext(path)[1].lower()
    mime = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    return send_file(path, mimetype=mime)


@app.route("/api/logout", methods=["POST"])
def api_logout():
    sid = current_sid()
    if sid:
        sessions.pop(sid, None)
        save_all()
    session.clear()
    return jsonify({"ok": True})


# ---------- admin ----------

@app.route("/admin")
def admin_page():
    from flask import render_template
    return render_template("admin.html", logged_in=is_admin(),
                           configured=bool(ADMIN_PASSWORD))


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(force=True, silent=True) or {}
    if ADMIN_PASSWORD and data.get("password") == ADMIN_PASSWORD:
        session["admin"] = True
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Wrong password."}), 403


@app.route("/api/admin/data")
def api_admin_data():
    if not is_admin():
        return jsonify({"ok": False}), 403
    rows = []
    for c, e in codes.items():
        cl = clones.get(c)
        njobs = sum(1 for j in jobs.values() if j.get("code") == c)
        rows.append({"code": c, "link": invite_link(c),
                     "used": bool(e.get("used_by")),
                     "created": e.get("created", ""),
                     "has_clone": bool(cl),
                     "clone_name": (cl or {}).get("name", ""),
                     "jobs": njobs})
    rows.sort(key=lambda r: r["created"], reverse=True)
    queued = sum(1 for j in jobs.values() if j.get("status") == "queued")
    return jsonify({"ok": True, "codes": rows,
                    "totals": {"codes": len(codes),
                               "used": sum(1 for e in codes.values() if e.get("used_by")),
                               "clones": len(clones),
                               "jobs": len(jobs),
                               "queued": queued,
                               "active_sessions": len(sessions)}})


@app.route("/api/admin/newcodes", methods=["POST"])
def api_admin_newcodes():
    if not is_admin():
        return jsonify({"ok": False}), 403
    data = request.get_json(force=True, silent=True) or {}
    try:
        n = int(data.get("n", 10))
    except (TypeError, ValueError):
        n = 10
    n = max(1, min(n, 50))
    now = datetime.datetime.now().isoformat(timespec="seconds")
    fresh = []
    for _ in range(n):
        c = make_code()
        codes[c] = {"used_by": None, "created": now, "used_at": None}
        fresh.append({"code": c, "link": invite_link(c)})
    _save_json("clonecodes.json", codes)
    return jsonify({"ok": True, "codes": fresh})


@app.route("/api/admin/revoke", methods=["POST"])
def api_admin_revoke():
    if not is_admin():
        return jsonify({"ok": False}), 403
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    e = codes.get(code)
    if not e:
        return jsonify({"ok": False, "error": "Code not found."}), 404
    sid = e.get("used_by")
    e["used_by"] = None
    e["used_at"] = None
    if sid:
        sessions.pop(sid, None)
    clones.pop(code, None)
    save_all()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
