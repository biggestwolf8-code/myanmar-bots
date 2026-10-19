"""Claude AI Pro web app.

Private 1-on-1 Claude chat in the browser. Invite-code access (like the
Telegram bot), per-code daily caps, Excel/PDF file downloads, usage tracking,
and an admin panel.

Env vars:
  ANTHROPIC_API_KEY  Claude API key (console.anthropic.com)
  MODEL              Claude model id (default: claude-fable-5-1)
  ADMIN_PASSWORD     Password for the /admin panel (required)
  DATA_DIR           Storage dir (default "."; use "/data" with a Railway
                     volume so codes/sessions/usage survive redeploys)
  DAILY_LIMIT        Max chat messages per invite code per day (default: 100)
  PORT               Listen port (default: 5000)

Invite links look like: https://<host>/i/<CODE>  (single use, like Telegram)
Admin panel: https://<host>/admin
"""
import base64
import datetime
import hashlib
import io
import json
import os
import re
import secrets
import time

from flask import Flask, jsonify, redirect, request, send_file, session, url_for

import brain

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif",
                ".pdf", ".txt", ".md", ".markdown", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def shrink_image(data, ext):
    """Downscale large images to bound vision cost. Returns (mime, bytes)."""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.thumbnail((2048, 2048))
    buf = io.BytesIO()
    if ext in (".png", ".gif"):
        img.save(buf, "PNG")
        return "image/png", buf.getvalue()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    return "image/jpeg", buf.getvalue()

DATA_DIR = os.environ.get("DATA_DIR", ".")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "100"))
DAILY_COST_LIMIT = float(os.environ.get("DAILY_COST_LIMIT", "1.0"))
PORT = int(os.environ.get("PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))


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

# code -> {"used_by": sid|None, "label": "", "created": ts, "used_at": ts|None,
#          "day": "YYYY-MM-DD", "count": int}
codes = _load_json("webcodes.json", {})
# sid -> {"code": code, "created": ts}
sessions = _load_json("websessions.json", {})
# email -> {"pw": hash, "code": code, "created": ts}
users = _load_json("webusers.json", {})
# sid -> [ {"role":..., "content":...} ]
histories = _load_json("webhistories.json", {})
# code -> {"input": int, "output": int, "cost": float}
usage = _load_json("webusage.json", {})
# fid -> {"name":..., "mime":..., "sid":..., "created": ts}
filemeta = _load_json("webfiles.json", {})

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def save_all():
    _save_json("webcodes.json", codes)
    _save_json("websessions.json", sessions)
    _save_json("webhistories.json", histories)
    _save_json("webusage.json", usage)
    _save_json("webfiles.json", filemeta)
    _save_json("webusers.json", users)


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000)
    return f"{salt}${h.hex()}"


def check_pw(pw, stored):
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hash_pw(pw, salt) == stored


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


def hist_key(sid):
    """Chat history and images follow the invite code, not the browser
    session — so the same chat survives signup, email login, and device
    switches. One-time migration of old sid-keyed entries."""
    code = code_for_sid(sid)
    if sid in histories and code not in histories:
        histories[code] = histories.pop(sid)
    if sid in session_images and code not in session_images:
        session_images[code] = session_images.pop(sid)
    return code


def over_daily_limit(code):
    today = datetime.date.today().isoformat()
    e = codes.get(code, {})
    d = e.get("daily") or {}
    if d.get("day") != today:
        return False
    return d.get("count", 0) >= DAILY_LIMIT


def over_daily_cost_limit(code):
    today = datetime.date.today().isoformat()
    e = codes.get(code, {})
    d = e.get("daily") or {}
    if d.get("day") != today:
        return False
    return d.get("cost", 0.0) >= DAILY_COST_LIMIT


def bump_daily(code, cost=0.0):
    today = datetime.date.today().isoformat()
    e = codes.setdefault(code, {})
    d = e.get("daily") or {}
    if d.get("day") == today:
        d["count"] = d.get("count", 0) + 1
        d["cost"] = d.get("cost", 0.0) + cost
    else:
        d = {"day": today, "count": 1, "cost": cost}
    e["daily"] = d


def record_usage(code, api_usage):
    inp = api_usage.get("input_tokens", 0)
    out = api_usage.get("output_tokens", 0)
    cost = brain.cost_for(brain.MODEL, inp, out)
    u = usage.setdefault(code, {"input": 0, "output": 0, "cost": 0.0})
    u["input"] += inp
    u["output"] += out
    u["cost"] += cost
    # Also track in daily counter for the $1/day cap
    today = datetime.date.today().isoformat()
    e = codes.setdefault(code, {})
    d = e.get("daily") or {}
    if d.get("day") == today:
        d["cost"] = d.get("cost", 0.0) + cost
        e["daily"] = d


def cleanup_files():
    """Drop generated files older than 24h."""
    now = time.time()
    dead = [fid for fid, m in filemeta.items() if now - m.get("created", 0) > 86400]
    for fid in dead:
        try:
            os.remove(os.path.join(DATA_DIR, "files", fid))
        except OSError:
            pass
        filemeta.pop(fid, None)
    if dead:
        _save_json("webfiles.json", filemeta)


def workspace_dir(sid):
    """Private per-session file workspace (persists on the volume)."""
    d = os.path.join(DATA_DIR, "workspaces", sid)
    os.makedirs(d, exist_ok=True)
    return d


def _finalize_reply(sid, code, reply_text):
    """Build downloadable files from ```excel/```pdf blocks. Returns (clean, files)."""
    clean, blocks = brain.extract_blocks(reply_text)
    files = []
    if blocks:
        cleanup_files()
        for kind, fname, fbytes, mime in brain.build_files(blocks):
            fid = secrets.token_hex(8)
            os.makedirs(os.path.join(DATA_DIR, "files"), exist_ok=True)
            with open(os.path.join(DATA_DIR, "files", fid), "wb") as f:
                f.write(fbytes)
            filemeta[fid] = {"name": fname, "mime": mime, "sid": sid,
                             "created": time.time()}
            files.append({"id": fid, "name": fname, "mime": mime})
        _save_json("webfiles.json", filemeta)
    return clean, files


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
    return redirect(url_for("index"))


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "Claude AI Pro",
        "short_name": "AI Pro",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#d97706",
        "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png"}],
    })


