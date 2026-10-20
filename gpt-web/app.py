"""Chat GPT Plus API web app.

Private 1-on-1 GPT chat in the browser, powered by OpenAI. Invite-code access,
per-code daily caps, Excel/PDF file downloads, usage tracking, and an admin panel.

Env vars:
  OPENAI_API_KEY   OpenAI API key (platform.openai.com)
  MODEL            OpenAI model id (default: gpt-6.1-sol)
  INPUT_RATE       $ per 1M input tokens for cost estimates (default: 2.0)
  OUTPUT_RATE      $ per 1M output tokens for cost estimates (default: 10.0)
  ADMIN_PASSWORD   Password for the /admin panel (required)
  DATA_DIR         Storage dir (default "."; use "/data" with a Railway
                   volume so codes/sessions/usage survive redeploys)
  DAILY_LIMIT      Max chat messages per invite code per day (default: 100)
  PORT             Listen port (default: 5000)

Invite links look like: https://<host>/i/<CODE>  (single use)
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
    if ext == ".png":
        img.save(buf, "PNG")
        return "image/png", buf.getvalue()
    img.convert("RGB").save(buf, "JPEG", quality=85)
    return "image/jpeg", buf.getvalue()

DATA_DIR = os.environ.get("DATA_DIR", ".")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SUBSCRIPTION_SECRET = os.environ.get("SUBSCRIPTION_SECRET", "")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "100"))
DAILY_COST_LIMIT = float(os.environ.get("DAILY_COST_LIMIT", "1.0"))
AGENT_DAILY_LIMIT = int(os.environ.get("AGENT_DAILY_LIMIT", "20"))
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
# Logins persist across browser restarts (90 days) — invite codes are
# single-use, so customers must not be locked out by closing the browser.
app.permanent_session_lifetime = datetime.timedelta(days=90)

codes = _load_json("gptcodes.json", {})
sessions = _load_json("gptsessions.json", {})
histories = _load_json("gpthistories.json", {})
usage = _load_json("gptusage.json", {})
filemeta = _load_json("gptfiles.json", {})
users = _load_json("gptusers.json", {})

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def save_all():
    _save_json("gptcodes.json", codes)
    _save_json("gptsessions.json", sessions)
    _save_json("gpthistories.json", histories)
    _save_json("gptusage.json", usage)
    _save_json("gptfiles.json", filemeta)
    _save_json("gptusers.json", users)


def hash_pw(pw, salt=None):
    import hashlib
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
    """Conversation store follows the invite code, not the browser session —
    so the same chats survive signup, email login, and device switches.
    One-time migration of old sid-keyed entries."""
    code = code_for_sid(sid)
    if sid in histories and code not in histories:
        histories[code] = histories.pop(sid)
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


def bump_daily(code):
    today = datetime.date.today().isoformat()
    e = codes.setdefault(code, {})
    d = e.get("daily") or {}
    if d.get("day") == today:
        d["count"] = d.get("count", 0) + 1
    else:
        d = {"day": today, "count": 1}
    e["daily"] = d


def over_agent_limit(code):
    today = datetime.date.today().isoformat()
    e = codes.get(code, {})
    d = e.get("agent_daily") or {}
    if d.get("day") != today:
        return False
    return d.get("count", 0) >= AGENT_DAILY_LIMIT


def bump_agent_daily(code):
    today = datetime.date.today().isoformat()
    e = codes.setdefault(code, {})
    d = e.get("agent_daily") or {}
    if d.get("day") == today:
        d["count"] = d.get("count", 0) + 1
    else:
        d = {"day": today, "count": 1}
    e["agent_daily"] = d


def workspace_dir(sid):
    d = os.path.join(DATA_DIR, "workspaces", sid)
    os.makedirs(d, exist_ok=True)
    return d


def record_usage(code, api_usage):
    inp = api_usage.get("input_tokens", 0)
    out = api_usage.get("output_tokens", 0)
    cost = brain.cost_for(inp, out)
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


def get_convo_store(sid):
    """Conversations for a session, migrating legacy flat history.
    Keyed by invite code so chats survive signup / email login / new devices."""
    hk = hist_key(sid)
    h = histories.get(hk)
    if not h or "convos" not in h:
        legacy = h if isinstance(h, list) else []
        msgs = []
        for m in legacy:
            if isinstance(m, dict):
                msgs.append({"role": m.get("role", "user"),
                             "content": m.get("content", ""), "files": []})
            elif isinstance(m, (list, tuple)) and len(m) == 2:
                msgs.append({"role": m[0], "content": m[1], "files": []})
        h = {"convos": [{"id": "c1", "title": "Chat", "messages": msgs,
                         "created": time.time(), "updated": time.time()}],
             "active": "c1"}
        histories[hk] = h
    return h


def active_convo(sid):
    st = get_convo_store(sid)
    for c in st["convos"]:
        if c["id"] == st.get("active"):
            return c
    st["active"] = st["convos"][0]["id"]
    return st["convos"][0]


def new_convo(sid):
    st = get_convo_store(sid)
    c = {"id": "c" + secrets.token_hex(6), "title": "New chat",
         "messages": [], "created": time.time(), "updated": time.time()}
    st["convos"].append(c)
    st["active"] = c["id"]
    return c


def api_turns_for(convo):
    return [{"role": m["role"], "content": m["content"]}
            for m in convo["messages"][-20:]]


def store_file(sid, fname, fbytes, mime):
    """Save generated bytes, return the file dict for the chat response."""
    fid = secrets.token_hex(8)
    os.makedirs(os.path.join(DATA_DIR, "files"), exist_ok=True)
    with open(os.path.join(DATA_DIR, "files", fid), "wb") as f:
        f.write(fbytes)
    filemeta[fid] = {"name": fname, "mime": mime, "sid": sid,
                     "created": time.time()}
    return {"id": fid, "name": fname, "mime": mime}


def track_images(code, n=1):
    u = usage.setdefault(code, {"input": 0, "output": 0, "cost": 0.0})
    u["images"] = u.get("images", 0) + n
    u["cost"] += brain.IMAGE_COST * n


def split_blocks(reply, user_text, pending_image=False):
    """Split fenced blocks; if the user asked for an image (this turn, or an
    earlier turn still pending) but the model didn't use the ```image fence,
    fall back to its last non-code fenced block as the prompt."""
    clean, blocks = brain.extract_blocks(reply)
    img_blocks = [content for kind, content in blocks if kind == "image"]
    if not img_blocks:
        fb_prompt, fb_clean = brain.extract_image_fallback(
            user_text, reply, force=pending_image)
        if fb_prompt:
            img_blocks = [fb_prompt]
            clean = fb_clean
    doc_blocks = [(kind, content) for kind, content in blocks if kind != "image"]
    return clean, img_blocks, doc_blocks


def update_pending_image(convo, text, img_blocks, files):
    """Remember an unfulfilled image request so a follow-up answer
    (e.g. 'photorealistic') still triggers generation."""
    if img_blocks and files:
        convo["pending_image"] = False
    elif brain.looks_like_image_request(text):
        convo["pending_image"] = True
    elif len(text) > 80:
        convo["pending_image"] = False


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
        _save_json("gptfiles.json", filemeta)


# ---------- pages ----------

@app.route("/")
def index():
    from flask import render_template
    return render_template("index.html", logged_in=bool(current_sid()),
                           model_name=brain.MODEL)


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


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "Chat GPT Plus API",
        "short_name": "GPT Plus",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#4f46e5",
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
    if e.get("used_by"):
        return jsonify({"ok": False, "error": "This invite code was already used."}), 410
    sid = secrets.token_hex(16)
    e["used_by"] = sid
    e["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    sessions[sid] = {"code": code, "created": e["used_at"]}
    save_all()
    session["sid"] = sid
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/my_usage", methods=["GET"])
def api_my_usage():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    u = usage.get(code, {"input": 0, "output": 0, "cost": 0.0})
    today = datetime.date.today().isoformat()
    e = codes.get(code, {})
    d = e.get("daily") or {}
    daily_cost = d.get("cost", 0.0) if d.get("day") == today else 0.0
    daily_count = d.get("count", 0) if d.get("day") == today else 0
    return jsonify({
        "ok": True,
        "total_cost": round(u.get("cost", 0.0), 4),
        "total_input": u.get("input", 0),
        "total_output": u.get("output", 0),
        "daily_cost": round(daily_cost, 4),
        "daily_count": daily_count,
        "daily_cost_limit": DAILY_COST_LIMIT,
        "daily_msg_limit": DAILY_LIMIT,
    })


@app.route("/api/signup", methods=["POST"])
def api_signup():
    """Create an email+password account linked to the current invite code.
    Requires an active invite-code session."""
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
        return jsonify({"ok": False, "error": "This account's subscription is gone — contact support."}), 410
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
    c = new_convo(sid)
    _save_json("gpthistories.json", histories)
    return jsonify({"ok": True, "convo": c["id"], "title": c["title"]})


@app.route("/api/convos")
def api_convos():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    st = get_convo_store(sid)
    convos = sorted(st["convos"], key=lambda c: c.get("updated", 0), reverse=True)
    return jsonify({"ok": True, "active": st["active"],
                    "convos": [{"id": c["id"], "title": c["title"],
                                "n": len(c["messages"])} for c in convos]})


@app.route("/api/convos/new", methods=["POST"])
def api_convos_new():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    c = new_convo(sid)
    _save_json("gpthistories.json", histories)
    return jsonify({"ok": True, "convo": c["id"], "title": c["title"]})


@app.route("/api/convos/open", methods=["POST"])
def api_convos_open():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    data = request.get_json(force=True, silent=True) or {}
    cid = data.get("id")
    st = get_convo_store(sid)
    c = next((x for x in st["convos"] if x["id"] == cid), None)
    if not c:
        return jsonify({"ok": False, "error": "Conversation not found."}), 404
    st["active"] = c["id"]
    _save_json("gpthistories.json", histories)
    return jsonify({"ok": True, "convo": c["id"], "title": c["title"],
                    "messages": c["messages"]})


@app.route("/api/convos/delete", methods=["POST"])
def api_convos_delete():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    data = request.get_json(force=True, silent=True) or {}
    cid = data.get("id")
    st = get_convo_store(sid)
    if len(st["convos"]) <= 1:
        # never delete the last one — just clear it
        c = st["convos"][0]
        c["messages"] = []
        c["title"] = "New chat"
        st["active"] = c["id"]
    else:
        st["convos"] = [x for x in st["convos"] if x["id"] != cid]
        if st.get("active") == cid:
            st["active"] = st["convos"][0]["id"]
    _save_json("gpthistories.json", histories)
    c = active_convo(sid)
    return jsonify({"ok": True, "active": c["id"], "messages": c["messages"]})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("message") or "").strip()
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

    agent_mode = bool(data.get("agent"))
    if agent_mode and over_agent_limit(code):
        return jsonify({"ok": False,
                         "error": f"Agent mode limit reached ({AGENT_DAILY_LIMIT}/day) — come back tomorrow!"}), 429

    convo = active_convo(sid)
    msgs = convo["messages"]
    msgs.append({"role": "user", "content": text, "files": []})
    if not any(m["role"] == "user" for m in msgs[:-1]):
        convo["title"] = text[:42]
    convo["updated"] = time.time()
    new_agent_files = []
    try:
        if agent_mode:
            wsdir = workspace_dir(sid)
            reply, api_usage, steps, new_agent_files = brain.ask_gpt_agent(
                api_turns_for(convo), wsdir)
            reply = reply.strip()
            if steps:
                reply += "\n\n⚙️ Steps: " + " → ".join(steps)
        else:
            reply, api_usage = brain.ask_gpt(api_turns_for(convo))
            reply = reply.strip()
    except Exception as ex:
        print("OpenAI API failed:", ex)
        msgs.pop()
        return jsonify({"ok": False,
                         "error": "The AI didn't respond — try again in a moment."}), 502
    if not reply:
        msgs.pop()
        return jsonify({"ok": False, "error": "Empty reply — try again."}), 502
    amsg = {"role": "assistant", "content": reply, "files": []}
    msgs.append(amsg)
    if len(msgs) > 40:
        del msgs[:-40]
    bump_daily(code)
    if agent_mode:
        bump_agent_daily(code)
    record_usage(code, api_usage)

    clean, img_blocks, doc_blocks = split_blocks(
        reply, text, pending_image=bool(convo.get("pending_image")))
    files = []
    if agent_mode:
        # offer agent-created workspace files as downloads
        for fname in new_agent_files:
            fpath = os.path.join(workspace_dir(sid), fname)
            if os.path.isfile(fpath):
                with open(fpath, "rb") as fh:
                    fbytes = fh.read()
                if len(fbytes) <= 10 * 1024 * 1024:
                    files.append(store_file(sid, fname, fbytes,
                                            "application/octet-stream"))
    blocked = False
    if img_blocks or doc_blocks:
        cleanup_files()
        import datetime
        for kind, fname, fbytes, mime in brain.build_files(doc_blocks):
            files.append(store_file(sid, fname, fbytes, mime))
        for prompt in img_blocks:
            try:
                img_bytes = brain.generate_image(prompt)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                files.append(store_file(sid, f"image_{ts}.png", img_bytes, "image/png"))
                track_images(code)
            except brain.ImageBlockedError:
                blocked = True
                print("image blocked by safety filter")
            except Exception as e:
                print("image generation failed:", e)
        _save_json("gptfiles.json", filemeta)
    amsg["files"] = files
    amsg["content"] = clean or amsg["content"]
    update_pending_image(convo, text, img_blocks, files)
    save_all()
    image_files = [f for f in files if f["mime"].startswith("image/")]
    if img_blocks and not image_files:
        msg = ("⚠️ That image was declined by the safety filter — "
               "try describing it differently." if blocked else
               "⚠️ I couldn't generate the image — try again in a moment.")
        amsg["content"] = msg
        _save_json("gpthistories.json", histories)
        return jsonify({"ok": True, "reply": msg, "files": files,
                        "convo": convo["id"], "title": convo["title"]})
    if doc_blocks and not files:
        return jsonify({"ok": True, "reply": reply, "files": [],
                        "convo": convo["id"], "title": convo["title"]})
    return jsonify({"ok": True, "reply": clean or "Here you go! 📎", "files": files,
                    "convo": convo["id"], "title": convo["title"]})


@app.route("/api/upload_chat", methods=["POST"])
def api_upload_chat():
    """Chat turn with file attachment(s) (photo or document). Multipart form."""
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    text = (request.form.get("message") or "").strip()
    files = request.files.getlist("file")
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"ok": False, "error": "No file attached."}), 400
    if len(files) > 5:
        return jsonify({"ok": False, "error": "Max 5 files at once."}), 400
    if len(text) > 6000:
        return jsonify({"ok": False, "error": "Message too long (6000 chars max)."}), 400
    if over_daily_limit(code):
        return jsonify({"ok": False,
                         "error": "You've reached today's message limit — come back tomorrow!"}), 429
    if over_daily_cost_limit(code):
        return jsonify({"ok": False,
                         "error": "You've reached today's $1 usage limit — come back tomorrow!"}), 429

    attachments = []
    stored_labels = []
    try:
        for f in files:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ALLOWED_EXTS:
                return jsonify({"ok": False,
                                 "error": f"{f.filename}: that file type isn't supported (photos, PDF, TXT, Markdown, CSV)."}), 400
            data = f.read()
            if len(data) > MAX_UPLOAD_BYTES:
                return jsonify({"ok": False, "error": f"{f.filename}: file too big (10MB max)."}), 400
            if not data:
                return jsonify({"ok": False, "error": f"{f.filename}: empty file."}), 400
            if ext in IMAGE_EXTS:
                mime, img_bytes = shrink_image(data, ext)
                attachments.append({"kind": "image", "mime": mime,
                                    "b64": base64.b64encode(img_bytes).decode()})
                stored_labels.append(f"[Image attached: {f.filename}]")
            else:
                ok, doc_text = brain.extract_doc_text(f.filename, data)
                if not ok:
                    return jsonify({"ok": False, "error": f"Couldn't read {f.filename}: {doc_text}"}), 400
                attachments.append({"kind": "doc", "name": f.filename, "text": doc_text})
                stored_labels.append(f"[Document attached: {f.filename}]")
        stored_label = " ".join(stored_labels)
    except Exception as e:
        print("upload processing failed:", e)
        return jsonify({"ok": False, "error": "Couldn't process that file."}), 400

    convo = active_convo(sid)
    msgs = convo["messages"]
    api_turns = api_turns_for(convo) + [{"role": "user", "content": text}]
    try:
        reply, api_usage = brain.ask_gpt(api_turns, attachments=attachments)
        reply = reply.strip()
    except Exception as ex:
        print("OpenAI API failed:", ex)
        return jsonify({"ok": False,
                         "error": "The AI didn't respond — try again in a moment."}), 502
    if not reply:
        return jsonify({"ok": False, "error": "Empty reply — try again."}), 502

    stored_content = (stored_label + " " + text).strip()
    msgs.append({"role": "user", "content": stored_content, "files": []})
    if not any(m["role"] == "user" for m in msgs[:-1]):
        convo["title"] = (text or files[0].filename or "Attachment")[:42]
    convo["updated"] = time.time()
    amsg = {"role": "assistant", "content": reply, "files": []}
    msgs.append(amsg)
    if len(msgs) > 40:
        del msgs[:-40]
    bump_daily(code)
    record_usage(code, api_usage)

    clean, img_blocks, doc_blocks = split_blocks(
        reply, text, pending_image=bool(convo.get("pending_image")))
    files = []
    blocked = False
    if img_blocks or doc_blocks:
        cleanup_files()
        for kind, fname, fbytes, mime in brain.build_files(doc_blocks):
            files.append(store_file(sid, fname, fbytes, mime))
        for prompt in img_blocks:
            try:
                img_bytes = brain.generate_image(prompt)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                files.append(store_file(sid, f"image_{ts}.png", img_bytes, "image/png"))
                track_images(code)
            except brain.ImageBlockedError:
                blocked = True
                print("image blocked by safety filter")
            except Exception as e:
                print("image generation failed:", e)
        _save_json("gptfiles.json", filemeta)
    amsg["files"] = files
    amsg["content"] = clean or amsg["content"]
    update_pending_image(convo, text, img_blocks, files)
    save_all()
    image_files = [f for f in files if f["mime"].startswith("image/")]
    if img_blocks and not image_files:
        msg = ("⚠️ That image was declined by the safety filter — "
               "try describing it differently." if blocked else
               "⚠️ I couldn't generate the image — try again in a moment.")
        amsg["content"] = msg
        _save_json("gpthistories.json", histories)
        return jsonify({"ok": True, "reply": msg, "files": files,
                        "convo": convo["id"], "title": convo["title"]})
    if doc_blocks and not files:
        return jsonify({"ok": True, "reply": reply, "files": [],
                        "convo": convo["id"], "title": convo["title"]})
    return jsonify({"ok": True, "reply": clean or "Here you go! 📎", "files": files,
                    "convo": convo["id"], "title": convo["title"]})


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
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Wrong password."}), 403


@app.route("/api/admin/rotate_secret", methods=["POST"])
def api_admin_rotate_secret():
    """Rotate the Flask session signing key (2026-10-20: the old value was
    accidentally committed to the public repo). Admin-guarded. The new key
    is generated server-side, persisted to the volume, and takes effect
    immediately; all existing sessions are invalidated once (users simply
    log in again). Returns a fingerprint so rotation can be verified
    without the value ever leaving the server."""
    if not is_admin():
        return jsonify({"ok": False}), 403
    new = secrets.token_hex(32)
    with open(os.path.join(DATA_DIR, "secret.key"), "w", encoding="utf-8") as f:
        f.write(new)
    app.secret_key = new
    fp = hashlib.sha256(new.encode()).hexdigest()[:12]
    return jsonify({"ok": True, "fp": fp})


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
                     "in": u["input"], "out": u["output"], "cost": round(u["cost"], 4),
                     "images": u.get("images", 0)})
    rows.sort(key=lambda r: r["created"], reverse=True)
    t_in = sum(u["input"] for u in usage.values())
    t_out = sum(u["output"] for u in usage.values())
    t_cost = sum(u["cost"] for u in usage.values())
    t_img = sum(u.get("images", 0) for u in usage.values())
    return jsonify({"ok": True, "codes": rows,
                    "totals": {"in": t_in, "out": t_out, "cost": round(t_cost, 4),
                               "images": t_img,
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
    _save_json("gptcodes.json", codes)
    return jsonify({"ok": True, "codes": fresh})



@app.route("/api/subscription/create_code", methods=["POST"])
def api_subscription_create_code():
    """Generate an invite code for the subscription bot on approved purchase.
    Auth: SUBSCRIPTION_SECRET env var must match the 'secret' field."""
    if not SUBSCRIPTION_SECRET:
        return jsonify({"ok": False, "error": "not_configured"}), 500
    data = request.get_json(force=True, silent=True) or {}
    if data.get("secret") != SUBSCRIPTION_SECRET:
        return jsonify({"ok": False}), 403
    days = int(data.get("days", 30))
    label = (data.get("label") or "subscription-bot")[:50]
    now = datetime.datetime.now().isoformat(timespec="seconds")
    c = make_code()
    codes[c] = {"used_by": None, "label": label, "created": now,
                "used_at": None, "daily": None, "expires_days": days}
    _save_json("webcodes.json", codes)
    return jsonify({"ok": True, "code": c, "link": invite_link(c)})

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
    histories.pop(code, None)
    histories.pop(sid, None)
    save_all()
    return jsonify({"ok": True})


# ---------- broadcast banner ----------
def _get_broadcast():
    try:
        with open(os.path.join(DATA_DIR, "broadcast.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


@app.route("/api/broadcast")
def api_broadcast():
    if not current_sid():
        return jsonify({"ok": False}), 401
    b = _get_broadcast()
    if not b.get("message"):
        return jsonify({"ok": True, "broadcast": None})
    return jsonify({"ok": True, "broadcast": b})


@app.route("/api/admin/broadcast", methods=["GET", "POST"])
def api_admin_broadcast():
    if not is_admin():
        return jsonify({"ok": False}), 403
    if request.method == "GET":
        b = _get_broadcast()
        return jsonify({"ok": True, "broadcast": b or None})
    data = request.get_json(force=True, silent=True) or {}
    msg = (data.get("message") or "").strip()[:500]
    if msg:
        b = {"id": str(int(time.time())), "message": msg,
             "at": datetime.datetime.now().isoformat()[:16]}
    else:
        b = {}
    with open(os.path.join(DATA_DIR, "broadcast.json"), "w", encoding="utf-8") as fh:
        json.dump(b, fh)
    return jsonify({"ok": True, "broadcast": b or None})


if __name__ == "__main__":
    if not brain.OPENAI_API_KEY:
        print("Set the OPENAI_API_KEY env var.")
    app.run(host="0.0.0.0", port=PORT)
