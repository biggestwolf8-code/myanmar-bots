#!/usr/bin/env python3
"""
Envato Elements personal download bot — @EnvatoElementsUnlimited_Bot.

Private bot for the owner's own Envato Elements unlimited subscription.
Search the Elements library from Telegram and get files + license delivered.

ACCESS: invite-code gated, no cap on the number of accounts. The first user
to /start becomes the owner; the owner mints single-use invite links with
/newcodes and opens one on each of their own Telegram accounts.

Env vars:
    BOT_TOKEN      - from @BotFather (used transiently at setup, never stored)
    DATA_DIR       - persistent dir for codes/cookie/downloads (Railway volume)
    ADMIN_CHAT_ID  - optional: pinned owner id (otherwise first /start wins)
    PORT           - web port for /healthz and file delivery (Railway sets this)
"""

import datetime
import html
import json
import os
import secrets
import threading
import time
import traceback

import requests
from flask import Flask, abort, send_file

import envato_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BOT_USERNAME = "EnvatoElementsUnlimited_Bot"
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
PORT = int(os.environ.get("PORT", "8080"))

if not BOT_TOKEN:
    raise SystemExit("Set the BOT_TOKEN env var (get it from @BotFather).")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
CODES_FILE = os.path.join(DATA_DIR, "codes.json")
DOWNLOADS_DIR = os.path.join(DATA_DIR, "downloads")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

TG_FILE_LIMIT = 50 * 1024 * 1024  # Bot API direct-send limit
LINK_TTL_HOURS = 24

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no confusing chars


# ---------- telegram helpers ----------

def api(method, payload=None, files=None, timeout=60):
    r = requests.post(f"{API}/{method}", data=payload or {},
                      files=files, timeout=timeout)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text[:200]}


