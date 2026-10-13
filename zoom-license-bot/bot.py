#!/usr/bin/env python3
"""
Zoom License Monitor — Telegram bot.

Watches the license status (Licensed vs Basic) of a set of Zoom accounts via
Zoom OAuth (one app, authorized once per account) and alerts the admin when a
license lapses.

How it works:
  1. A Zoom OAuth app (user-managed) is created once in the Zoom Marketplace
     with redirect URI = ZOOM_REDIRECT_URI and scope `user:read`.
  2. Each Zoom account authorizes the app once (via /reauth link or a browser
     session). The OAuth callback (/oauth/callback) captures the code and the
     bot stores the refresh token (Fernet-encrypted) per account.
  3. /check (or the daily auto-check) calls GET /v2/users/me for each stored
     refresh token and reads the `type` field: 1 = Basic, 2 = Licensed.
  4. Any status change since the last check is reported to the admin.

Env vars:
    BOT_TOKEN         Telegram bot token from @BotFather (required)
    ADMIN_CHAT_ID     Telegram user id allowed to use the bot (required)
    ZOOM_CLIENT_ID    Zoom OAuth app client id (required)
    ZOOM_CLIENT_SECRET Zoom OAuth app client secret (required)
    ZOOM_REDIRECT_URI e.g. https://zoom-license.example.up.railway.app/oauth/callback (required)
    ENCRYPTION_KEY    Fernet key for token storage (required; generate with
                      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    DATA_DIR          Directory for tokens.json (default ./data; on Railway use /data volume)
    CHECK_HOUR        Hour (Asia/Bangkok) for the daily auto-check (default 9)

Run: pip install -r requirements.txt && python bot.py
Railway: Procfile `web: python bot.py`, volume mounted at /data, DATA_DIR=/data
"""

import base64
import datetime
import json
import logging
import os
import threading
import time
import urllib.parse

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, request

# ---------------------------------------------------------------- config

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID", "").strip()
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET", "").strip()
ZOOM_REDIRECT_URI = os.environ.get("ZOOM_REDIRECT_URI", "").strip()
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "").strip()
DATA_DIR = os.environ.get("DATA_DIR", "./data").strip() or "./data"
CHECK_HOUR = int(os.environ.get("CHECK_HOUR", "9") or 9)

for name, val in [("BOT_TOKEN", BOT_TOKEN), ("ADMIN_CHAT_ID", ADMIN_CHAT_ID),
                  ("ZOOM_CLIENT_ID", ZOOM_CLIENT_ID), ("ZOOM_CLIENT_SECRET", ZOOM_CLIENT_SECRET),
                  ("ZOOM_REDIRECT_URI", ZOOM_REDIRECT_URI), ("ENCRYPTION_KEY", ENCRYPTION_KEY)]:
    if not val:
        raise SystemExit(f"Set the {name} env var.")

try:
    FERNET = Fernet(ENCRYPTION_KEY.encode())
except Exception as e:
    raise SystemExit(f"ENCRYPTION_KEY is not a valid Fernet key: {e}")

os.makedirs(DATA_DIR, exist_ok=True)
STORE_PATH = os.path.join(DATA_DIR, "tokens.json")

# Seed list for the first batch of accounts. The bot is not limited to these:
# ANY account that authorizes the Zoom app is added to the registry dynamically
# (the OAuth callback stores by the email Zoom reports) and included in checks.
SEED_EMAILS = [
    "onlineclass.22517+c53@gmail.com",
    "onlineclass.22517+c54@gmail.com",
    "onlineclass.22517+c55@gmail.com",
    "onlineclass.22517+c56@gmail.com",
    "onlineclass.22517+c57@gmail.com",
    "onlineclass.22517+c58@gmail.com",
    "onlineclass.22517+c59@gmail.com",
    "onlineclass.22517+c60@gmail.com",
    "onlineclass.22517+c61@gmail.com",
    "onlineclass.22517+c62@gmail.com",
    "onlineclass.22517+c63@gmail.com",
    "onlineclass.22517+c64@gmail.com",
    "onlineclass.22517+c65@gmail.com",
    "onlineclass.22517+c66@gmail.com",
    "onlineclass.22517+c67@gmail.com",
]

