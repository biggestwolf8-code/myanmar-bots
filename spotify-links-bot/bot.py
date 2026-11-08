#!/usr/bin/env python3
"""
Spotify Links Bot — search the Spotify catalogue and share song links.

Type a song name (or /search <song>) and the bot replies with the top
matches: title, artist, album and a button that opens each song in Spotify.
Telegram unfurls the top link into a playable Spotify card. No audio is
downloaded or stored anywhere — the bot only shares links.

Env vars:
    BOT_TOKEN             - from @BotFather
    SPOTIFY_CLIENT_ID     - from a Spotify Developer app (developer.spotify.com)
    SPOTIFY_CLIENT_SECRET - same app's client secret
    ADMIN_CHAT_ID         - optional: Telegram user id for error reports

Spotify search uses the client-credentials flow (app-only, no user login).
Development-mode apps return at most 10 results per query; this bot asks
for 5. No preview audio is available from the API — links only, by design.
"""

import html
import json
import os
import time
import traceback

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()

if not BOT_TOKEN:
    raise SystemExit("Set the BOT_TOKEN env var (get it from @BotFather).")
if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise SystemExit("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET "
                     "(create an app at developer.spotify.com).")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"

RESULTS_LIMIT = 5

WELCOME = (
    "🎵 Spotify Links Bot\n\n"
    "Type a song name and I'll find it on Spotify — tap a result to open "
    "it in Spotify.\n\n"
    "သီချင်းနာမည် ရိုက်လိုက်ပါ — Spotify မှာ ရှာပေးပြီး link ပို့ပေးပါမယ်။\n\n"
    "Try: <i>Blinding Lights</i>  •  /search <i>Shape of You</i>\n\n"
    "Developed by Arkar Myowin"
)

HELP = (
    "🎵 How to use this bot\n\n"
    "• Just type a song name — e.g. <i>Blinding Lights</i>\n"
    "• Or use /search <i>song name</i>\n"
    "• Tap a result button to open that song in Spotify.\n\n"
    "The bot only shares Spotify links — it doesn't download music."
)


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- Spotify

_spotify_token = {"access_token": None, "expires_at": 0}


def spotify_token():
    """Client-credentials token, cached until shortly before expiry."""
    now = time.time()
    if _spotify_token["access_token"] and _spotify_token["expires_at"] > now + 60:
        return _spotify_token["access_token"]
    r = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    _spotify_token["access_token"] = data["access_token"]
    _spotify_token["expires_at"] = now + int(data.get("expires_in", 3600))
    return _spotify_token["access_token"]


def spotify_search(query):
    """Return up to RESULTS_LIMIT tracks: dicts with name, artists, album,
    url and explicit flag. Raises on API failure."""
    token = spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "track", "limit": RESULTS_LIMIT}
    r = requests.get(SPOTIFY_SEARCH_URL, headers=headers, params=params,
                     timeout=15)
    if r.status_code == 401:  # token expired mid-flight; refresh once
        _spotify_token["access_token"] = None
        headers = {"Authorization": f"Bearer {spotify_token()}"}
        r = requests.get(SPOTIFY_SEARCH_URL, headers=headers, params=params,
                         timeout=15)
    r.raise_for_status()
    items = r.json().get("tracks", {}).get("items", []) or []
    out = []
    for it in items:
        artists = ", ".join(a.get("name", "") for a in it.get("artists", []))
        out.append({
            "name": it.get("name", "Unknown title"),
            "artists": artists or "Unknown artist",
            "album": (it.get("album") or {}).get("name", ""),
            "url": (it.get("external_urls") or {}).get("spotify", ""),
            "explicit": bool(it.get("explicit")),
        })
    return [t for t in out if t["url"]]


# ---------------------------------------------------------------- Telegram

def tg(method, payload, timeout=30):
    r = requests.post(f"{TG_API}/{method}", json=payload, timeout=timeout)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if not data.get("ok"):
        log("Telegram API error:", method, r.status_code, r.text[:300])
    return data


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": False}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendMessage", payload)


def send_results(chat_id, query, tracks):
    lines = [f"🎵 Top matches for <b>{html.escape(query)}</b>:\n"]
    buttons = []
    for i, t in enumerate(tracks, 1):
        tag = " [E]" if t["explicit"] else ""
        album = f" — <i>{html.escape(t['album'])}</i>" if t["album"] else ""
        lines.append(
            f"{i}. <b>{html.escape(t['name'])}</b>{tag}\n"
            f"   {html.escape(t['artists'])}{album}")
        label = f"▶ {i}. {t['name']}"
        if len(label) > 60:
            label = label[:57] + "…"
        buttons.append([{"text": label, "url": t["url"]}])
    # First link in the text makes Telegram unfurl the top track's player card.
    lines.append(f"\n▶ Top match: {tracks[0]['url']}")
    text = "\n".join(lines)
    send_message(chat_id, text, {"inline_keyboard": buttons})


def handle_update(upd):
    msg = upd.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    if text.startswith("/start"):
        send_message(chat_id, WELCOME)
        return
    if text.startswith("/help"):
        send_message(chat_id, HELP)
        return
    if text.startswith("/search"):
        query = text[len("/search"):].strip()
    else:
        query = text
    if text.startswith("/") and not query:
        send_message(chat_id, HELP)
        return
    if not query:
        send_message(chat_id, "Type a song name and I'll find it on Spotify. 🎵")
        return
    log("search:", repr(query[:80]), "from", chat_id)
    try:
        tracks = spotify_search(query)
    except Exception as e:
        log("Spotify search failed:", repr(e))
        send_message(
            chat_id,
            "Spotify search isn't working right now — please try again in a bit. 🙏")
        return
    if not tracks:
        send_message(
            chat_id,
            f"Couldn't find <b>{html.escape(query)}</b> on Spotify. "
            "Check the spelling or try the artist name too.")
        return
    send_results(chat_id, query, tracks)


def main():
    log("Spotify Links Bot started. Polling for updates...")
    offset = None
    while True:
        try:
            r = requests.get(
                f"{TG_API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40)
            data = r.json()
            if not data.get("ok"):
                log("getUpdates not ok:", r.text[:300])
                time.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    handle_update(upd)
                except Exception:
                    log("update failed:\n", traceback.format_exc())
        except requests.exceptions.RequestException as e:
            log("poll error:", repr(e))
            time.sleep(5)
        except Exception:
            log("loop error:\n", traceback.format_exc())
            time.sleep(5)


if __name__ == "__main__":
    main()
