#!/usr/bin/env python3
"""
Zoom License Monitor — Telegram bot.

Watches the license status (Licensed vs Basic) of a fleet of Zoom accounts
and alerts the admin when a license lapses.

Two data paths (OAuth is the future; sweeps work today):
  A. Zoom OAuth (one app, authorized once per account). The OAuth callback
     (/oauth/callback) captures the code and the bot stores the refresh token
     (Fernet-encrypted) per account. Live checks call GET /v2/users/me.
  B. Credential sweeps: a scheduled browser job signs into each account and
     reads the license status, then POSTs results to /ingest (protected by
     INGEST_SECRET). The bot records them and alerts on changes.

Env vars:
    BOT_TOKEN         Telegram bot token from @BotFather (required)
    ADMIN_CHAT_ID     Telegram user id allowed to use the bot (required)
    ZOOM_CLIENT_ID    Zoom OAuth app client id (required)
    ZOOM_CLIENT_SECRET Zoom OAuth app client secret (required)
    ZOOM_REDIRECT_URI e.g. https://zoom-license.example.up.railway.app/oauth/callback (required)
    ENCRYPTION_KEY    Fernet key for token storage (required; generate with
                      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    DATA_DIR          Directory for tokens.json (default ./data; on Railway use /data volume)
    CHECK_HOUR        Hour (Asia/Bangkok) for the daily summary (default 9)
    INGEST_SECRET     Shared secret protecting POST /ingest (required)

Run: pip install -r requirements.txt && python bot.py
Railway: Procfile `web: python bot.py`, volume mounted at /data, DATA_DIR=/data
"""

import base64
import datetime
import json
import logging
import os
import re
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
INGEST_SECRET = os.environ.get("INGEST_SECRET", "").strip()

for name, val in [("BOT_TOKEN", BOT_TOKEN), ("ADMIN_CHAT_ID", ADMIN_CHAT_ID),
                  ("ZOOM_CLIENT_ID", ZOOM_CLIENT_ID), ("ZOOM_CLIENT_SECRET", ZOOM_CLIENT_SECRET),
                  ("ZOOM_REDIRECT_URI", ZOOM_REDIRECT_URI), ("ENCRYPTION_KEY", ENCRYPTION_KEY),
                  ("INGEST_SECRET", INGEST_SECRET)]:
    if not val:
        raise SystemExit(f"Set the {name} env var.")

try:
    FERNET = Fernet(ENCRYPTION_KEY.encode())
except Exception as e:
    raise SystemExit(f"ENCRYPTION_KEY is not a valid Fernet key: {e}")

os.makedirs(DATA_DIR, exist_ok=True)
STORE_PATH = os.path.join(DATA_DIR, "tokens.json")

# Diagnostic / non-fleet records to always ignore
# (probe@test.com was inserted by a live diagnostic 2026-10-13)
EXCLUDED_EMAILS = {"probe@test.com"}


def fleet_emails(store):
    return sorted((set(SEED_EMAILS) | set(store["accounts"].keys())) - EXCLUDED_EMAILS)


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
    # Exact format of the Marketplace-generated install URL. NOTE: do NOT add
    # a scope parameter — the hand-built URL with scope=user:read:user failed
    # with "Application not found" for non-owner accounts (2026-10-13); the
    # generated URL without scope works and applies the app's configured scopes.
    q = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": ZOOM_CLIENT_ID,
        "redirect_uri": ZOOM_REDIRECT_URI,
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
    emails = fleet_emails(store)

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


def send(chat_id, text, parse_mode=None, silent=False):
    # split long messages
    for i in range(0, len(text), 3900):
        kw = {"chat_id": chat_id, "text": text[i:i + 3900],
              "disable_notification": silent}
        if parse_mode:
            kw["parse_mode"] = parse_mode
        tg("sendMessage", **kw)


def is_admin(msg):
    uid = str(msg.get("from", {}).get("id", ""))
    # Support comma-separated ADMIN_CHAT_IDS for multiple accounts
    ids = [x.strip() for x in os.environ.get("ADMIN_CHAT_IDS", "").split(",") if x.strip()]
    if not ids:
        ids = [str(ADMIN_CHAT_ID)]
    return uid in ids


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


LICENSE_CYCLE_DAYS = 14
WARN_DAYS_BEFORE = 1


def _parse_ts(ts):
    try:
        dt = datetime.datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return None