@app.route("/icon.png")
def icon():
    return send_file(os.path.join(BASE_DIR, "static", "icon.png"),
                     mimetype="image/png")


# ---------- chat API ----------

@app.route("/api/redeem", methods=["POST"])
def api_redeem():
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    e = codes.get(code)
    if not e:
        return jsonify({"ok": False, "error": "Invalid invite code."}), 404
    if e.get("banned"):
        return jsonify({"ok": False, "error": e.get("ban_message", "This code has been disabled.")}), 403
    if e.get("used_by"):
        return jsonify({"ok": False, "error": "This invite code was already used."}), 410
    sid = secrets.token_hex(16)
    e["used_by"] = sid
    e["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    sessions[sid] = {"code": code, "created": e["used_at"]}
    save_all()
    session["sid"] = sid
    return jsonify({"ok": True})


@app.route("/api/signup", methods=["POST"])
def api_signup():
    """Create an email+password account linked to the current invite code.
    Requires an active invite-code session. Chat history follows the code,
    so nothing is lost."""
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Sign in with your invite code first."}), 401
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "error": "Enter a valid email address."}), 400
    if len(pw) < 6:
        return jsonify({"ok": False, "error": "Password must be at least 6 characters."}), 400
    if email in users:
        return jsonify({"ok": False, "error": "This email is already registered — log in instead."}), 409
    code = code_for_sid(sid)
    users[email] = {"pw": hash_pw(pw), "code": code,
                    "created": datetime.datetime.now().isoformat(timespec="seconds")}
    save_all()
    return jsonify({"ok": True})


@app.route("/api/email_login", methods=["POST"])
def api_email_login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    u = users.get(email)
    if not u or not check_pw(pw, u.get("pw", "")):
        return jsonify({"ok": False, "error": "Wrong email or password."}), 401
    code = u.get("code")
    if code not in codes:
        return jsonify({"ok": False, "error": "This account's access is gone — contact support."}), 410
    sid = secrets.token_hex(16)
    sessions[sid] = {"code": code, "created": datetime.datetime.now().isoformat(timespec="seconds"),
                     "via": "email", "email": email}
    save_all()
    session["sid"] = sid
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("sid", None)
    return jsonify({"ok": True})


@app.route("/api/new", methods=["POST"])
def api_new():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    hk = hist_key(sid)
    histories.pop(hk, None)
    session_images.pop(hk, None)
    persist_images(hk)
    _save_json("webhistories.json", histories)
    return jsonify({"ok": True})


