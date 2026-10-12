"""TuneBox — private music streaming web app.

A Spotify-style player for your own audio files. Listeners get in with
invite codes (share links like https://<host>/i/<CODE>), browse the library,
build playlists, and stream. The admin uploads MP3s and manages codes.

Env vars:
  ADMIN_PASSWORD  Password for the /admin panel (required)
  DATA_DIR        Storage dir (default "."; use "/data" with a Railway
                  volume so tracks/codes/playlists survive redeploys)
  PORT            Listen port (default: 5000)
  MAX_UPLOAD_MB   Max upload size in MB (default: 300)

Deploy (Railway): new service from the myanmar-bots repo, root directory
`music-web`, plus a volume mounted at `/data`, DATA_DIR=/data.
"""
import datetime
import mimetypes
import os
import re
import secrets

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   send_file, session)

DATA_DIR = os.environ.get("DATA_DIR", ".")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PORT = int(os.environ.get("PORT", "5000"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "300"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACKS_DIR = os.path.join(DATA_DIR, "tracks")
ALLOWED_EXTS = {"mp3", "m4a", "aac", "ogg", "oga", "wav", "flac", "opus", "mp4"}
# MIME -> extension, used when the uploaded filename has no usable extension
# (common when picking files from iOS).
EXT_BY_MIME = {
    "audio/mpeg": "mp3", "audio/mp3": "mp3",
    "audio/mp4": "m4a", "audio/x-m4a": "m4a",
    "audio/aac": "aac", "audio/aacp": "aac",
    "audio/ogg": "ogg", "audio/opus": "opus",
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/flac": "flac", "audio/x-flac": "flac",
    "video/mp4": "mp4",
}


def _upload_ext(f, audio):
    """Pick a file extension: trusted filename first, then MIME hints."""
    name = (f.filename or "")
    if "." in name:
        e = name.rsplit(".", 1)[-1].lower()
        if e in ALLOWED_EXTS:
            return e
    for src in (f.mimetype or "",
                (audio.mime[0] if getattr(audio, "mime", None) else "")):
        m = src.split(";")[0].strip().lower()
        if m in EXT_BY_MIME:
            return EXT_BY_MIME[m]
    return "mp3"

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

TUNEBOX_VERSION = "1.5"


# ---------------------------------------------------------------- storage

def _load_json(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return json_load(f)
    except (FileNotFoundError, ValueError):
        return default


def json_load(f):
    import json
    return json.load(f)


def _save_json(name, data):
    import json
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

# code -> {"used_by": sid|None, "label": "", "created": ts, "used_at": ts|None}
codes = _load_json("tbcodes.json", {})
# sid -> {"code": code, "created": ts}
sessions = _load_json("tbsessions.json", {})
# tid -> {"title","artist","album","ext","duration","size","uploaded_at","plays"}
tracks = _load_json("tbtracks.json", {})
# sid -> [{"id","name","tids":[],"created"}]
playlists = _load_json("tbplaylists.json", {})

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def save_all():
    _save_json("tbcodes.json", codes)
    _save_json("tbsessions.json", sessions)
    _save_json("tbtracks.json", tracks)
    _save_json("tbplaylists.json", playlists)


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


def require_listener():
    sid = current_sid()
    if not sid:
        abort(401)
    return sid


def track_path(t):
    return os.path.join(TRACKS_DIR, t["file"])


def public_track(tid, t):
    return {"id": tid, "title": t["title"], "artist": t["artist"],
            "album": t["album"], "duration": t.get("duration", 0),
            "plays": t.get("plays", 0)}


# ----------------------------------------------------------------- pages

@app.route("/")
def home():
    from flask import render_template
    if not current_sid():
        return render_template("login.html", app_name="TuneBox")
    return render_template("index.html", app_name="TuneBox")


@app.route("/i/<code>")
def redeem(code):
    code = code.strip().upper()
    e = codes.get(code)
    if not e:
        from flask import render_template
        return render_template("login.html", app_name="TuneBox",
                               error="That invite code doesn't exist."), 404
    if e.get("used_by") and e["used_by"] not in sessions:
        e["used_by"] = None  # stale lock, free it
    if e.get("used_by"):
        from flask import render_template
        return render_template("login.html", app_name="TuneBox",
                               error="This invite link was already used."), 403
    sid = secrets.token_hex(16)
    sessions[sid] = {"code": code, "created": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    e["used_by"] = sid
    e["used_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_all()
    session["sid"] = sid
    return redirect("/")


@app.route("/login", methods=["POST"])
def login():
    code = (request.form.get("code") or "").strip().upper()
    return redeem(code)


@app.route("/logout")
def logout():
    sid = session.pop("sid", None)
    if sid and sid in sessions:
        code = sessions[sid].get("code")
        if code and codes.get(code, {}).get("used_by") == sid:
            codes[code]["used_by"] = None
        sessions.pop(sid, None)
        playlists.pop(sid, None)
        save_all()
    return redirect("/")


# -------------------------------------------------------------- library API

@app.route("/api/tracks")
def api_tracks():
    require_listener()
    q = (request.args.get("q") or "").lower()
    out = []
    for tid, t in tracks.items():
        if q and q not in (t["title"] + " " + t["artist"] + " " + t["album"]).lower():
            continue
        out.append(public_track(tid, t))
    out.sort(key=lambda x: x["title"].lower())
    return jsonify({"tracks": out, "count": len(tracks)})


@app.route("/api/stream/<tid>")
def api_stream(tid):
    require_listener()
    t = tracks.get(tid)
    if not t:
        abort(404)
    path = track_path(t)
    if not os.path.isfile(path):
        abort(404)
    mime = mimetypes.guess_type("x." + t["ext"])[0] or "audio/mpeg"
    size = os.path.getsize(path)
    range_header = request.headers.get("Range")

    if not range_header:
        return send_file(path, mimetype=mime, conditional=True)

    m = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
    if not m:
        abort(416)
    s, e = m.groups()
    try:
        start = int(s) if s else 0
        end = int(e) if e else size - 1
    except ValueError:
        abort(416)
    if start >= size:
        abort(416)
    end = min(end, size - 1)
    length = end - start + 1

    def generate():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    rv = Response(generate(), status=206, mimetype=mime,
                  direct_passthrough=True)
    rv.headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
    rv.headers["Content-Length"] = str(length)
    rv.headers["Accept-Ranges"] = "bytes"
    return rv


@app.route("/api/played/<tid>", methods=["POST"])
def api_played(tid):
    require_listener()
    t = tracks.get(tid)
    if not t:
        abort(404)
    t["plays"] = t.get("plays", 0) + 1
    _save_json("tbtracks.json", tracks)
    return jsonify({"ok": True, "plays": t["plays"]})


# ------------------------------------------------------------ playlists API

@app.route("/api/playlists")
def api_playlists():
    sid = require_listener()
    pls = playlists.get(sid, [])
    return jsonify({"playlists": [
        {"id": p["id"], "name": p["name"], "count": len(p["tids"])} for p in pls]})


@app.route("/api/playlists", methods=["POST"])
def api_playlist_create():
    sid = require_listener()
    name = (request.json.get("name") or "").strip()[:60] or "New playlist"
    pls = playlists.setdefault(sid, [])
    pid = secrets.token_hex(6)
    pls.append({"id": pid, "name": name, "tids": [],
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save_all()
    return jsonify({"ok": True, "id": pid, "name": name})


@app.route("/api/playlists/<pid>")
def api_playlist_get(pid):
    sid = require_listener()
    for p in playlists.get(sid, []):
        if p["id"] == pid:
            items = [public_track(tid, tracks[tid]) for tid in p["tids"]
                     if tid in tracks]
            return jsonify({"id": pid, "name": p["name"], "tracks": items})
    abort(404)


@app.route("/api/playlists/<pid>", methods=["DELETE"])
def api_playlist_delete(pid):
    sid = require_listener()
    pls = playlists.get(sid, [])
    playlists[sid] = [p for p in pls if p["id"] != pid]
    save_all()
    return jsonify({"ok": True})


@app.route("/api/playlists/<pid>/tracks", methods=["POST"])
def api_playlist_add(pid):
    sid = require_listener()
    tid = (request.json.get("track_id") or "")
    if tid not in tracks:
        abort(404)
    for p in playlists.get(sid, []):
        if p["id"] == pid:
            if tid not in p["tids"]:
                p["tids"].append(tid)
                save_all()
            return jsonify({"ok": True, "count": len(p["tids"])})
    abort(404)


@app.route("/api/playlists/<pid>/tracks/<tid>", methods=["DELETE"])
def api_playlist_remove(pid, tid):
    sid = require_listener()
    for p in playlists.get(sid, []):
        if p["id"] == pid:
            p["tids"] = [x for x in p["tids"] if x != tid]
            save_all()
            return jsonify({"ok": True})
    abort(404)


# ------------------------------------------------------------------ admin

def admin_ok():
    return session.get("admin") is True


@app.route("/admin", methods=["GET", "POST"])
def admin():
    from flask import render_template
    if request.method == "POST":
        if (request.form.get("password") or "") == ADMIN_PASSWORD and ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        return render_template("admin.html", need_login=True,
                               error="Wrong password."), 403
    if not admin_ok():
        return render_template("admin.html", need_login=True)
    total_plays = sum(t.get("plays", 0) for t in tracks.values())
    top = sorted(tracks.items(), key=lambda kv: kv[1].get("plays", 0),
                 reverse=True)[:10]
    err = request.args.get("err")
    errmsg = {"notaudio": "That file couldn't be read as audio. Please choose an MP3, M4A, MP4, WAV, FLAC or OGG file.",
              "nofile": "No file was chosen — please pick a file first."}.get(err)
    return render_template(
        "admin.html", need_login=False, errmsg=errmsg,
        track_list=[(tid, public_track(tid, t), t.get("uploaded_at", ""))
                    for tid, t in sorted(tracks.items(),
                                         key=lambda kv: kv[1]["title"].lower())],
        code_list=[(c, e.get("label", ""), bool(e.get("used_by")),
                    invite_link(c)) for c, e in sorted(codes.items())],
        stats={"tracks": len(tracks), "plays": total_plays,
               "codes": len(codes),
               "used_codes": sum(1 for e in codes.values() if e.get("used_by"))},
        top=[(tid, t["title"], t["artist"], t.get("plays", 0)) for tid, t in top],
        max_mb=MAX_UPLOAD_MB)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    if not admin_ok():
        abort(403)
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect("/admin?err=nofile")
    # Save first, then validate the actual content (not just the extension):
    # phones often send audio files with missing or odd filenames.
    os.makedirs(TRACKS_DIR, exist_ok=True)
    tmp = os.path.join(TRACKS_DIR, ".tmp_" + secrets.token_hex(8))
    f.save(tmp)
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(tmp)
        ok = audio is not None and getattr(audio, "info", None)
    except Exception:
        ok = False
        audio = None
    if not ok:
        print(f"upload rejected (not audio): filename={f.filename!r} "
              f"mimetype={f.mimetype!r}", flush=True)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return redirect("/admin?err=notaudio")

    duration = int(getattr(audio.info, "length", 0) or 0)
    ext = _upload_ext(f, audio)
    tid = secrets.token_hex(8)
    filename = tid + "." + ext
    path = os.path.join(TRACKS_DIR, filename)
    os.replace(tmp, path)

    title = (request.form.get("title") or "").strip()
    if not title:
        title = os.path.splitext(f.filename)[0][:120] or "Untitled"
    artist = (request.form.get("artist") or "").strip()[:120] or "Unknown artist"
    album = (request.form.get("album") or "").strip()[:120]

    tracks[tid] = {"title": title[:120], "artist": artist, "album": album,
                   "ext": ext, "file": filename,
                   "duration": duration,
                   "size": os.path.getsize(path),
                   "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()[:16].replace("T", " "),
                   "plays": 0}
    save_all()
    return redirect("/admin")


@app.route("/admin/delete/<tid>", methods=["POST"])
def admin_delete(tid):
    if not admin_ok():
        abort(403)
    t = tracks.pop(tid, None)
    if t:
        try:
            os.remove(track_path(t))
        except OSError:
            pass
        for pls in playlists.values():
            for p in pls:
                if tid in p["tids"]:
                    p["tids"].remove(tid)
        save_all()
    return redirect("/admin")


@app.route("/admin/codes", methods=["POST"])
def admin_codes():
    if not admin_ok():
        abort(403)
    n = max(1, min(100, int(request.form.get("n") or 1)))
    label = (request.form.get("label") or "").strip()[:60]
    made = []
    for _ in range(n):
        c = make_code()
        codes[c] = {"used_by": None, "label": label,
                    "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "used_at": None}
        made.append(c)
    save_all()
    return redirect("/admin")


@app.route("/admin/revoke/<code>", methods=["POST"])
def admin_revoke(code):
    if not admin_ok():
        abort(403)
    e = codes.pop(code, None)
    if e and e.get("used_by") in sessions:
        sessions.pop(e["used_by"], None)
    save_all()
    return redirect("/admin")


@app.route("/sw.js")
def sw():
    rv = send_file(os.path.join(BASE_DIR, "static", "sw.js"),
                   mimetype="application/javascript")
    rv.headers["Service-Worker-Allowed"] = "/"
    rv.headers["Cache-Control"] = "no-cache"
    return rv


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "version": TUNEBOX_VERSION,
                    "tracks": len(tracks)})


if __name__ == "__main__":
    if not ADMIN_PASSWORD:
        print("WARNING: ADMIN_PASSWORD is not set — /admin will stay locked.")
    app.run(host="0.0.0.0", port=PORT)