ZOOM_AUTH_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_ME_URL = "https://api.zoom.us/v2/users/me"

TYPE_NAMES = {1: "Basic", 2: "Licensed", 3: "On-prem"}
BKK = datetime.timezone(datetime.timedelta(hours=7))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("zoom-license-bot")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
store_lock = threading.Lock()

# ---------------------------------------------------------------- store

def load_store():
    with store_lock:
        if not os.path.exists(STORE_PATH):
            return {"accounts": {}, "alerts_on": True}
        try:
            with open(STORE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("accounts", {})
            data.setdefault("alerts_on", True)
            return data
        except Exception as e:
            log.warning("Could not read store: %s", e)
            return {"accounts": {}, "alerts_on": True}


def save_store(data):
    with store_lock:
        tmp = STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, STORE_PATH)


def enc(s: str) -> str:
    return FERNET.encrypt(s.encode()).decode()


def dec(s: str) -> str:
    return FERNET.decrypt(s.encode()).decode()

# ---------------------------------------------------------------- zoom api

def _basic_auth():
    raw = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def zoom_token_request(payload):
    r = requests.post(
        ZOOM_TOKEN_URL,
        headers={"Authorization": _basic_auth(),
                 "Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def exchange_code(code):
    return zoom_token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ZOOM_REDIRECT_URI,
    })


def refresh_tokens(refresh_token):
    return zoom_token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })


def get_me(access_token):
    r = requests.get(ZOOM_ME_URL,
                     headers={"Authorization": f"Bearer {access_token}"},
                     timeout=30)
    if r.status_code == 401:
        return None  # token dead
    r.raise_for_status()
    return r.json()


def authorize_url(state=""):
    q = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": ZOOM_CLIENT_ID,
        "redirect_uri": ZOOM_REDIRECT_URI,
        # granular scope as granted in the Marketplace (legacy "user:read"
        # no longer exists in the scope picker)
        "scope": "user:read:user",
        "state": state,
    })
    return f"{ZOOM_AUTH_URL}?{q}"


def check_one_account(email, acc):
    """Returns (status, detail). status in: Licensed, Basic, NEEDS_REAUTH, ERROR."""
    try:
        rt = dec(acc["refresh_token"])
    except (InvalidToken, KeyError) as e:
        return "ERROR", f"cannot decrypt stored token: {e}"
    try:
        toks = refresh_tokens(rt)
    except requests.HTTPError as e:
        body = getattr(e.response, "text", "")[:200]
        if e.response is not None and e.response.status_code in (400, 401):
            return "NEEDS_REAUTH", f"refresh rejected ({body})"
        return "ERROR", f"refresh failed: {e} {body}"
    except Exception as e:
        return "ERROR", f"refresh failed: {e}"
    new_rt = toks.get("refresh_token")
    access = toks.get("access_token")
    if not access:
        return "ERROR", "no access_token in refresh response"
    # persist rotated refresh token
    if new_rt and new_rt != rt:
        store = load_store()
        if email in store["accounts"]:
            store["accounts"][email]["refresh_token"] = enc(new_rt)
            save_store(store)
    try:
        me = get_me(access)
    except Exception as e:
        return "ERROR", f"users/me failed: {e}"
    if me is None:
        return "NEEDS_REAUTH", "access token rejected"
    t = me.get("type")
    name = TYPE_NAMES.get(t, f"Unknown({t})")
    return name, me.get("email", "")