# Images stay visible for follow-up questions (like Claude Pro): the latest
# attached images are re-sent with every later message in the same session.
# Persisted to disk (not just memory) so a server restart/redeploy mid-chat
# can't silently "forget" them.
session_images = _load_json("webimages.json", {})


def persist_images(key):
    imgs = session_images.get(key, [])[-3:]
    if imgs:
        session_images[key] = imgs
    else:
        session_images.pop(key, None)
    live_codes = set(sessions[s]["code"] for s in sessions)
    for s in [s for s in session_images if s not in sessions and s not in live_codes]:
        session_images.pop(s, None)
    _save_json("webimages.json", session_images)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    hk = hist_key(sid)
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("message") or "").strip()
    agent_mode = bool(data.get("agent"))
    if not text:
        return jsonify({"ok": False, "error": "Empty message."}), 400
    if len(text) > 6000:
        return jsonify({"ok": False, "error": "Message too long (6000 chars max)."}), 400
    if over_daily_limit(code):
        return jsonify({"ok": False,
                         "error": "You've reached today's message limit — come back tomorrow!"}), 429
    if over_daily_cost_limit(code):
        return jsonify({"ok": False,
                         "error": "You've reached today's $1 usage limit — come back tomorrow!"}), 429

    history = histories.setdefault(hk, [])
    hist_len = len(history)
    history.append({"role": "user", "content": text})
    brain.trim_history(history)
    steps, wsfiles = [], []
    try:
        if agent_mode:
            wsdir = workspace_dir(sid)
            reply, api_usage, steps, new_files = brain.ask_claude_agent(
                history, wsdir)
            reply = (reply or "").strip()
            wsfiles = [{"name": n, "url": "/wsfile/" + n} for n in new_files
                       if os.path.isfile(os.path.join(wsdir, n))]
        else:
            # re-send images attached earlier this session so follow-ups can see them
            attachments = [{"kind": "image", "mime": mime, "b64": b64}
                           for mime, b64 in session_images.get(hk, [])]
            reply, api_usage = brain.ask_claude(history, attachments=attachments or None)
            reply = reply.strip()
    except Exception as ex:
        print("Claude API failed:", ex)
        del history[hist_len:]  # roll back user msg + any partial agent turns
        return jsonify({"ok": False,
                         "error": "The AI didn't respond — try again in a moment."}), 502
    if not reply:
        del history[hist_len:]
        return jsonify({"ok": False, "error": "Empty reply — try again."}), 502
    if not agent_mode:
        history.append({"role": "assistant", "content": reply})
        brain.trim_history(history)
    bump_daily(code)
    record_usage(code, api_usage)

    clean, files = _finalize_reply(sid, code, reply)
    save_all()
    if not clean and not files and not wsfiles:
        return jsonify({"ok": True, "reply": reply, "files": []})
    return jsonify({"ok": True, "reply": clean or "Here you go! 📎",
                    "files": files, "steps": steps, "wsfiles": wsfiles})


