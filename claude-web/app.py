"""Claude Coworker web app.

Private 1-on-1 Claude chat in the browser. Invite-code access (like the
Telegram bot), per-code daily caps, Excel/PDF file downloads, usage tracking,
and an admin panel.

Env vars:
  ANTHROPIC_API_KEY  Claude API key (console.anthropic.com)
  MODEL              Claude model id (default: claude-sonnet-5-5)
  ADMIN_PASSWORD     Password for the /admin panel (required)
  DATA_DIR           Storage dir (default "."; use "/data" with a Railway
                     volume so codes/sessions/usage survive redeploys)
  DAILY_LIMIT        Max chat messages per invite code per day (default: 100)
  PORT               Listen port (default: 5000)

Invite links look like: https://<host>/i/<CODE>  (single use, like Telegram)
Admin panel: https://<host>/admin
"""
import datetime
import json
import os
import secrets
import time

from flask import Flask, jsonify, redirect, request, send_file, session, url_for

import brain

DATA_DIR = os.environ.get("DATA_DIR", ".")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "100"))
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


def over_daily_limit(code):
    today = datetime.date.today().isoformat()
    e = codes.get(code, {})
    d = e.get("daily") or {}
    if d.get("day") != today:
        return False
    return d.get("count", 0) >= DAILY_LIMIT


def bump_daily(code):
    today = datetime.date.today().isoformat()
    e = codes.setdefault(code, {})
    d = e.get("daily") or {}
    if d.get("day") == today:
        d["count"] = d.get("count", 0) + 1
    else:
        d = {"day": today, "count": 1}
    e["daily"] = d


def record_usage(code, api_usage):
    inp = api_usage.get("input_tokens", 0)
    out = api_usage.get("output_tokens", 0)
    u = usage.setdefault(code, {"input": 0, "output": 0, "cost": 0.0})
    u["input"] += inp
    u["output"] += out
    u["cost"] += brain.cost_for(brain.MODEL, inp, out)


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
        "name": "Claude Coworker",
        "short_name": "Claude",
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
    if e.get("used_by"):
        return jsonify({"ok": False, "error": "This invite code was already used."}), 410
    sid = secrets.token_hex(16)
    e["used_by"] = sid
    e["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    sessions[sid] = {"code": code, "created": e["used_at"]}
    save_all()
    session["sid"] = sid
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
    histories.pop(sid, None)
    _save_json("webhistories.json", histories)
    return jsonify({"ok": True})


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

    history = histories.setdefault(sid, [])
    history.append({"role": "user", "content": text})
    history[:] = history[-20:]
    try:
        reply, api_usage = brain.ask_claude(history)
        reply = reply.strip()
    except Exception as ex:
        print("Claude API failed:", ex)
        history.pop()
        return jsonify({"ok": False,
                         "error": "The AI didn't respond — try again in a moment."}), 502
    if not reply:
        history.pop()
        return jsonify({"ok": False, "error": "Empty reply — try again."}), 502
    history.append({"role": "assistant", "content": reply})
    history[:] = history[-20:]
    bump_daily(code)
    record_usage(code, api_usage)

    clean, blocks = brain.extract_blocks(reply)
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
    save_all()
    if blocks and not files:
        # nothing built — send the raw text so nothing is lost
        return jsonify({"ok": True, "reply": reply, "files": []})
    return jsonify({"ok": True, "reply": clean or "Here you go! 📎", "files": files})


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
    if sid:
        sessions.pop(sid, None)
        histories.pop(sid, None)
    save_all()
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not brain.ANTHROPIC_API_KEY:
        print("Set the ANTHROPIC_API_KEY env var.")
    app.run(host="0.0.0.0", port=PORT)