def account_expiry_date(acc):
    """Effective license expiry date for an account, or None if unknown.

    Prefers the real expiration date from billing settings; falls back to
    licensed_since + 14 days.
    """
    exp = _parse_ts(acc.get("license_expires_at"))
    if exp:
        return exp.date()
    since = _parse_ts(acc.get("licensed_since"))
    if since:
        return (since + datetime.timedelta(days=LICENSE_CYCLE_DAYS)).date()
    return None


def expiry_warnings(store, now=None):
    """Accounts whose license expires tomorrow (or is overdue).

    Returns list of (email, days_left, kind) where kind is
    'expiring' (1 day left) or 'overdue' (expired but still marked Licensed).
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    warns = []
    for email, acc in store["accounts"].items():
        if acc.get("last_type") != "Licensed":
            continue
        exp_date = account_expiry_date(acc)
        if not exp_date:
            continue
        days_left = (exp_date - today).days
        if days_left == WARN_DAYS_BEFORE:
            warns.append((email, days_left, "expiring"))
        elif days_left <= 0:
            warns.append((email, days_left, "overdue"))
    return sorted(warns)


def fmt_warnings(warns):
    exp = [(e, d) for e, d, k in warns if k == "expiring"]
    over = [(e, d) for e, d, k in warns if k == "overdue"]
    lines = []
    if exp:
        lines.append(f"\u23f0 {len(exp)} license(s) expire TOMORROW:")
        lines.append(_id_list([e for e, _ in exp], limit=40))
    if over:
        lines.append(f"\u26a0\ufe0f {len(over)} license(s) expired but still show Licensed — verify:")
        lines.append(_id_list([e for e, _ in over], limit=40))
    return "\n".join(lines)


def handle_message(msg):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return
    if not is_admin(msg):
        # Reply (not silent) so a wrong ADMIN_CHAT_ID is diagnosable.
        if text.split()[0].split("@")[0].lower() == "/start":
            uid = msg.get("from", {}).get("id", "?")
            send(chat_id, f"This bot is private. (your id: {uid})")
        return
    parts = text.split()
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/start":
        send(chat_id,
             "\U0001f50d Zoom License Monitor\n\n"
             "Watches your Zoom accounts and alerts you when a license lapses.\n"
             "Statuses come from periodic license sweeps (change alerts are\n"
             "sent automatically when a sweep finds one).\n\n"
             "/check — last known license statuses\n"
             "/status — status counts summary\n"
             "/accounts — authorization coverage\n"
             "/list licensed|basic|problems — list accounts by status\n"
             "/expiring — licenses expiring within 2 days\n"
             "/backdate YYYY-MM-DD — fallback: set license start date for\n"
             "  currently-Licensed accounts lacking a real expiration date\n"
             "/renewed [YYYY-MM-DD] id1 id2 ... — stamp the accounts YOU\n"
             "  just renewed with a fresh 14-day clock (only those)\n"
             "/reauth <email> — authorize link (for OAuth mode)\n"
             "/alerts on|off — change alerts on/off")
    elif cmd == "/check":
        store = load_store()
        oauth_accounts = [e for e, a in store["accounts"].items() if a.get("refresh_token")]
        if oauth_accounts:
            send(chat_id, "\u23f3 Checking OAuth-linked accounts live...")
            results = {}
            for email in sorted(oauth_accounts):
                try:
                    results[email] = check_one_account(email, store["accounts"][email])
                except Exception as e:
                    results[email] = ("ERROR", str(e)[:200])
            for email, (status, _) in results.items():
                if status in ("Licensed", "Basic"):
                    store["accounts"][email]["last_type"] = status
                    store["accounts"][email]["last_check"] = datetime.datetime.now(
                        datetime.timezone.utc).isoformat()
            save_store(store)
            send(chat_id, fmt_table(results) + "\n\n(live OAuth check)")
        else:
            # Sweep mode: report last known results from credential sweeps.
            results = {}
            for email in fleet_emails(store):
                a = store["accounts"].get(email, {})
                st = a.get("last_type")
                if st in ("Licensed", "Basic"):
                    results[email] = (st, "")
                else:
                    results[email] = (a.get("sweep_status") or "UNKNOWN",
                                      a.get("sweep_detail") or "no sweep data yet")
            out = fmt_table(results)
            ls = store.get("last_sweep_at", "")
            out += f"\n\nLast sweep: {ls[:16].replace('T', ' ')} UTC" if ls else "\n\nNo sweep yet."
            send(chat_id, out)
    elif cmd == "/status":
        store = load_store()
        emails = fleet_emails(store)
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
        parts_l = arg.lower().split()
        f = parts_l[0] if parts_l else ""
        full = "full" in parts_l
        def _fmt(emails, limit=200):
            if full:
                # one per line in a code block — tap to copy in Telegram
                lst = sorted(emails)
                body = "\n".join(lst[:limit])
                if len(lst) > limit:
                    body += f"\n…(+{len(lst) - limit} more)"
                return "```\n" + body + "\n```" if body else "—"
            lst = [short_email(e) for e in sorted(emails)]
            if len(lst) > limit:
                return ", ".join(lst[:limit]) + f" …(+{len(lst) - limit} more)"
            return ", ".join(lst) or "—"
        emails = fleet_emails(store)
        pm = "Markdown" if full else None
        if f == "licensed":
            ids = [e for e in emails if store["accounts"].get(e, {}).get("last_type") == "Licensed"]
            send(chat_id, f"\u2705 Licensed ({len(ids)}):\n" + _fmt(ids), parse_mode=pm)
        elif f == "basic":
            ids = [e for e in emails if store["accounts"].get(e, {}).get("last_type") == "Basic"]
            send(chat_id, f"\u26aa Basic ({len(ids)}):\n" + _fmt(ids), parse_mode=pm)
        elif f in ("problems", "problem"):
            lines = ["\u2753 Needs attention:"]
            for e in emails:
                a = store["accounts"].get(e, {})
                st = a.get("last_type", "unknown")
                if st not in ("Licensed", "Basic"):
                    lines.append(f"{e if full else short_email(e)}: {st}")
            send(chat_id, "\n".join(lines) if len(lines) > 1 else "\u2705 No problem accounts.")
        else:
            send(chat_id, "Usage: /list licensed|basic|problems [full]")
    elif cmd == "/expiring":
        store = load_store()
        warns = expiry_warnings(store)
        if not warns:
            send(chat_id, "\u2705 No licenses expiring within the next 2 days.")
        else:
            send(chat_id, fmt_warnings(warns))
    elif cmd == "/backdate":
        # /backdate 2026-10-10 -> licensed_since = that date 00:00 UTC
        # for all currently-Licensed accounts.
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", arg.strip())
        if not m:
            send(chat_id, "Usage: /backdate YYYY-MM-DD\n"
                         "Sets the 14-day clock start for all currently-Licensed accounts.")
            return
        try:
            dt = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                   tzinfo=datetime.timezone.utc)
        except ValueError:
            send(chat_id, "Invalid date. Usage: /backdate YYYY-MM-DD")
            return
        if dt > datetime.datetime.now(datetime.timezone.utc):
            send(chat_id, "Date can't be in the future.")
            return
        store = load_store()
        n = 0
        for acc in store["accounts"].values():
            if acc.get("last_type") == "Licensed":
                acc["licensed_since"] = dt.isoformat()
                n += 1
        save_store(store)
        send(chat_id, f"\u2705 14-day clock set to {arg} for {n} Licensed account(s). "
                      f"Expiry warnings will fire 1 day before day 14.")
    elif cmd == "/renewed":
        # /renewed [YYYY-MM-DD] id1 id2 ... — stamp a fresh 14-day clock for
        # ONLY the named accounts (the ones you just renewed manually).
        # This is the safe alternative to /backdate, which resets the clock
        # for every Licensed account at once.
        tokens = [t for t in parts[1:]]
        renewal_date = None
        if tokens and re.match(r"^(\d{4})-(\d{2})-(\d{2})$", tokens[0]):
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", tokens[0])
            try:
                renewal_date = datetime.date(int(m.group(1)), int(m.group(2)),
                                            int(m.group(3)))
                tokens = tokens[1:]
            except ValueError:
                send(chat_id, "Invalid date. Usage: /renewed [YYYY-MM-DD] id1 id2 ...")
                return
        if renewal_date is None:
            renewal_date = datetime.datetime.now(datetime.timezone.utc).date()
        if renewal_date > datetime.datetime.now(datetime.timezone.utc).date():
            send(chat_id, "Date can't be in the future.")
            return
        if not tokens:
            send(chat_id, "Usage: /renewed [YYYY-MM-DD] id1 id2 ...\n"
                          "Example: /renewed c35 c37 c38")
            return
        store = load_store()
        by_id = {}
        for email in store["accounts"]:
            by_id.setdefault(short_email(email).lower(), email)
        new_exp = (renewal_date + datetime.timedelta(days=LICENSE_CYCLE_DAYS)).isoformat()
        stamped, flipped, unknown = [], [], []
        for tid in tokens:
            email = by_id.get(tid.lower())
            if not email:
                unknown.append(tid)
                continue
            acc = store["accounts"][email]
            was = acc.get("last_type")
            acc["license_expires_at"] = new_exp
            acc["last_type"] = "Licensed"
            acc["last_check"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            (flipped if was != "Licensed" else stamped).append(short_email(email))
        save_store(store)
        lines = [f"\u2705 Renewal recorded ({renewal_date.isoformat()} \u2192 expires {new_exp}):"]
        if stamped:
            lines.append("Stamped: " + ", ".join(sorted(stamped)))
        if flipped:
            lines.append("Basic \u2192 Licensed: " + ", ".join(sorted(flipped)))
        if unknown:
            lines.append("\u2753 Unknown IDs (not stamped): " + ", ".join(unknown))
        send(chat_id, "\n".join(lines))
    elif cmd == "/accounts":
        store = load_store()
        emails = fleet_emails(store)
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
    """Runs every minute; at CHECK_HOUR BKK sends the daily license summary.

    In sweep mode this summarizes the last sweep (change alerts are sent at
    ingest time). If any accounts have OAuth tokens, they are checked live.
    """
    last_run_date = None
    while True:
        try:
            now = datetime.datetime.now(BKK)
            if now.hour == CHECK_HOUR and now.minute < 2 and last_run_date != now.date():
                last_run_date = now.date()
                store = load_store()
                if not store.get("alerts_on", True):
                    log.info("alerts off, skipping daily summary")
                    continue
                oauth_accounts = [e for e, a in store["accounts"].items()
                                  if a.get("refresh_token")]
                if oauth_accounts:
                    log.info("running daily live OAuth check")
                    results = {}
                    for email in sorted(oauth_accounts):
                        try:
                            results[email] = check_one_account(email, store["accounts"][email])
                        except Exception as e:
                            results[email] = ("ERROR", str(e)[:200])
                    prev = {e: a.get("last_type") for e, a in store["accounts"].items()}
                    changes = []
                    for email, (status, detail) in results.items():
                        if status in ("Licensed", "Basic"):
                            if prev.get(email) and prev[email] != status:
                                changes.append((email, prev[email], status, ""))
                            store["accounts"][email]["last_type"] = status
                            store["accounts"][email]["last_check"] = datetime.datetime.now(
                                datetime.timezone.utc).isoformat()
                    save_store(store)
                    if changes:
                        send(ADMIN_CHAT_ID, fmt_changes(changes))
                        continue
                # Sweep-mode summary (also sent when live check found no changes)
                counts = {}
                for a in store["accounts"].values():
                    st = a.get("last_type", "unknown")
                    counts[st] = counts.get(st, 0) + 1
                ls = store.get("last_sweep_at", "")
                total = sum(counts.values())
                if total == 0:
                    send(ADMIN_CHAT_ID,
                         "\u2705 Daily Zoom summary: no accounts tracked yet. "
                         "Run a sweep to populate license statuses.")
                else:
                    summary = ", ".join(f"{k} ({v})" for k, v in sorted(counts.items()))
                    when = f"swept {ls[:16].replace('T', ' ')} UTC" if ls else "no sweep yet"
                    send(ADMIN_CHAT_ID,
                         f"\u2705 Daily Zoom summary ({total} accounts, {when}): {summary}.")
                # 1-day advance expiry warnings (14-day license cycle).
                # Each expiry warns once (ingest-time urgent alerts and the
                # daily job share the warned_for_expiry marker).
                warns = expiry_warnings(store)
                fresh = []
                for email, dl, kind in warns:
                    acc = store["accounts"][email]
                    exp_date = account_expiry_date(acc)
                    key = exp_date.isoformat() if exp_date else None
                    if acc.get("warned_for_expiry") != key:
                        fresh.append((email, dl, kind))
                        if key:
                            acc["warned_for_expiry"] = key
                if fresh:
                    save_store(store)
                    if store.get("alerts_on", True):
                        send(ADMIN_CHAT_ID, fmt_warnings(fresh))
        except Exception:
            log.exception("daily check error")
        time.sleep(60)

# ---------------------------------------------------------------- flask (oauth callback + health)

app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/diag")
def diag():
    """Safe diagnostic: verifies Telegram token without exposing it."""
    result = {"token_valid": False, "bot_username": None, "admin_set": bool(ADMIN_CHAT_ID)}
    try:
        r = requests.post(f"{TG_API}/getMe", timeout=15)
        data = r.json()
        if data.get("ok"):
            result["token_valid"] = True
            result["bot_username"] = data["result"].get("username")
        else:
            result["tg_error"] = data.get("description", "unknown")
    except Exception as e:
        result["tg_error"] = str(e)[:100]
    try:
        w = requests.post(f"{TG_API}/getWebhookInfo", timeout=15).json()
        if w.get("ok"):
            result["webhook_url"] = w["result"].get("url") or None
            result["pending_updates"] = w["result"].get("pending_update_count")
    except Exception:
        pass
    return result


@app.post("/ingest")
def ingest():
    """Receive sweep results. Protected by INGEST_SECRET.

    Body JSON: {"results": {"email": {"status": "Licensed"|"Basic"|"ERROR"|"BLOCKED",
                                      "detail": "...",
                                      "expires_at": "2026-10-27" (optional)}}, "swept_at": "<iso>"}
    Updates the store, alerts the admin on license changes.
    """
    if request.headers.get("X-Ingest-Secret", "") != INGEST_SECRET:
        return {"ok": False, "error": "forbidden"}, 403
    try:
        body = request.get_json(force=True)
    except Exception:
        return {"ok": False, "error": "bad json"}, 400
    results = body.get("results") or {}
    swept_at = body.get("swept_at") or datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    if not isinstance(results, dict):
        return {"ok": False, "error": "results must be an object"}, 400

    store = load_store()
    changes = []
    updated = 0
    for email, info in results.items():
        email = str(email).strip().lower()
        if "@" not in email or not isinstance(info, dict):
            continue
        status = str(info.get("status", "")).strip()
        detail = str(info.get("detail", ""))[:300]
        acc = store["accounts"].setdefault(email, {})
        prev = acc.get("last_type")
        acc["sweep_status"] = status
        acc["sweep_detail"] = detail
        acc["last_sweep"] = swept_at
        # license expiration date from the account's billing settings, when known
        exp = str(info.get("expires_at") or "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", exp):
            acc["license_expires_at"] = exp[:10]
        elif status == "Basic":
            acc.pop("license_expires_at", None)
        if status in ("Licensed", "Basic"):
            if status == "Licensed" and prev != "Licensed":
                # (Re)licensed: start the 14-day clock. If the license was
                # granted before this sweep, use /backdate to correct it.
                acc["licensed_since"] = swept_at
            elif status == "Basic":
                if prev == "Licensed":
                    acc["last_lapsed_at"] = swept_at
                acc.pop("licensed_since", None)
            acc["last_type"] = status
            acc["last_check"] = swept_at
            updated += 1
            if prev and prev != status:
                changes.append((email, prev, status, ""))
        elif status in ("ERROR", "BLOCKED"):
            # keep last known license, but note the sweep couldn't verify it
            updated += 1
    store["last_sweep_at"] = swept_at
    save_store(store)
    log.info("ingested %d accounts, %d changes", updated, len(changes))

    if changes and store.get("alerts_on", True):
        try:
            send(ADMIN_CHAT_ID, fmt_changes(changes))
        except Exception:
            log.exception("alert send failed")

    # Immediate alert for licenses expiring within 1 day (don't wait for the
    # daily job — a sweep may land after the morning summary ran).
    today = datetime.datetime.now(datetime.timezone.utc).date()
    urgent = []
    for email in results:
        email = str(email).strip().lower()
        acc = store["accounts"].get(email)
        if not acc or acc.get("last_type") != "Licensed":
            continue
        exp_date = account_expiry_date(acc)
        if not exp_date:
            continue
        days_left = (exp_date - today).days
        key = exp_date.isoformat()
        if days_left <= WARN_DAYS_BEFORE and acc.get("warned_for_expiry") != key:
            urgent.append((email, days_left))
            acc["warned_for_expiry"] = key
    if urgent:
        save_store(store)
        if store.get("alerts_on", True):
            lines = ["\u23f0 Licenses expiring soon:"]
            for email, dl in sorted(urgent):
                when = "TOMORROW" if dl == 1 else ("TODAY" if dl == 0 else f"{-dl}d OVERDUE")
                lines.append(f"{short_email(email)}: expires {when}")
            try:
                send(ADMIN_CHAT_ID, "\n".join(lines))
            except Exception:
                log.exception("urgent expiry alert failed")

    return {"ok": True, "updated": updated, "changes": len(changes)}


@app.get("/privacy")
def privacy():
    return """<!doctype html><html><head><meta charset="utf-8">