def check_all():
    """Check every registered account (seed list + any that authorized).
    Runs with a small thread pool so 100s of accounts finish in ~1-2 min."""
    from concurrent.futures import ThreadPoolExecutor
    store = load_store()
    emails = sorted(set(SEED_EMAILS) | set(store["accounts"].keys()))

    def _one(email):
        acc = store["accounts"].get(email)
        if not acc or not acc.get("refresh_token"):
            return email, ("NOT_AUTHORIZED", "app not authorized for this account yet")
        try:
            return email, check_one_account(email, acc)
        except Exception as e:  # never let one account kill the sweep
            log.exception("check failed for %s", email)
            return email, ("ERROR", str(e)[:200])

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for email, res in pool.map(_one, emails):
            results[email] = res
    return results

# ---------------------------------------------------------------- telegram

def tg(method, **params):
    r = requests.post(f"{TG_API}/{method}", json=params, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False}


def send(chat_id, text):
    # split long messages
    for i in range(0, len(text), 3900):
        tg("sendMessage", chat_id=chat_id, text=text[i:i + 3900])


def is_admin(msg):
    return str(msg.get("from", {}).get("id", "")) == str(ADMIN_CHAT_ID)


def short_email(email):
    # onlineclass.22517+c62@gmail.com -> c62
    m = email.split("+")
    if len(m) > 1:
        return m[1].split("@")[0]
    return email


def _id_list(emails, limit=25):
    ids = [short_email(e) for e in sorted(emails)]
    if len(ids) > limit:
        return ", ".join(ids[:limit]) + f" …(+{len(ids) - limit} more)"
    return ", ".join(ids) or "—"


def fmt_table(results, show_detail=False):
    lic = [e for e, (s, _) in results.items() if s == "Licensed"]
    bas = [e for e, (s, _) in results.items() if s == "Basic"]
    other = [(e, s, d) for e, (s, d) in results.items() if s not in ("Licensed", "Basic")]
    total = len(results)
    lines = [f"\U0001f50d Zoom licenses — {datetime.datetime.now(BKK):%d %b %H:%M} "
             f"(Bangkok) — {total} accounts", ""]
    lines.append(f"\u2705 Licensed ({len(lic)}): " + _id_list(lic))
    lines.append(f"\u26aa Basic ({len(bas)}): " + _id_list(bas))
    for e, s, d in sorted(other):
        line = f"\u2753 {short_email(e)}: {s}"
        if show_detail and d:
            line += f" — {d[:100]}"
        lines.append(line)
    return "\n".join(lines)


def fmt_changes(changes):
    """changes: list of (email, old, new, detail). Compact for large fleets."""
    lines = ["\u26a0\ufe0f Zoom license changes detected:"]
    for email, old, new, detail in changes[:30]:
        line = f"{short_email(email)}: {old} → {new}"
        if detail:
            line += f" ({detail[:100]})"
        lines.append(line)
    if len(changes) > 30:
        lines.append(f"…(+{len(changes) - 30} more)")
    return "\n".join(lines)


