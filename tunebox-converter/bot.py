#!/usr/bin/env python3
"""
TuneBox Converter — owner's own videos to MP3.

Send the bot a YouTube link, a direct link to one of your own videos
(or send the video file itself) and it returns the audio as an MP3.
Owner-only: only the admin's Telegram id may use it.

This is a converter for videos you own. It does not search or fetch
from Spotify or any other streaming site.

Env vars:
    BOT_TOKEN       - from @BotFather
    ADMIN_CHAT_ID   - Telegram user id of the owner (default: Arkar, 8028025915)
    YOUTUBE_COOKIES - optional: contents of a Netscape cookies.txt exported
                      from a browser signed in to YouTube. Needed when
                      YouTube's "Sign in to confirm you're not a bot" check
                      blocks the bot's server (datacenter IPs get flagged).
    GOOGLE_COOKIES  - optional: the same export from google.com (the
                      session cookies live there); the web players may
                      withhold audio formats without them.
    POT_PROVIDER_URL - optional: base URL of the bgutil PO-token
                      provider server. Default http://127.0.0.1:4416.
                      On Railway this is the provider service over
                      private networking
                      (http://bgutil-pot-provider.railway.internal:4416).

Limits: input files up to 400 MB; output MP3 must fit Telegram's 50 MB
bot-upload limit (re-encodes at 64 kbps once if the 128 kbps file is too
big, otherwise it tells you the file is too long).
"""

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import traceback
import urllib.parse

import requests
import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "8028025915").strip()

if not BOT_TOKEN:
    raise SystemExit("Set the BOT_TOKEN env var (get it from @BotFather).")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TG_FILE = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

MAX_INPUT_BYTES = 400 * 1024 * 1024
MAX_SEND_BYTES = 48 * 1024 * 1024  # under Telegram's 50 MB bot limit
VIDEO_EXTS = {"mp4", "mov", "webm", "mkv", "avi", "m4v", "mpg", "mpeg",
              "3gp", "flv", "wmv", "m4a", "mp3", "wav", "ogg", "oga",
              "flac", "opus", "aac"}

WELCOME = (
    "🎵 TuneBox Converter\n\n"
    "Send me a YouTube link, a direct link to one of your own videos, "
    "or send the video file itself, and I'll send back the audio as "
    "an MP3.\n\n"
    "Your videos only — this bot doesn't fetch from Spotify or any "
    "other streaming site.\n\n"
    "Developed by Arkar Myowin"
)


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# ---------------------------------------------------------------- Telegram

def tg(method, payload, timeout=60):
    r = requests.post(f"{TG_API}/{method}", json=payload, timeout=timeout)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if not data.get("ok"):
        log("Telegram API error:", method, r.status_code, r.text[:300])
    return data


def send_message(chat_id, text):
    return tg("sendMessage", {"chat_id": chat_id, "text": text})


def send_audio(chat_id, path, title):
    with open(path, "rb") as f:
        r = requests.post(
            f"{TG_API}/sendAudio",
            data={"chat_id": chat_id, "title": title[:120],
                  "performer": "TuneBox Converter"},
            files={"audio": (os.path.basename(path), f, "audio/mpeg")},
            timeout=300)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if not data.get("ok"):
        log("sendAudio failed:", r.status_code, r.text[:300])
    return data


def get_file_path(file_id):
    data = tg("getFile", {"file_id": file_id}, timeout=30)
    res = data.get("result") or {}
    return res.get("file_path")


# ---------------------------------------------------------------- fetching

def _url_is_public(url):
    """Reject localhost / private / reserved hosts (SSRF guard)."""
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local \
                or ip.is_reserved or ip.is_multicast:
            return False
    return True


def download_url(url, dest):
    """Stream a direct file link to dest. Returns (ok, error)."""
    if not _url_is_public(url):
        return False, "That link doesn't point to a public file."
    try:
        with requests.get(url, stream=True, timeout=(10, 120),
                          allow_redirects=True) as r:
            if r.status_code != 200:
                return False, f"Couldn't fetch the link (HTTP {r.status_code})."
            total = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_INPUT_BYTES:
                        return False, "That file is over 400 MB — too big."
                    f.write(chunk)
    except requests.exceptions.RequestException as e:
        return False, f"Couldn't fetch the link ({e.__class__.__name__})."
    if total == 0:
        return False, "The link returned an empty file."
    return True, ""


