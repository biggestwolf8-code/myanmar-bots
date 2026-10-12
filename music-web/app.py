"""TuneBox — private music streaming web app.

A Spotify-style player for your own audio files. Listeners sign up with
their email + password, then activate an access code (each code grants
listening for a set number of days, like a subscription). They browse the
library, build playlists, and stream. The admin uploads audio and manages
users and access codes.

Env vars:
  ADMIN_PASSWORD  Password for the /admin panel (required)
  DATA_DIR        Storage dir (default "."; use "/data" with a Railway
                  volume so tracks/users/codes/playlists survive redeploys)
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
import time

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   send_file, session)
from werkzeug.security import check_password_hash, generate_password_hash

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
app.permanent_session_lifetime = datetime.timedelta(days=90)

TUNEBOX_VERSION = "3.1"


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

# email(lowercased) -> {"pw": hash, "created": ts, "disabled": bool}
users = _load_json("tbusers.json", {})
# code -> {"label": "", "days": 30, "created": ts, "used_by": email|None,
#          "used_at": ts|None, "expires_at": ts|None}
codes = _load_json("tbcodes.json", {})
# sid -> {"user": email, "created": ts}
sessions = _load_json("tbsessions.json", {})
# tid -> {"title","artist","album","ext","duration","size","uploaded_at","plays"}
tracks = _load_json("tbtracks.json", {})
# email -> [{"id","name","tids":[],"created"}]
playlists = _load_json("tbplaylists.json", {})


def save_all():
    _save_json("tbusers.json", users)
    _save_json("tbcodes.json", codes)
    _save_json("tbsessions.json", sessions)
    _save_json("tbtracks.json", tracks)
    _save_json("tbplaylists.json", playlists)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# simple in-memory brute-force guard: ip -> {"n": fails, "until": ts}
_login_hits = {}


def _rate_limited(ip):
    h = _login_hits.get(ip)
    return bool(h and h["until"] > time.time())


def _rate_hit(ip):
    h = _login_hits.setdefault(ip, {"n": 0, "until": 0})
    h["n"] += 1
    if h["n"] >= 15:
        h["until"] = time.time() + 600
        h["n"] = 0


def _rate_clear(ip):
    _login_hits.pop(ip, None)


def valid_email(email):
    return bool(email) and len(email) <= 120 and EMAIL_RE.match(email)


def current_user():
    sid = session.get("sid")
    if sid and sid in sessions:
        email = sessions[sid].get("user")
        u = users.get(email)
        if u and not u.get("disabled"):
            return email
    return None


def require_listener():
    email = current_user()
    if not email or not has_access(email):
        abort(401)
    return email


def new_session(email):
    sid = secrets.token_hex(16)
    sessions[sid] = {"user": email,
                     "created": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save_all()
    session["sid"] = sid
    session.permanent = True


CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def make_code():
    while True:
        c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        if c not in codes:
            return c


def invite_link(code):
    return request.host_url.rstrip("/") + "/i/" + code


def access_until(email):
    """Latest expiry of any code redeemed by this account (None if none)."""
    best = None
    for e in codes.values():
        if e.get("used_by") == email and e.get("expires_at"):
            if best is None or e["expires_at"] > best:
                best = e["expires_at"]
    return best


def has_access(email):
    au = access_until(email)
    return bool(au and au > datetime.datetime.now(datetime.timezone.utc).isoformat())


def redeem_code(email, code):
    """Attach a code to an account, extending access. Returns (ok, message)."""
    code = (code or "").strip().upper()
    e = codes.get(code)
    if not e:
        return False, "That code doesn't exist."
    if e.get("used_by") and e["used_by"] != email:
        return False, "This code was already used by another account."
    now = datetime.datetime.now(datetime.timezone.utc)
    au = access_until(email)
    start_iso = au if au and au > now.isoformat() else now.isoformat()
    start_dt = datetime.datetime.fromisoformat(start_iso)
    e["used_by"] = email
    e["used_at"] = now.isoformat()
    e["expires_at"] = (start_dt + datetime.timedelta(days=int(e.get("days") or 30))).isoformat()
    save_all()
    return True, ""


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
    email = current_user()
    if not email:
        return render_template("login.html", app_name="TuneBox", mode="login")
    if not has_access(email):
        return render_template("redeem.html", app_name="TuneBox",
                               email=email, expired=bool(access_until(email)))
    return render_template("index.html", app_name="TuneBox")


@app.route("/i/<code>")
def redeem(code):
    from flask import render_template
    code = (code or "").strip().upper()
    if not codes.get(code):
        return render_template("login.html", app_name="TuneBox", mode="login",
                               error="That code doesn't exist."), 404
    email = current_user()
    if email:
        ok, msg = redeem_code(email, code)
        if not ok:
            return render_template("redeem.html", app_name="TuneBox",
                                   email=email, expired=bool(access_until(email)),
                                   error=msg), 403
        return redirect("/")
    session["pending_code"] = code
    return render_template("login.html", app_name="TuneBox", mode="login",
                           note="Sign in or create an account to activate your code.")


@app.route("/redeem", methods=["POST"])
def redeem_post():
    from flask import render_template
    email = current_user()
    if not email:
        return redirect("/")
    ok, msg = redeem_code(email, request.form.get("code"))
    if not ok:
        return render_template("redeem.html", app_name="TuneBox",
                               email=email, expired=bool(access_until(email)),
                               error=msg), 403
    return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    from flask import render_template
    if current_user():
        return redirect("/")
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _rate_limited(ip):
            return render_template("login.html", app_name="TuneBox", mode="login",
                                   error="Too many attempts — try again in a few minutes."), 429
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        u = users.get(email)
        if not u or u.get("disabled") or not check_password_hash(u["pw"], pw):
            _rate_hit(ip)
            return render_template("login.html", app_name="TuneBox", mode="login",
                                   error="Wrong email or password."), 401
        _rate_clear(ip)
        new_session(email)
        pc = session.pop("pending_code", None)
        if pc:
            redeem_code(email, pc)  # best effort; failures surface on the redeem page
        return redirect("/")
    return render_template("login.html", app_name="TuneBox", mode="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    from flask import render_template
    if current_user():
        return redirect("/")
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _rate_limited(ip):
            return render_template("login.html", app_name="TuneBox", mode="register",
                                   error="Too many attempts — try again in a few minutes."), 429
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        if not valid_email(email):
            return render_template("login.html", app_name="TuneBox", mode="register",
                                   error="Please enter a valid email address."), 400
        if len(pw) < 6:
            return render_template("login.html", app_name="TuneBox", mode="register",
                                   error="Password needs at least 6 characters."), 400
        if email in users:
            _rate_hit(ip)
            return render_template("login.html", app_name="TuneBox", mode="register",
                                   error="This email already has an account — sign in instead."), 400
        users[email] = {"pw": generate_password_hash(pw),
                        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "disabled": False}
        _rate_clear(ip)
        new_session(email)
        pc = session.pop("pending_code", None)
        if pc:
            redeem_code(email, pc)  # best effort; failures surface on the redeem page
        return redirect("/")
    return render_template("login.html", app_name="TuneBox", mode="register")


@app.route("/logout")
def logout():
    sid = session.pop("sid", None)
    if sid and sid in sessions:
        sessions.pop(sid, None)
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
    email = require_listener()
    name = (request.json.get("name") or "").strip()[:60] or "New playlist"
    pls = playlists.setdefault(email, [])
    pid = secrets.token_hex(6)
    pls.append({"id": pid, "name": name, "tids": [],
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save_all()
    return jsonify({"ok": True, "id": pid, "name": name})


@app.route("/api/playlists/<pid>")
def api_playlist_get(pid):
    email = require_listener()
    for p in playlists.get(email, []):
        if p["id"] == pid:
            items = [public_track(tid, tracks[tid]) for tid in p["tids"]
                     if tid in tracks]
            return jsonify({"id": pid, "name": p["name"], "tracks": items})
    abort(404)


@app.route("/api/playlists/<pid>", methods=["DELETE"])
def api_playlist_delete(pid):
    email = require_listener()
    pls = playlists.get(email, [])
    playlists[email] = [p for p in pls if p["id"] != pid]
    save_all()
    return jsonify({"ok": True})


@app.route("/api/playlists/<pid>/tracks", methods=["POST"])
def api_playlist_add(pid):
    email = require_listener()
    tid = (request.json.get("track_id") or "")
    if tid not in tracks:
        abort(404)
    for p in playlists.get(email, []):
        if p["id"] == pid:
            if tid not in p["tids"]:
                p["tids"].append(tid)
                save_all()
            return jsonify({"ok": True, "count": len(p["tids"])})
    abort(404)


@app.route("/api/playlists/<pid>/tracks/<tid>", methods=["DELETE"])
def api_playlist_remove(pid, tid):
    email = require_listener()
    for p in playlists.get(email, []):
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
    okmsg = None
    if request.args.get("ok"):
        okmsg = request.args["ok"] + " track(s) uploaded ✓"
        if request.args.get("bad"):
            okmsg += " (" + request.args["bad"] + " skipped — not audio)"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return render_template(
        "admin.html", need_login=False, errmsg=errmsg, okmsg=okmsg,
        reset_email=request.args.get("reset_email"),
        reset_pw=request.args.get("reset_pw"),
        track_list=[(tid, public_track(tid, t), t.get("uploaded_at", ""))
                    for tid, t in sorted(tracks.items(),
                                         key=lambda kv: kv[1]["title"].lower())],
        user_list=[(email, u.get("created", "")[:16].replace("T", " "),
                    len(playlists.get(email, [])), bool(u.get("disabled")),
                    (access_until(email) or "")[:10])
                   for email, u in sorted(users.items())],
        code_list=[(c, e.get("label", ""), e.get("days", 30),
                    e.get("used_by"), (e.get("expires_at") or "")[:10],
                    invite_link(c)) for c, e in sorted(codes.items())],
        stats={"tracks": len(tracks), "plays": total_plays,
               "users": len(users),
               "codes": len(codes),
               "active_codes": sum(1 for e in codes.values()
                                  if e.get("used_by") and (e.get("expires_at") or "") > now_iso)},
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
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return redirect("/admin?err=nofile")
    title = (request.form.get("title") or "").strip()
    artist = (request.form.get("artist") or "").strip()[:120] or "Unknown artist"
    album = (request.form.get("album") or "").strip()[:120]
    os.makedirs(TRACKS_DIR, exist_ok=True)
    ok, bad = 0, 0
    for f in files:
        # a typed title only applies when uploading a single file
        if _ingest_upload(f, title if len(files) == 1 else "", artist, album):
            ok += 1
        else:
            bad += 1
    save_all()
    if ok == 0:
        return redirect("/admin?err=notaudio")
    url = "/admin?ok=" + str(ok)
    if bad:
        url += "&bad=" + str(bad)
    return redirect(url)


def _ingest_upload(f, title, artist, album):
    """Validate and store one uploaded file. Returns True on success."""
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
        return False

    duration = int(getattr(audio.info, "length", 0) or 0)
    ext = _upload_ext(f, audio)
    tid = secrets.token_hex(8)
    filename = tid + "." + ext
    path = os.path.join(TRACKS_DIR, filename)
    os.replace(tmp, path)

    if not title:
        title = os.path.splitext(f.filename)[0][:120] or "Untitled"

    tracks[tid] = {"title": title[:120], "artist": artist, "album": album,
                   "ext": ext, "file": filename,
                   "duration": duration,
                   "size": os.path.getsize(path),
                   "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()[:16].replace("T", " "),
                   "plays": 0}
    return True


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
    days = max(1, min(3650, int(request.form.get("days") or 30)))
    label = (request.form.get("label") or "").strip()[:60]
    for _ in range(n):
        c = make_code()
        codes[c] = {"label": label, "days": days,
                    "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "used_by": None, "used_at": None, "expires_at": None}
    save_all()
    return redirect("/admin")


@app.route("/admin/revoke/<code>", methods=["POST"])
def admin_revoke(code):
    if not admin_ok():
        abort(403)
    codes.pop((code or "").strip().upper(), None)
    save_all()
    return redirect("/admin")


@app.route("/api/me")
def api_me():
    email = require_listener()
    au = access_until(email) or ""
    return jsonify({"email": email, "access_until": au[:10] if au else ""})


@app.route("/admin/users/reset", methods=["POST"])
def admin_user_reset():
    if not admin_ok():
        abort(403)
    email = (request.form.get("email") or "").strip().lower()
    u = users.get(email)
    if not u:
        return redirect("/admin")
    new_pw = secrets.token_urlsafe(9)
    u["pw"] = generate_password_hash(new_pw)
    # force re-login everywhere
    for sid in [s for s, e in sessions.items() if e.get("user") == email]:
        sessions.pop(sid, None)
    save_all()
    return redirect(f"/admin?reset_email={email}&reset_pw={new_pw}")


@app.route("/admin/users/toggle", methods=["POST"])
def admin_user_toggle():
    if not admin_ok():
        abort(403)
    email = (request.form.get("email") or "").strip().lower()
    u = users.get(email)
    if u:
        u["disabled"] = not u.get("disabled")
        if u["disabled"]:
            for sid in [s for s, e in sessions.items() if e.get("user") == email]:
                sessions.pop(sid, None)
        save_all()
    return redirect("/admin")


@app.route("/admin/users/delete", methods=["POST"])
def admin_user_delete():
    if not admin_ok():
        abort(403)
    email = (request.form.get("email") or "").strip().lower()
    if email in users:
        users.pop(email, None)
        playlists.pop(email, None)
        for sid in [s for s, e in sessions.items() if e.get("user") == email]:
            sessions.pop(sid, None)
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