def send_text(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return api("sendMessage", payload)


def send_photo(chat_id, photo_url, caption, reply_markup=None):
    payload = {"chat_id": chat_id, "photo": photo_url, "caption": caption,
               "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return api("sendPhoto", payload)


def send_document(chat_id, path, caption=""):
    with open(path, "rb") as f:
        return api("sendDocument",
                   {"chat_id": chat_id, "caption": caption[:1024],
                    "parse_mode": "HTML"},
                   files={"document": (os.path.basename(path), f)})


def answer_callback(cb_id, text=""):
    return api("answerCallbackQuery",
               {"callback_query_id": cb_id, "text": text[:200]})


def inline_kb(buttons):
    return {"inline_keyboard": buttons}


# ---------- invite codes ----------

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


def invite_link(code):
    return f"https://t.me/{BOT_USERNAME}?start={code}"


def is_owner(user_id):
    if ADMIN_CHAT_ID:
        return str(user_id) == str(ADMIN_CHAT_ID)
    codes = load_codes()
    owner = codes.get("__owner__", {}).get("used_by")
    return bool(owner) and str(user_id) == str(owner)


def is_activated(user_id):
    if is_owner(user_id):
        return True
    codes = load_codes()
    return any(e.get("used_by") == str(user_id) for k, e in codes.items()
               if not k.startswith("__"))


def redeem_code(code, user_id):
    code = (code or "").strip().upper()
    codes = load_codes()
    # First ever /start claims ownership when no owner exists yet.
    if not codes.get("__owner__", {}).get("used_by") and not ADMIN_CHAT_ID:
        codes["__owner__"] = {"used_by": str(user_id),
                              "used_at": _now_iso(), "label": "owner"}
        save_codes(codes)
        return "owner"
    entry = codes.get(code)
    if not entry or code.startswith("__"):
        return "invalid"
    exp = entry.get("expires_at")
    if exp and not entry.get("used_by"):
        try:
            if datetime.datetime.fromisoformat(exp) < datetime.datetime.now():
                return "expired"
        except ValueError:
            pass
    if str(entry.get("used_by")) == str(user_id):
        return "already_yours"
    if entry.get("used_by"):
        return "used"
    entry["used_by"] = str(user_id)
    entry["used_at"] = _now_iso()
    save_codes(codes)
    return "ok"


def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


GATE_MSG = (
    "🔒 This is a private bot.\n\n"
    "Open your personal invite link to activate it on this account."
)


# ---------- secure file delivery ----------

# token -> {"path":..., "name":..., "expires":...}
dl_tokens = {}
dl_lock = threading.Lock()

# item cache for download buttons: key -> item dict
item_cache = {}
item_lock = threading.Lock()


def public_base():
    return os.environ.get("PUBLIC_URL", "").strip().rstrip("/")


def mint_dl_token(path, name, hours=LINK_TTL_HOURS):
    token = secrets.token_urlsafe(16)
    with dl_lock:
        dl_tokens[token] = {
            "path": path, "name": name,
            "expires": time.time() + hours * 3600,
        }
    return token


app = Flask(__name__)


@app.route("/healthz")
def healthz():
    return {"ok": True, "service": "envato-bot",
            "time": _now_iso()}, 200


@app.route("/dl/<token>")
def download_file(token):
    with dl_lock:
        entry = dl_tokens.get(token)
    if not entry or entry["expires"] < time.time() or \
            not os.path.isfile(entry["path"]):
        abort(404)
    return send_file(entry["path"], as_attachment=True,
                     download_name=entry["name"])


def file_link(token):
    base = public_base()
    if not base:
        return None
    return f"{base}/dl/{token}"


# ---------- command handlers ----------

def handle_start(chat_id, user_id, args):
    if args:
        res = redeem_code(args[0], user_id)
        if res == "owner":
            send_text(chat_id,
                      "👑 You're the owner now. This bot is private to you.\n\n"
                      "Mint invite links for your other Telegram accounts:\n"
                      "<code>/newcodes 5</code>\n\n"
                      "Then <b>/search</b> to find Envato Elements assets.")
            return
        if res == "ok":
            send_text(chat_id,
                      "🎉 This account is activated!\n\n"
                      "Try <code>/search business presentation</code>")
            return
        if res == "already_yours":
            send_text(chat_id, "This invite link is already tied to this account. ✅")
            return
        if res == "expired":
            send_text(chat_id, "😕 That invite link expired (90-day validity). "
                               "Ask the owner for a fresh one.")
            return
        send_text(chat_id, "😕 That invite link is invalid or already used.")
        return
    # Plain /start: first user claims ownership when none exists yet.
    if not ADMIN_CHAT_ID and not load_codes().get("__owner__", {}).get("used_by"):
        res = redeem_code("", user_id)
        if res == "owner":
            send_text(chat_id,
                      "👑 You're the owner now. This bot is private to you.\n\n"
                      "Mint invite links for your other Telegram accounts:\n"
                      "<code>/newcodes 5</code>\n\n"
                      "Then <b>/search</b> to find Envato Elements assets.")
            return
    if is_activated(user_id):
        send_text(chat_id,
                  "👋 Envato Elements download bot.\n\n"
                  "<code>/search &lt;keywords&gt;</code> — find assets\n"
                  "<code>/recent</code> — your recent downloads\n"
                  "<code>/status</code> — Envato session health\n"
                  "<code>/newcodes 5</code> — invite links for your other accounts\n\n"
                  "Developed by Arkar Myowin")
    else:
        send_text(chat_id, GATE_MSG)


def handle_newcodes(chat_id, user_id, args):
    if not is_activated(user_id):
        send_text(chat_id, GATE_MSG)
        return
    try:
        n = max(1, min(50, int(args[0]) if args else 5))
    except ValueError:
        n = 5
    try:
        days = int(args[1]) if len(args) > 1 else 90
        days = max(1, min(365, days))
    except ValueError:
        days = 90
    codes = load_codes()
    fresh = []
    expires_at = (datetime.datetime.now() +
                  datetime.timedelta(days=days)).isoformat(timespec="seconds")
    for _ in range(n):
        c = make_code()
        codes[c] = {"used_by": None, "created_at": _now_iso(),
                    "expires_at": expires_at}
        fresh.append(c)
    save_codes(codes)
    lines = [f"🎟️ {n} single-use invite link(s) — valid {days} days, open one "
             f"on each of your Telegram accounts (no limit on how many):", ""]
    lines += [invite_link(c) for c in fresh]
    lines += ["", f"Usage: <code>/newcodes 5 30</code> for 30-day codes, "
                  f"<code>/newcodes 5 60</code> for 60-day."]
    send_text(chat_id, "\n".join(lines))


def handle_users(chat_id, user_id, args):
    if not is_activated(user_id):
        send_text(chat_id, GATE_MSG)
        return
    codes = load_codes()
    used = [(c, e) for c, e in codes.items()
            if not c.startswith("__") and e.get("used_by")]
    unused = sum(1 for c, e in codes.items()
                 if not c.startswith("__") and not e.get("used_by"))
    lines = [f"👥 Activated accounts: {len(used)}, unused invites: {unused}", ""]
    for c, e in used:
        lines.append(f"• <code>{c}</code> → {e['used_by']} "
                     f"({e.get('used_at', '?')})")
    send_text(chat_id, "\n".join(lines) if used else
              "No accounts activated yet (besides you).")


def handle_revoke(chat_id, user_id, args):
    if not is_activated(user_id):
        send_text(chat_id, GATE_MSG)
        return
    if not args:
        send_text(chat_id, "Usage: <code>/revoke CODE</code>")
        return
    code = args[0].strip().upper()
    codes = load_codes()
    entry = codes.get(code)
    if not entry or code.startswith("__") or not entry.get("used_by"):
        send_text(chat_id, "That code isn't tied to any account.")
        return
    uid = entry["used_by"]
    entry["used_by"] = None
    entry["revoked_at"] = _now_iso()
    save_codes(codes)
    send_text(chat_id, f"🚫 Deactivated account {uid} (code <code>{code}</code>).")


def handle_search(chat_id, user_id, args):
    if not is_activated(user_id):
        send_text(chat_id, GATE_MSG)
        return
    query = " ".join(args).strip()
    if not query:
        send_text(chat_id, "Usage: <code>/search business presentation</code>")
        return
    wait = send_text(chat_id, f"🔍 Searching Elements for “{html.escape(query)}”…")
    try:
        results = envato_client.search(query, limit=20)
    except envato_client.SessionExpired:
        send_text(chat_id, "⚠️ Envato session expired. Refresh it with "
                           "<code>/setcookie</code> (I'll walk you through it).")
        return
    except Exception as e:
        send_text(chat_id, f"😕 Search failed: {html.escape(str(e)[:200])}")
        return
    if not results:
        send_text(chat_id, "No results. Try different keywords.")
        return
    with item_lock:
        for item in results:
            key = secrets.token_urlsafe(8)
            item_cache[key] = item
            item["_key"] = key
    # Visual cards like the website: thumbnail + caption + download button.
    api("deleteMessage", {"chat_id": chat_id,
                          "message_id": wait.get("result", {}).get("message_id", 0)})
    send_text(chat_id, f"🔍 Top results for “{html.escape(query)}” — tap ⬇️ to download:")
    for i, item in enumerate(results, 1):
        kb = inline_kb([[{"text": "⬇️ Download",
                          "callback_data": f"dl:{item['_key']}"}]])
        caption = (f"<b>{html.escape(item['title'])}</b>\n"
                   f"👤 {html.escape(item.get('author', ''))} · "
                   f"🏷️ {html.escape(item.get('category', ''))}")
        thumb = item.get("thumb")
        if thumb:
            send_photo(chat_id, thumb, caption, reply_markup=kb)
        else:
            send_text(chat_id, caption, reply_markup=kb)


def do_download(chat_id, user_id, key):
    with item_lock:
        item = item_cache.get(key)
    if not item:
        send_text(chat_id, "😕 That result expired — please /search again.")
        return
    title = item["title"]
    send_text(chat_id, f"⬇️ Downloading <b>{html.escape(title)}</b>…")
    try:
        path, fname, lic_pdf = envato_client.download_item(item)
    except envato_client.SessionExpired:
        send_text(chat_id, "⚠️ Envato session expired. Refresh it with "
                           "<code>/setcookie</code>.")
        return
    except Exception as e:
        traceback.print_exc()
        send_text(chat_id, f"😕 Download failed: {html.escape(str(e)[:200])}")
        return
    size = os.path.getsize(path)
    caption = (f"📦 <b>{html.escape(fname)}</b>\n"
               f"📄 License: {html.escape(title)}")
    if size <= TG_FILE_LIMIT:
        send_document(chat_id, path, caption)
        if lic_pdf and os.path.isfile(lic_pdf):
            send_document(chat_id, lic_pdf, "📜 License certificate")
    else:
        token = mint_dl_token(path, fname)
        link = file_link(token)
        if link:
            send_text(chat_id,
                      f"{caption}\n\n"
                      f"📁 {size/1024/1024:.0f} MB — too big for Telegram, "
                      f"download here (valid {LINK_TTL_HOURS}h):\n{link}")
        else:
            send_text(chat_id,
                      f"{caption}\n\n⚠️ File is {size/1024/1024:.0f} MB and "
                      f"no public URL is configured — set PUBLIC_URL.")
        if lic_pdf and os.path.isfile(lic_pdf) and \
                os.path.getsize(lic_pdf) <= TG_FILE_LIMIT:
            send_document(chat_id, lic_pdf, "📜 License certificate")


def handle_status(chat_id, user_id, args):
    if not is_activated(user_id):
        send_text(chat_id, GATE_MSG)
        return
    try:
        ok, detail = envato_client.check_session()
    except Exception as e:
        ok, detail = False, str(e)[:200]
    send_text(chat_id,
              f"Envato session: {'✅ active' if ok else '❌ expired'}\n"
              f"{html.escape(detail)}\n\n"
              f"Refresh with <code>/setcookie</code> when needed.")


def handle_setcookie(chat_id, user_id, args):
    if not is_activated(user_id):
        send_text(chat_id, GATE_MSG)
        return
    cookie = " ".join(args).strip()
    if not cookie:
        send_text(chat_id,
                  "Paste your Envato session cookie after the command:\n"
                  "<code>/setcookie name1=value1; name2=value2</code>\n\n"
                  "To get it: log in at elements.envato.com in your browser, "
                  "open devtools → Application → Cookies, and copy the values.")
        return
    try:
        envato_client.save_cookie(cookie)
        ok, detail = envato_client.check_session()
    except Exception as e:
        send_text(chat_id, f"😕 Couldn't save it: {html.escape(str(e)[:200])}")
        return
    send_text(chat_id,
              f"Cookie saved. Session check: "
              f"{'✅ active' if ok else '❌ not working'}\n{html.escape(detail)}")


def handle_recent(chat_id, user_id, args):
    if not is_activated(user_id):
        send_text(chat_id, GATE_MSG)
        return
    files = sorted(
        (os.path.join(DOWNLOADS_DIR, f) for f in os.listdir(DOWNLOADS_DIR)
         if os.path.isfile(os.path.join(DOWNLOADS_DIR, f))
         and not f.endswith(".LICENSE.txt")),
        key=os.path.getmtime, reverse=True)[:10]
    if not files:
        send_text(chat_id, "No downloads yet. Try <code>/search</code> 🙂")
        return
    lines = ["🕘 Recent downloads (tap to get a fresh link):", ""]
    kb_buttons = []
    with item_lock:
        for path in files:
            key = secrets.token_urlsafe(8)
            item_cache["file:" + key] = {"file_path": path}
            kb_buttons.append([{"text": "🔗 " + os.path.basename(path)[:40],
                                "callback_data": f"fl:{key}"}])
    send_text(chat_id, "\n".join(lines), reply_markup=inline_kb(kb_buttons))


def handle_callback(cb):
    cb_id = cb["id"]
    chat_id = cb["message"]["chat"]["id"]
    user_id = cb["from"]["id"]
    data = cb.get("data", "")
    if not is_activated(user_id):
        answer_callback(cb_id, "Private bot — invite needed.")
        return
    answer_callback(cb_id)
    if data.startswith("dl:"):
        threading.Thread(target=do_download,
                         args=(chat_id, user_id, data[3:]),
                         daemon=True).start()
    elif data.startswith("fl:"):
        with item_lock:
            entry = item_cache.get("file:" + data[3:])
        if not entry:
            send_text(chat_id, "😕 Link expired — /recent again.")
            return
        path = entry["file_path"]
        token = mint_dl_token(path, os.path.basename(path))
        link = file_link(token)
        if link:
            send_text(chat_id, f"🔗 Fresh download link (valid {LINK_TTL_HOURS}h):\n{link}")
        else:
            send_text(chat_id, "⚠️ No PUBLIC_URL configured.")


COMMANDS = {
    "/start": handle_start,
    "/newcodes": handle_newcodes,
    "/users": handle_users,
    "/revoke": handle_revoke,
    "/search": handle_search,
    "/status": handle_status,
    "/setcookie": handle_setcookie,
    "/recent": handle_recent,
}


def handle_update(upd):
    try:
        if "callback_query" in upd:
            handle_callback(upd["callback_query"])
            return
        msg = upd.get("message", {})
        text = (msg.get("text") or "").strip()
        if not text:
            return
        chat_id = msg["chat"]["id"]
        user_id = msg["from"]["id"]
        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        args = parts[1:]
        handler = COMMANDS.get(cmd)
        if handler:
            handler(chat_id, user_id, args)
        elif is_activated(user_id):
            # Plain text = quick search.
            handle_search(chat_id, user_id, parts)
        else:
            send_text(chat_id, GATE_MSG)
    except Exception:
        traceback.print_exc()


def poll_forever():
    offset = 0
    while True:
        try:
            r = requests.get(f"{API}/getUpdates",
                             params={"offset": offset, "timeout": 30},
                             timeout=40).json()
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                threading.Thread(target=handle_update, args=(upd,),
                                 daemon=True).start()
        except Exception:
            traceback.print_exc()
            time.sleep(5)


def main():
    threading.Thread(target=poll_forever, daemon=True).start()
    print(f"envato-bot polling as @{BOT_USERNAME}, web on :{PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)


if __name__ == "__main__":
    main()