def download_telegram_file(file_path, dest):
    url = f"{TG_FILE}/{file_path}"
    try:
        with requests.get(url, stream=True, timeout=(10, 120)) as r:
            if r.status_code != 200:
                return False, f"Couldn't fetch your file (HTTP {r.status_code})."
            total = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_INPUT_BYTES:
                        return False, "That file is over 400 MB — too big."
                    f.write(chunk)
    except requests.exceptions.RequestException as e:
        return False, f"Couldn't fetch your file ({e.__class__.__name__})."
    return (total > 0), "" if total > 0 else "That file came back empty."


def is_youtube_url(url):
    """True for youtube.com / youtu.be video links (watch, shorts, live,
    embed, music)."""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "youtu.be" or host.endswith(".youtube.com") \
        or host == "youtube.com"


def _youtube_cookies_file():
    """Optional cookies for yt-dlp, from the YOUTUBE_COOKIES env var
    (a Netscape cookies.txt exported from a browser signed in to
    YouTube) plus GOOGLE_COOKIES (the same export from google.com —
    the session cookies live there, and the web players may withhold
    formats without them). YouTube's bot-check ("Sign in to confirm
    you're not a bot") blocks datacenter IPs like Railway's; a
    signed-in session gets past it. Returns the temp file path, or
    None when neither is set. Only lengths are ever logged, never the
    cookie values."""
    parts = []
    for name in ("YOUTUBE_COOKIES", "GOOGLE_COOKIES"):
        text = os.environ.get(name, "").strip()
        if text:
            parts.append(text if text.endswith("\n") else text + "\n")
    if not parts:
        log("YouTube cookies: not set")
        return None
    path = os.path.join(tempfile.gettempdir(), "youtube-cookies.txt")
    with open(path, "w") as f:
        f.writelines(parts)
    log("YouTube cookies: set (%d chars in %d part(s)), file ready"
        % (sum(len(p) for p in parts), len(parts)))
    return path


class _WarningCollector:
    """Collects yt-dlp warnings/errors (and PO-token-related debug lines)
    so a failed pass can say WHY it failed. yt-dlp calls logger.warning
    even when quiet/no_warnings are set, so this sees the "Missing
    required Data Sync ID" / "Missing required Visitor Data" / "No
    supported JavaScript runtime" warnings that the Railway logs
    otherwise hide. Only warnings, errors and matching debug lines are
    kept — download progress is dropped."""
    _DEBUG_KEEP = ("po token", "visitor", "javascript", "deno", "gvs",
                   "data sync", "js runtime")

    def __init__(self):
        self.lines = []

    def debug(self, msg):
        if any(k in msg.lower() for k in self._DEBUG_KEEP):
            self.lines.append(msg)

    def warning(self, msg):
        self.lines.append("WARNING: " + msg)

    def error(self, msg):
        # Skip tracebacks — the final error line is kept separately.
        if msg.startswith("Traceback (most recent call last)"):
            return
        self.lines.append("ERROR: " + msg)


def _pot_provider_url():
    """Base URL of the bgutil PO-token provider server (see README).
    The bot and the provider run as separate Railway services, so this
    points at the provider over Railway private networking by default;
    http://127.0.0.1:4416 is the local default."""
    return os.environ.get(
        "POT_PROVIDER_URL", "http://127.0.0.1:4416").strip()


