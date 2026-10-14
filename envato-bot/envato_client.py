"""Envato Elements client — session-cookie based.

There is no official Elements download API, so this drives the same
endpoints the website uses, authenticated with the owner's login session
cookie (saved via /setcookie, stored on the persistent volume).

Endpoint details are filled in after the site investigation; the plumbing
(session, errors, file streaming) is ready.
"""

import os

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
COOKIE_FILE = os.path.join(DATA_DIR, "envato_cookie.txt")
DOWNLOADS_DIR = os.path.join(DATA_DIR, "downloads")


class EnvatoError(Exception):
    pass


class SessionExpired(EnvatoError):
    pass


def save_cookie(cookie):
    cookie = (cookie or "").strip()
    if not cookie:
        raise EnvatoError("Empty cookie.")
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = COOKIE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(cookie)
    os.replace(tmp, COOKIE_FILE)


def load_cookie():
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _session():
    cookie = load_cookie()
    if not cookie:
        raise SessionExpired("No Envato session saved yet.")
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/131.0 Safari/537.36"),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://elements.envato.com/",
    })
    # Cookie may be pasted as a full "a=1; b=2" header value.
    for part in cookie.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            s.cookies.set(name.strip(), value.strip(),
                          domain=".envato.com")
    return s


def check_session():
    """Returns (ok, detail)."""
    # TODO: fill in after site investigation.
    raise NotImplementedError("check_session: awaiting endpoint discovery")


def search(query, limit=8):
    """Returns a list of dicts: id, title, category, thumb, page_url."""
    # TODO: fill in after site investigation.
    raise NotImplementedError("search: awaiting endpoint discovery")


def download_item(item):
    """Downloads the item; returns (path, filename, license_text)."""
    # TODO: fill in after site investigation.
    raise NotImplementedError("download_item: awaiting endpoint discovery")
