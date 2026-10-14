#!/usr/bin/env python3
"""
Envato Elements web app — private download site for the owner's subscription.

Invite-code login (single-use, 90-day validity). Search the Elements library,
preview thumbnails, download files + license certificates.

Env vars:
    DATA_DIR       - persistent dir (Railway volume at /data)
    ADMIN_PASSWORD - for /admin
    PORT           - web port (Railway sets this)
"""

import datetime
import hashlib
import html
import json
import os
import secrets
import threading

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session)

import envato_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
PORT = int(os.environ.get("PORT", "8080"))
SECRET = os.environ.get("FLASK_SECRET", secrets.token_hex(16))

CODES_FILE = os.path.join(DATA_DIR, "web_codes.json")
USERS_FILE = os.path.join(DATA_DIR, "web_users.json")
os.makedirs(DATA_DIR, exist_ok=True)

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

app = Flask(__name__)
app.secret_key = SECRET
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

# search cache: key -> list of items (for download buttons)
search_cache = {}
cache_lock = threading.Lock()


# ---------- invite codes ----------

def _now():
    return datetime.datetime.now()


def _now_iso():
    return _now().isoformat(timespec="seconds")


def load_codes():
    try:
        with open(CODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("codes", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_codes(codes):
    tmp = CODES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"codes": codes}, f, ensure_ascii=False)
    os.replace(tmp, CODES_FILE)


def make_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def code_valid(entry):
    if not entry or entry.get("used_by"):
        # used codes stay valid for the user who redeemed them
        return True
    exp = entry.get("expires_at")
    if exp:
        try:
            if datetime.datetime.fromisoformat(exp) < _now():
                return False
        except ValueError:
            pass
    return True


def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **k):
        if not session.get("code") and not session.get("email"):
            return redirect("/login")
        # verify code still valid
        if session.get("code"):
            codes = load_codes()
            entry = codes.get(session["code"])
            if not entry or not entry.get("used_by"):
                session.clear()
                return redirect("/login")
        if session.get("email"):
            users = load_users()
            if session["email"] not in users:
                session.clear()
                return redirect("/login")
        return fn(*a, **k)

    return wrapper


# ---------- email users ----------

def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("users", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_users(users):
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False)
    os.replace(tmp, USERS_FILE)


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


# ---------- routes ----------

@app.route("/healthz")
def healthz():
    return {"ok": True, "service": "envato-web", "time": _now_iso()}


@app.route("/")
def index():
    if session.get("code") or session.get("email"):
        return redirect("/app")
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        # Email login
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        if email and pw:
            users = load_users()
            u = users.get(email)
            if u and check_pw(pw, u["pw"]):
                session["email"] = email
                return redirect("/app")
            err = "Wrong email or password."
        else:
            # Invite code login
            code = (request.form.get("code") or "").strip().upper()
            codes = load_codes()
            entry = codes.get(code)
            if entry and not entry.get("used_by") and code_valid(entry):
                entry["used_by"] = "web-user"
                entry["used_at"] = _now_iso()
                save_codes(codes)
                session["code"] = code
                return redirect("/app")
            err = "Invalid, used, or expired code."
    return render_template("login.html", err=err)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    err = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        pw2 = request.form.get("password2") or ""
        users = load_users()
        if not email or "@" not in email:
            err = "Enter a valid email."
        elif len(pw) < 6:
            err = "Password must be at least 6 characters."
        elif pw != pw2:
            err = "Passwords don't match."
        elif email in users:
            err = "That email is already registered — just log in."
        else:
            users[email] = {"pw": hash_pw(pw), "created_at": _now_iso()}
            save_users(users)
            session["email"] = email
            return redirect("/app")
    return render_template("signup.html", err=err)


@app.route("/i/<code>")
def auto_redeem(code):
    code = (code or "").strip().upper()
    codes = load_codes()
    entry = codes.get(code)
    if entry and not entry.get("used_by") and code_valid(entry):
        entry["used_by"] = "web-user"
        entry["used_at"] = _now_iso()
        save_codes(codes)
        session["code"] = code
        return redirect("/app")
    return redirect("/login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/app")