def _download_with_clients(url, tmpdir, clients, cookies=None):
    """One yt-dlp pass with the given player clients. Returns
    (path, title) on success, (None, error string) on failure.
    On failure, the yt-dlp warnings collected for this pass are logged
    so the Railway logs show the real reason (e.g. a missing PO-token
    input) instead of just the final error.
    The bgutil HTTP provider (see README) mints the Proof-of-Origin
    tokens the web players need; its base URL comes from
    POT_PROVIDER_URL."""
    collector = _WarningCollector()
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmpdir, "input.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "verbose": True,
        "logger": collector,
        "ffmpeg_location": os.path.dirname(ffmpeg_exe()),
        "extractor_args": {
            "youtube": {"player_client": clients},
            "youtubepot-bgutilhttp": {"base_url": [_pot_provider_url()]},
            # NOTE: the value MUST be a one-element list. yt-dlp's
            # _configuration_arg turns the value into a list and takes
            # [0]; a bare string would be split into characters and
            # [0] would be just "h", so the provider would try to
            # reach "h/ping" ("Unsupported url scheme: ''") and the
            # token server would never be contacted at all.
        },
    }
    if cookies:
        ydl_opts["cookiefile"] = cookies
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        for line in collector.lines:
            log("yt-dlp (%s): %s" % (",".join(clients), line[:300]))
        return None, repr(e)[:300]
    title = ((info or {}).get("title") or "audio")[:120]
    for name in sorted(os.listdir(tmpdir)):
        if name.startswith("input."):
            return os.path.join(tmpdir, name), title
    return None, "YouTube gave me no audio file for that link."


def download_youtube_audio(url, tmpdir):
    """yt-dlp: fetch the best audio stream for one YouTube video.
    Passes, in order: the phone/TV clients with NO cookies (they fetch
    fine without a sign-in, and web cookies can trip them up), then
    the web players WITH the signed-in cookies if set — the web
    player is the one YouTube's bot-check demands a sign-in for, and
    the Safari/mobile/embedded web players are the ones yt-dlp's own
    guidance recommends with cookies, since plain web often answers
    a signed-in request with "Requested format is not available"
    (its formats need a Proof-of-Origin token).
    "Made for Kids" videos (all of the owner's story videos) come back
    as "not available" with the default web client; the android client
    fetches them fine. Music videos (Vevo etc.) get one last try
    through the YouTube Music players, which use a different endpoint
    that sometimes hands over formats the web players withhold.
    Returns (path, title) on success, (None, error message) on failure."""
    cookies = _youtube_cookies_file()
    passes = [
        ("phone/TV, no cookies", ["android", "ios", "tv"], None),
        ("web, cookies", ["web"], cookies),
        ("web_safari, cookies", ["web_safari"], cookies),
        ("mweb, cookies", ["mweb"], cookies),
        ("web_embedded, cookies", ["web_embedded"], cookies),
        ("music, cookies", ["android_music", "web_music", "ios_music"],
         cookies),
    ]
    last_err = ""
    for label, clients, ck in passes:
        if ck is None and label != "phone/TV, no cookies":
            continue
        src, title_or_err = _download_with_clients(url, tmpdir, clients, ck)
        if src:
            return src, title_or_err
        log("yt-dlp pass (%s) failed:" % label, title_or_err)
        last_err = title_or_err
    err = last_err
    if "Sign in to confirm you're not a bot" in err:
        return None, ("YouTube blocked the download — it flagged the "
                      "bot's server as a bot. It's not the video; "
                      "the bot needs a signed-in session to get past "
                      "that check.")
    if "The page needs to be reloaded" in err:
        return None, ("YouTube asked for a reload and the download "
                      "didn't come through — try sending the link again.")
    return None, ("I couldn't get audio from that YouTube link — it "
                  "may be unavailable, age-restricted, or blocked.")
    title = ((info or {}).get("title") or "audio")[:120]
    for name in sorted(os.listdir(tmpdir)):
        if name.startswith("input."):
            return os.path.join(tmpdir, name), title
    return None, "YouTube gave me no audio file for that link."


# ---------------------------------------------------------------- convert

def convert_to_mp3(src, dst, bitrate="128k"):
    """ffmpeg: strip video, encode MP3. Returns True on success."""
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-i", src,
           "-vn", "-c:a", "libmp3lame", "-b:a", bitrate, dst]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        log("ffmpeg failed:", p.stderr[:500])
        return False
    return os.path.isfile(dst) and os.path.getsize(dst) > 0