@app.route("/api/upload_chat", methods=["POST"])
def api_upload_chat():
    """Chat turn with a file attachment (photo or document). Multipart form."""
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    hk = hist_key(sid)
    text = (request.form.get("message") or "").strip()
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No file attached."}), 400
    if len(text) > 6000:
        return jsonify({"ok": False, "error": "Message too long (6000 chars max)."}), 400
    if over_daily_limit(code):
        return jsonify({"ok": False,
                         "error": "You've reached today's message limit — come back tomorrow!"}), 429
    if over_daily_cost_limit(code):
        return jsonify({"ok": False,
                         "error": "You've reached today's $1 usage limit — come back tomorrow!"}), 429
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        return jsonify({"ok": False,
                         "error": "That file type isn't supported (photos, PDF, TXT, Markdown, CSV)."}), 400
    data = f.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"ok": False, "error": "File too big (10MB max)."}), 400
    if not data:
        return jsonify({"ok": False, "error": "Empty file."}), 400

    attachments = []
    stored_label = ""
    stored_extra = ""
    try:
        if ext in IMAGE_EXTS:
            mime, img_bytes = shrink_image(data, ext)
            b64 = base64.b64encode(img_bytes).decode()
            attachments.append({"kind": "image", "mime": mime, "b64": b64})
            session_images.setdefault(hk, []).append([mime, b64])
            persist_images(sid)
            stored_label = f"[Image attached: {f.filename}]"
        elif ext == ".pdf":
            attachments.append({"kind": "pdf",
                                "b64": base64.b64encode(data).decode()})
            ok, pdf_text = brain.extract_pdf_text(data)
            stored_extra = pdf_text if ok else ""
            stored_label = f"[PDF attached: {f.filename}]"
        else:
            ok, doc_text = brain.extract_doc_text(f.filename, data)
            if not ok:
                return jsonify({"ok": False, "error": f"Couldn't read that file: {doc_text}"}), 400
            attachments.append({"kind": "doc", "name": f.filename, "text": doc_text})
            stored_extra = doc_text[:6000]
            stored_label = f"[Document attached: {f.filename}]"
    except Exception as e:
        print("upload processing failed:", e)
        return jsonify({"ok": False, "error": "Couldn't process that file."}), 400

    history = histories.setdefault(hk, [])
    hist_len = len(history)
    agent_mode = (request.form.get("agent") or "").lower() in ("1", "true", "on")
    steps, wsfiles = [], []
    try:
        if agent_mode:
            # Agent mode: the file lands in the workspace so the agent can
            # actually work with it (run code on a CSV, read a doc, ...).
            wsdir = workspace_dir(sid)
            wsfname = os.path.basename(f.filename or "upload")
            try:
                with open(brain.safe_ws_path(wsdir, wsfname), "wb") as fh:
                    fh.write(data)
                ws_note = f"\n[File saved to your workspace as {wsfname}]"
            except ValueError:
                ws_note = ""
            if stored_extra:
                user_text = f"{stored_label}\n{stored_extra}\n\n{text}".strip() + ws_note
            else:
                user_text = ((stored_label + " " + text).strip()
                             or stored_label) + ws_note
            history.append({"role": "user", "content": user_text})
            brain.trim_history(history)
            agent_attachments = []
            if ext in IMAGE_EXTS and session_images.get(hk):
                mime_last, b64_last = session_images[hk][-1]
                agent_attachments = [{"kind": "image", "mime": mime_last,
                                      "b64": b64_last}]
            reply, api_usage, steps, new_files = brain.ask_claude_agent(
                history, wsdir, attachments=agent_attachments or None)
            reply = (reply or "").strip()
            wsfiles = [{"name": n, "url": "/wsfile/" + n} for n in new_files
                       if os.path.isfile(os.path.join(wsdir, n))]
        else:
            history.append({"role": "user", "content": text})
            brain.trim_history(history)
            # Re-send images attached earlier this session on EVERY turn (including
            # upload turns). If the model ever sees an "[Image attached]" placeholder
            # without the image data, it falsely concludes it hallucinated earlier
            # descriptions and "retracts" them.
            prior = session_images.get(hk, [])
            if ext in IMAGE_EXTS:
                prior = prior[:-1]  # the just-uploaded image is already in attachments
            for mime0, b640 in prior:
                attachments.append({"kind": "image", "mime": mime0, "b64": b640})
            reply, api_usage = brain.ask_claude(history, attachments=attachments)
            reply = reply.strip()
    except Exception as ex:
        print("Claude API failed:", ex)
        del history[hist_len:]  # roll back user msg + any partial agent turns
        return jsonify({"ok": False,
                         "error": "The AI didn't respond — try again in a moment."}), 502
    if not reply:
        del history[hist_len:]
        return jsonify({"ok": False, "error": "Empty reply — try again."}), 502
    if not agent_mode:
        # store the document text (not just a placeholder) so follow-up
        # questions work; images are re-sent from session_images instead
        if stored_extra:
            stored_content = (f"{stored_label}\n{stored_extra}\n\n{text}").strip()
        else:
            stored_content = (stored_label + " " + text).strip() or stored_label
        history[-1] = {"role": "user", "content": stored_content}
        history.append({"role": "assistant", "content": reply})
        brain.trim_history(history)
    bump_daily(code)
    record_usage(code, api_usage)

    clean, files = _finalize_reply(sid, code, reply)
    save_all()
    if not clean and not files and not wsfiles:
        return jsonify({"ok": True, "reply": reply, "files": []})
    return jsonify({"ok": True, "reply": clean or "Here you go! 📎",
                    "files": files, "steps": steps, "wsfiles": wsfiles})