<title>Privacy Policy — Zoom License Monitor</title></head>
<body style="font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 16px">
<h1>Privacy Policy — Zoom License Monitor</h1>
<p>Last updated: 13 October 2026</p>
<h2>What this app does</h2>
<p>Zoom License Monitor is a private tool for the owner of a fleet of Zoom
accounts. It reads each account's license type (Licensed vs Basic) via the
Zoom API so the owner can see which accounts have active licenses. It also
provides a Telegram bot interface for viewing those statuses.</p>
<h2>Data we collect</h2>
<ul>
<li>Zoom account email address, Zoom user ID, display name, and license type
(Basic / Licensed), obtained via the Zoom API with the account owner's
authorization.</li>
<li>OAuth refresh tokens, stored encrypted.</li>
<li>The Telegram chat ID of the bot administrator (for sending status alerts).</li>
</ul>
<h2>How data is used and stored</h2>
<p>Data is used solely to display license statuses and send change alerts to
the administrator. Tokens are encrypted at rest. Data is stored on the owner's
private server and is never sold or shared with third parties.</p>
<h2>Data retention and deletion</h2>
<p>Data is retained while the app is in use. The owner may revoke the app's
access at any time from Zoom's Marketplace settings, and may request deletion
of stored data by contacting the owner.</p>
<h2>Contact</h2>
<p>For privacy questions, contact the app owner via the Zoom Marketplace
listing.</p>
</body></html>"""


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


def sweep_job():
    """Every 6 hours:
    1. Detect Licensed accounts whose expiry date has passed -> mark Basic,
       alert immediately (no login needed, date is known).
    2. Re-check accounts marked Basic via Playwright (they may have been
       renewed) -> alert on Basic->Licensed flips.
    """
    import time as _time
    import datetime as _dt
    # Wait for bot to fully start
    _time.sleep(60)
    while True:
        try:
            from sweeper import run_targeted_sweep
            store = load_store()
            today = _dt.datetime.now(_dt.timezone.utc).date()

            # Step 1: expiry dates that have passed -> Basic
            expired = []
            for email in fleet_emails(store):
                acc = store["accounts"].get(email, {})
                if acc.get("last_type") != "Licensed":
                    continue
                exp = acc.get("license_expires_at")
                if not exp:
                    continue
                try:
                    exp_date = _dt.date.fromisoformat(exp[:10])
                except Exception:
                    continue
                if exp_date < today:
                    acc["last_type"] = "Basic"
                    acc["expired_on"] = exp
                    expired.append(email)
            if expired:
                save_store(store)
                log.info(f"Marked {len(expired)} expired accounts as Basic")
                if store.get("alerts_on", True):
                    lines = ["⚠️ License expired — now Basic:"]
                    for email in sorted(expired):
                        lines.append(short_email(email))
                    send(ADMIN_CHAT_ID, "\n".join(lines))

            # Step 2: re-check Basic accounts (catches renewals)
            checked, changes = run_targeted_sweep(
                store, save_store, fleet_emails, short_email)
            if checked:
                log.info(f"Targeted sweep: checked {checked}, {len(changes)} changes")
                if changes and store.get("alerts_on", True):
                    lines = ["✅ License renewed — back to Licensed:"]
                    for email, prev, new in changes:
                        lines.append(f"{short_email(email)}: {prev} → {new}")
                    send(ADMIN_CHAT_ID, "\n".join(lines))
        except Exception:
            log.exception("sweep job error")
        # Every 6 hours
        _time.sleep(6 * 3600)


def main():
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=daily_check_job, daemon=True).start()
    threading.Thread(target=sweep_job, daemon=True).start()
    port = int(os.environ.get("PORT", "5000"))
    log.info("starting Flask on port %s", port)
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