def handle_message(msg):
    chat_id = msg["chat"]["id"]
    if not is_admin(msg):
        return
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/start":
        send(chat_id,
             "\U0001f50d Zoom License Monitor\n\n"
             "Watches your Zoom accounts and alerts you when a license lapses.\n\n"
             "/check — check all licenses now\n"
             "/status — last known statuses (no API calls)\n"
             "/accounts — authorization coverage\n"
             "/list licensed|basic|problems — list accounts by status\n"
             "/reauth <email|c62> — authorize link for one account\n"
             "/alerts on|off — daily auto-check alerts")
    elif cmd == "/check":
        send(chat_id, "\u23f3 Checking all accounts, this takes a minute or so...")
        results = check_all()
        store = load_store()
        prev = {e: a.get("last_type") for e, a in store["accounts"].items()}
        changes = []
        for email, (status, detail) in results.items():
            if status in ("Licensed", "Basic") and prev.get(email) and prev[email] != status:
                changes.append((email, prev[email], status, ""))
            if status in ("Licensed", "Basic"):
                store["accounts"].setdefault(email, {})["last_type"] = status
                store["accounts"][email]["last_check"] = datetime.datetime.now(
                    datetime.timezone.utc).isoformat()
        save_store(store)
        out = fmt_table(results)
        if changes:
            out += "\n\n" + fmt_changes(changes)
        send(chat_id, out)
    elif cmd == "/status":
        store = load_store()
        emails = sorted(set(SEED_EMAILS) | set(store["accounts"].keys()))
        counts = {}
        for e in emails:
            st = store["accounts"].get(e, {}).get("last_type", "unknown")
            counts[st] = counts.get(st, 0) + 1
        lines = ["\U0001f4cb Last known statuses: "
                 + ", ".join(f"{k} ({v})" for k, v in sorted(counts.items()))]
        # show detail only for non-OK accounts to stay compact
        for e in emails:
            a = store["accounts"].get(e, {})
            st = a.get("last_type", "unknown")
            if st not in ("Licensed", "Basic"):
                lines.append(f"{short_email(e)}: {st}")
        send(chat_id, "\n".join(lines))
    elif cmd == "/list":
        store = load_store()
        f = arg.lower()
        emails = sorted(set(SEED_EMAILS) | set(store["accounts"].keys()))
        if f == "licensed":
            ids = [e for e in emails if store["accounts"].get(e, {}).get("last_type") == "Licensed"]
            send(chat_id, f"\u2705 Licensed ({len(ids)}):\n" + _id_list(ids, limit=200))
        elif f == "basic":
            ids = [e for e in emails if store["accounts"].get(e, {}).get("last_type") == "Basic"]
            send(chat_id, f"\u26aa Basic ({len(ids)}):\n" + _id_list(ids, limit=200))
        elif f in ("problems", "problem"):
            lines = ["\u2753 Needs attention:"]
            for e in emails:
                a = store["accounts"].get(e, {})
                st = a.get("last_type", "unknown")
                if st not in ("Licensed", "Basic"):
                    lines.append(f"{short_email(e)}: {st}")
            send(chat_id, "\n".join(lines) if len(lines) > 1 else "\u2705 No problem accounts.")
        else:
            send(chat_id, "Usage: /list licensed|basic|problems")
    elif cmd == "/accounts":
        store = load_store()
        emails = sorted(set(SEED_EMAILS) | set(store["accounts"].keys()))
        ok = sum(1 for e in emails if store["accounts"].get(e, {}).get("refresh_token"))
        send(chat_id,
             f"Authorized: {ok}/{len(emails)} accounts.\n"
             f"Use /reauth <full email> to authorize another account.")
    elif cmd == "/reauth":
        target = arg.strip().lower()
        if "@" in target:
            email = target
        else:
            email = next((e for e in sorted(set(SEED_EMAILS) | set(load_store()["accounts"].keys()))
                          if short_email(e) == target), None)
        if not email or "@" not in email:
            send(chat_id, f"Unknown account '{arg}'. Use /reauth <full email>, e.g. /reauth onlineclass.22517+c99@gmail.com")
            return
        url = authorize_url(state=short_email(email))
        send(chat_id,
             f"Open this link while signed in to Zoom as {email}, then click Authorize:\n{url}\n\n"
             f"I'll capture the token automatically when Zoom redirects back.")
    elif cmd == "/alerts":
        store = load_store()
        if arg.lower() == "off":
            store["alerts_on"] = False
            save_store(store)
            send(chat_id, "\U0001f515 Daily auto-check alerts OFF.")
        else:
            store["alerts_on"] = True
            save_store(store)
            send(chat_id, "\U0001f514 Daily auto-check alerts ON.")
    else:
        send(chat_id, "Unknown command. Try /check, /status, /accounts, /reauth, /alerts.")


def poll_loop():
    offset = 0
    log.info("Telegram polling started")
    while True:
        try:
            r = requests.post(f"{TG_API}/getUpdates",
                              json={"offset": offset, "timeout": 50}, timeout=70)
            data = r.json()
            if not data.get("ok"):
                time.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message")
                if msg:
                    try:
                        handle_message(msg)
                    except Exception:
                        log.exception("handler error")
        except Exception:
            log.exception("poll error")
            time.sleep(5)