def handle_convert(chat_id, src_path, title):
    """Convert src_path to MP3 and send it. Cleans up after itself."""
    tmpdir = tempfile.mkdtemp(prefix="tbc_")
    try:
        out = os.path.join(tmpdir, "audio.mp3")
        if not convert_to_mp3(src_path, out, "128k"):
            send_message(chat_id,
                         "I couldn't read audio from that file — it may not "
                         "be a video/audio file. 🙏")
            return
        if os.path.getsize(out) > MAX_SEND_BYTES:
            log("128k MP3 too big, retrying at 64k")
            if not convert_to_mp3(src_path, out, "64k") or \
                    os.path.getsize(out) > MAX_SEND_BYTES:
                send_message(
                    chat_id,
                    "That video is too long — even at low quality the MP3 "
                    "is over Telegram's 50 MB limit. Try a shorter clip.")
                return
        send_audio(chat_id, out, title)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def guess_title(url):
    path = urllib.parse.urlparse(url).path
    name = os.path.basename(path)
    name = urllib.parse.unquote(name)
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return (name or "audio").replace("_", " ").replace("-", " ")[:120]


def handle_update(upd):
    msg = upd.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    from_user = msg.get("from") or {}
    if not chat_id:
        return
    if str(from_user.get("id", "")) != str(ADMIN_CHAT_ID):
        send_message(chat_id, "Sorry — this bot is private, for its owner only.")
        return
    text = (msg.get("text") or "").strip()
    if text.startswith("/start") or text.startswith("/help"):
        send_message(chat_id, WELCOME)
        return
    if text.startswith("http://") or text.startswith("https://"):
        url = text.split()[0]
        if is_youtube_url(url):
            send_message(chat_id, "Fetching audio from YouTube… ⏬")
            tmpdir = tempfile.mkdtemp(prefix="tbc_")
            try:
                src, title_or_err = download_youtube_audio(url, tmpdir)
                if not src:
                    send_message(chat_id, title_or_err)
                    return
                send_message(chat_id, "Converting to MP3… 🎵")
                handle_convert(chat_id, src, title_or_err)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
            return
        ext = urllib.parse.urlparse(url).path.rsplit(".", 1)[-1].lower() \
            if "." in urllib.parse.urlparse(url).path else ""
        if ext and ext not in VIDEO_EXTS:
            send_message(chat_id,
                         "That link doesn't look like a video or audio file "
                         "(I accept direct mp4/mov/webm/mkv/audio links).")
            return
        send_message(chat_id, "Downloading your video… ⏬")
        tmpdir = tempfile.mkdtemp(prefix="tbc_")
        try:
            src = os.path.join(tmpdir, "input." + (ext or "mp4"))
            ok, err = download_url(url, src)
            if not ok:
                send_message(chat_id, err)
                return
            send_message(chat_id, "Converting to MP3… 🎵")
            handle_convert(chat_id, src, guess_title(url))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        return
    video = msg.get("video") or msg.get("document") or {}
    file_id = video.get("file_id")
    if file_id:
        mime = (video.get("mime_type") or "")
        if not (mime.startswith("video/") or mime.startswith("audio/")):
            send_message(chat_id, "Please send a video or audio file.")
            return
        send_message(chat_id, "Got it — converting to MP3… 🎵")
        file_path = get_file_path(file_id)
        if not file_path:
            send_message(chat_id, "I couldn't fetch that file — try again.")
            return
        tmpdir = tempfile.mkdtemp(prefix="tbc_")
        try:
            ext = (video.get("file_name") or "").rsplit(".", 1)[-1].lower() \
                if "." in (video.get("file_name") or "") else "mp4"
            src = os.path.join(tmpdir, "input." + (ext or "mp4"))
            ok, err = download_telegram_file(file_path, src)
            if not ok:
                send_message(chat_id, err)
                return
            title = (video.get("file_name") or "audio").rsplit(".", 1)[0]
            handle_convert(chat_id, src, title)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        return
    if text:
        send_message(chat_id,
                     "Send me a YouTube link, a direct link to one of your "
                     "videos, or send the video file itself, and I'll "
                     "return the MP3. 🎵")


def main():
    log("TuneBox Converter started. Polling for updates...")
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