@app.route("/files/<fid>")
def get_file(fid):
    sid = current_sid()
    m = filemeta.get(fid)
    if not sid or not m or m.get("sid") != sid:
        return "Not found", 404
    path = os.path.join(DATA_DIR, "files", fid)
    if not os.path.exists(path):
        return "Expired", 410
    return send_file(path, mimetype=m["mime"], as_attachment=True,
                     download_name=m["name"])


# ---------- workspace (per-session file area for agent mode) ----------

def _ws_size_display(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


@app.route("/api/ws_files")
def api_ws_files():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    wsdir = workspace_dir(sid)
    items = []
    for name in sorted(os.listdir(wsdir)):
        p = os.path.join(wsdir, name)
        if os.path.isfile(p):
            st = os.stat(p)
            items.append({
                "name": name,
                "size": _ws_size_display(st.st_size),
                "mtime": datetime.datetime.fromtimestamp(st.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"),
            })
    return jsonify({"ok": True, "files": items})


@app.route("/wsfile/<path:name>")
def ws_file(name):
    sid = current_sid()
    if not sid:
        return "Not found", 404
    try:
        p = brain.safe_ws_path(workspace_dir(sid), name)
    except ValueError:
        return "Not found", 404
    if not os.path.isfile(p):
        return "Not found", 404
    return send_file(p, as_attachment=True,
                     download_name=os.path.basename(p))


@app.route("/api/ws_delete", methods=["POST"])
def api_ws_delete():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "No file named."}), 400
    try:
        p = brain.safe_ws_path(workspace_dir(sid), name)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid path."}), 400
    if not os.path.isfile(p):
        return jsonify({"ok": False, "error": "File not found."}), 404
    os.remove(p)
    return jsonify({"ok": True})


@app.route("/api/ws_upload", methods=["POST"])
def api_ws_upload():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No file attached."}), 400
    data = f.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"ok": False, "error": "File too big (10MB max)."}), 400
    if not data:
        return jsonify({"ok": False, "error": "Empty file."}), 400
    fname = os.path.basename(f.filename or "upload")
    if not fname:
        return jsonify({"ok": False, "error": "Bad filename."}), 400
    try:
        p = brain.safe_ws_path(workspace_dir(sid), fname)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid filename."}), 400
    with open(p, "wb") as fh:
        fh.write(data)
    return jsonify({"ok": True, "name": fname})


# ---------- admin ----------

def is_admin():
    return session.get("admin") is True and ADMIN_PASSWORD


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
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Wrong password."}), 403


@app.route("/api/admin/data")
def api_admin_data():
    if not is_admin():
        return jsonify({"ok": False}), 403
    rows = []
    for c, e in codes.items():
        u = usage.get(c, {"input": 0, "output": 0, "cost": 0.0})
        d = e.get("daily") or {}
        rows.append({"code": c, "link": invite_link(c),
                     "used": bool(e.get("used_by")),
                     "created": e.get("created", ""),
                     "today": d.get("count", 0) if d.get("day") == datetime.date.today().isoformat() else 0,
                     "in": u["input"], "out": u["output"], "cost": round(u["cost"], 4)})
    rows.sort(key=lambda r: r["created"], reverse=True)
    t_in = sum(u["input"] for u in usage.values())
    t_out = sum(u["output"] for u in usage.values())
    t_cost = sum(u["cost"] for u in usage.values())
    return jsonify({"ok": True, "codes": rows,
                    "totals": {"in": t_in, "out": t_out, "cost": round(t_cost, 4),
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
        codes[c] = {"used_by": None, "label": "", "created": now,
                    "used_at": None, "daily": None}
        fresh.append({"code": c, "link": invite_link(c)})
    _save_json("webcodes.json", codes)
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
    # Optional ban with message
    ban_msg = (data.get("ban_message") or "").strip()
    if ban_msg:
        e["banned"] = True
        e["ban_message"] = ban_msg
    else:
        e.pop("banned", None)
        e.pop("ban_message", None)
    if sid:
        sessions.pop(sid, None)
    histories.pop(code, None)
    histories.pop(sid, None)
    session_images.pop(code, None)
    session_images.pop(sid, None)
    save_all()
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not brain.ANTHROPIC_API_KEY:
        print("Set the ANTHROPIC_API_KEY env var.")
    app.run(host="0.0.0.0", port=PORT)