# ---------------------------------------------------------------- scheduler

def daily_check_job():
    """Runs every minute; fires the auto-check once per day at CHECK_HOUR BKK."""
    last_run_date = None
    while True:
        try:
            now = datetime.datetime.now(BKK)
            if now.hour == CHECK_HOUR and now.minute < 2 and last_run_date != now.date():
                last_run_date = now.date()
                store = load_store()
                if not store.get("alerts_on", True):
                    log.info("alerts off, skipping daily check")
                    continue
                if not any(a.get("refresh_token") for a in store["accounts"].values()):
                    log.info("no authorized accounts yet, skipping daily check")
                    continue
                log.info("running daily license check")
                results = check_all()
                prev = {e: a.get("last_type") for e, a in store["accounts"].items()}
                changes = []
                for email, (status, detail) in results.items():
                    if status in ("Licensed", "Basic"):
                        if prev.get(email) and prev[email] != status:
                            changes.append((email, prev[email], status, ""))
                        store["accounts"].setdefault(email, {})["last_type"] = status
                        store["accounts"][email]["last_check"] = datetime.datetime.now(
                            datetime.timezone.utc).isoformat()
                    elif status in ("NEEDS_REAUTH", "ERROR"):
                        changes.append((email, prev.get(email, "?"), status, detail))
                save_store(store)
                if changes:
                    send(ADMIN_CHAT_ID, fmt_changes(changes) + "\n\n" + fmt_table(results))
                else:
                    n_lic = sum(1 for s, _ in results.values() if s == "Licensed")
                    n_bas = sum(1 for s, _ in results.values() if s == "Basic")
                    send(ADMIN_CHAT_ID,
                         f"\u2705 Daily Zoom check: no changes. "
                         f"{n_lic} Licensed, {n_bas} Basic, {len(results)} total.")
        except Exception:
            log.exception("daily check error")
        time.sleep(60)

# ---------------------------------------------------------------- flask (oauth callback + health)

app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/oauth/callback")
def oauth_callback():
    code = request.args.get("code", "")
    err = request.args.get("error", "")
    state = request.args.get("state", "")
    if err or not code:
        return f"Authorization failed: {err or 'no code returned'}. You can close this tab.", 400
    try:
        toks = exchange_code(code)
    except Exception as e:
        log.exception("code exchange failed")
        return f"Token exchange failed: {e}. You can close this tab.", 400
    rt = toks.get("refresh_token")
    access = toks.get("access_token")
    if not rt or not access:
        return "Zoom did not return tokens. You can close this tab.", 400
    try:
        me = get_me(access)
    except Exception as e:
        return f"Could not read Zoom user: {e}. You can close this tab.", 400
    email = (me or {}).get("email", "").strip().lower()
    if not email:
        return "Could not determine the Zoom account email. You can close this tab.", 400
    store = load_store()
    acc = store["accounts"].setdefault(email, {})
    acc["refresh_token"] = enc(rt)
    acc["zoom_user_id"] = me.get("id", "")
    acc["display_name"] = me.get("display_name", "")
    save_store(store)
    log.info("captured OAuth token for %s (state=%s)", email, state)
    try:
        send(ADMIN_CHAT_ID,
             f"\u2705 Zoom account authorized: {email} "
             f"({TYPE_NAMES.get(me.get('type'), me.get('type'))})")
    except Exception:
        pass
    done = sum(1 for a in store["accounts"].values() if a.get("refresh_token"))
    return (f"Authorized {email} successfully! You can close this tab.<br><br>"
            f"{done} account(s) connected so far."), 200


def main():
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=daily_check_job, daemon=True).start()
    port = int(os.environ.get("PORT", "5000"))
    log.info("starting Flask on port %s", port)
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