@login_required
def app_page():
    return render_template("app.html")


@app.route("/api/search")
@login_required
def api_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "Empty query."}), 400
    try:
        results = envato_client.search(q, limit=20)
    except envato_client.SessionExpired:
        return jsonify({"error": "Envato session expired."}), 401
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500
    key = secrets.token_urlsafe(8)
    with cache_lock:
        search_cache[key] = {r["itemUuid"]: r for r in results}
    # strip to what the UI needs
    items = [{
        "uuid": r["itemUuid"],
        "type": r["itemType"],
        "title": r["title"],
        "author": r.get("author", ""),
        "thumb": r.get("thumb", ""),
    } for r in results]
    return jsonify({"key": key, "items": items})


@app.route("/dl/<key>/<uuid>")
@login_required
def download_file(key, uuid):
    with cache_lock:
        bucket = search_cache.get(key, {})
        item = bucket.get(uuid)
    if not item:
        abort(404)
    try:
        path, fname, lic_pdf = envato_client.download_item(item)
    except envato_client.SessionExpired:
        abort(401)
    except Exception:
        abort(500)
    # stash license path for the /license endpoint
    with cache_lock:
        bucket["_lic_" + uuid] = lic_pdf
    return send_file(path, as_attachment=True, download_name=fname)


@app.route("/license/<key>/<uuid>")
@login_required
def download_license(key, uuid):
    with cache_lock:
        bucket = search_cache.get(key, {})
        lic = bucket.get("_lic_" + uuid)
    if not lic or not os.path.isfile(lic):
        abort(404)
    return send_file(lic, as_attachment=True,
                     download_name=os.path.basename(lic).split("_", 1)[-1])


@app.route("/api/status")
@login_required
def api_status():
    try:
        ok, detail = envato_client.check_session()
    except Exception as e:
        ok, detail = False, str(e)[:200]
    return jsonify({"ok": ok, "detail": detail})


# ---------- admin ----------

def admin_ok():
    return ADMIN_PASSWORD and session.get("admin") is True


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and not admin_ok():
        if (request.form.get("pw") or "") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        return render_template("admin_login.html", err="Wrong password.")
    if not admin_ok():
        return render_template("admin_login.html", err="")
    codes = load_codes()
    rows = []
    for c, e in sorted(codes.items(), key=lambda kv: kv[1].get("created_at", ""), reverse=True):
        if c.startswith("__"):
            continue
        rows.append({
            "code": c,
            "used": bool(e.get("used_by")),
            "created": e.get("created_at", "?")[:10],
            "expires": (e.get("expires_at", "") or "")[:10] or "never",
            "link": f"/i/{c}",
        })
    return render_template("admin.html", rows=rows)


@app.route("/admin/newcodes", methods=["POST"])
def admin_newcodes():
    if not admin_ok():
        abort(403)
    try:
        n = max(1, min(50, int(request.form.get("n", "5"))))
    except ValueError:
        n = 5
    try:
        days = max(1, min(365, int(request.form.get("days", "90"))))
    except ValueError:
        days = 90
    codes = load_codes()
    exp = (_now() + datetime.timedelta(days=days)).isoformat(timespec="seconds")
    for _ in range(n):
        c = make_code()
        codes[c] = {"used_by": None, "created_at": _now_iso(), "expires_at": exp}
    save_codes(codes)
    return redirect("/admin")


@app.route("/admin/revoke/<code>", methods=["POST"])
def admin_revoke(code):
    if not admin_ok():
        abort(403)
    codes = load_codes()
    e = codes.get(code.upper())
    if e:
        e["used_by"] = None
        e["revoked_at"] = _now_iso()
        save_codes(codes)
    return redirect("/admin")


if __name__ == "__main__":
    print(f"envato-web on :{PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
