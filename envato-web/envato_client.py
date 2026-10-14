"""Envato Elements client — session-cookie based.

There is no official Elements download API, so this drives the same
endpoints the website (app.envato.com, a React Router app) uses,
authenticated with the owner's login session cookie.

Cookie source (in order):
  1. ENVATO_COOKIE env var (set on Railway)
  2. File saved via /setcookie (persistent volume)

Search responses are React Router single-fetch payloads: a flat JSON array
("heap") where objects are encoded as {"_<keyIdx>": <valIdx>, ...} —
key names live at the key index, values at the value index.
"""

import os
import urllib.parse

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
COOKIE_FILE = os.path.join(DATA_DIR, "envato_cookie.txt")
DOWNLOADS_DIR = os.path.join(DATA_DIR, "downloads")

APP_BASE = "https://app.envato.com"


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
    env = os.environ.get("ENVATO_COOKIE", "").strip()
    if env:
        return env
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
        "Accept": "*/*",
        "Referer": "https://app.envato.com/",
    })
    # Cookie may be pasted as a full "a=1; b=2" header value.
    for part in cookie.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            name, value = name.strip(), value.strip()
            if name and value:
                s.cookies.set(name, value, domain=".envato.com")
    return s


def _is_guest_response(resp):
    """Detect auth failure: redirect to guest sign-in."""
    if resp.status_code in (401, 403):
        return True
    # React Router SingleFetchRedirect to guest sign-in.
    try:
        body = resp.content
    except Exception:
        return False
    return b"guestSignIn" in body[:5000]


def decode_turbostream(arr):
    """Decode a React Router single-fetch heap into plain Python."""
    n = len(arr)
    memo = {}

    def ref(i):
        if i < 0:
            return None
        if i in memo:
            return memo[i]
        if i >= n:
            return None
        v = arr[i]
        if isinstance(v, dict):
            obj = {}
            memo[i] = obj
            for k, r in v.items():
                try:
                    fname = ref(int(k[1:]))
                except (ValueError, IndexError):
                    fname = k
                obj[fname] = ref(r) if isinstance(r, int) else r
            return obj
        if isinstance(v, list):
            lst = []
            memo[i] = lst
            for x in v:
                lst.append(ref(x) if isinstance(x, int) else x)
            return lst
        memo[i] = v
        return v

    return ref(0)


def _route_data(payload, route_id):
    """Extract the `data` for a route id from a decoded payload."""
    try:
        return payload[route_id]["data"]
    except (KeyError, TypeError):
        raise EnvatoError(f"Unexpected response shape (missing {route_id}).")


def check_session():
    """Returns (ok, detail). Uses the search endpoint as a session probe."""
    s = _session()
    url = APP_BASE + "/search/all.data?term=test"
    try:
        r = s.get(url, timeout=30)
    except requests.RequestException as e:
        return False, f"Network error: {e}"
    if _is_guest_response(r):
        return False, "Session not accepted (guest redirect)."
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}."
    try:
        payload = decode_turbostream(r.json())
        data = _route_data(payload, "routes/search.all/route")
    except Exception as e:
        return False, f"Parse error: {e}"
    term = data.get("term")
    authed = "displayName" in r.text
    if authed:
        return True, f"Session active (probe term={term!r})."
    return False, "Response looks anonymous; cookie may be invalid."


def search(query, limit=8):
    """Returns list of dicts: itemUuid, itemType, title, author, thumb."""
    s = _session()
    url = (APP_BASE + "/search/all.data?term=" +
           urllib.parse.quote_plus(query))
    try:
        r = s.get(url, timeout=30)
    except requests.RequestException as e:
        raise EnvatoError(f"Network error: {e}")
    if _is_guest_response(r):
        raise SessionExpired("Envato session expired or not accepted.")
    if r.status_code != 200:
        raise EnvatoError(f"Search HTTP {r.status_code}.")
    payload = decode_turbostream(r.json())
    data = _route_data(payload, "routes/search.all/route")
    sar = data.get("searchAllResults", {})
    results = []
    for _type_key, type_data in sar.items():
        if not isinstance(type_data, dict):
            continue
        for entry in type_data.get("items", []) or []:
            item = (entry or {}).get("item") or {}
            uuid = item.get("itemUuid")
            if not uuid:
                continue
            image = item.get("image") or {}
            results.append({
                "itemUuid": uuid,
                "itemType": item.get("itemType", ""),
                "title": item.get("title", "Untitled"),
                "author": item.get("authorUsername", ""),
                "thumb": image.get("fallbackSrc", ""),
                # legacy keys used by bot.py display
                "id": uuid,
                "category": item.get("itemType", ""),
            })
            if len(results) >= limit:
                return results
    return results


def _download_url(item_uuid, item_type):
    """Get the signed file URL via the /download route loader."""
    s = _session()
    url = (APP_BASE + "/download.data?itemUuid=" +
           urllib.parse.quote_plus(item_uuid) +
           "&itemType=" + urllib.parse.quote_plus(item_type) +
           "&_data=routes/download/route")
    try:
        r = s.get(url, timeout=30)
    except requests.RequestException as e:
        raise EnvatoError(f"Network error: {e}")
    if _is_guest_response(r):
        raise SessionExpired("Envato session expired or not accepted.")
    if r.status_code != 200:
        raise EnvatoError(f"Download HTTP {r.status_code}.")
    payload = decode_turbostream(r.json())
    data = _route_data(payload, "routes/download/route")
    dl_url = data.get("downloadUrl")
    if not dl_url:
        raise EnvatoError("No download URL in response.")
    return dl_url


def _create_license(item_uuid, project_name="Telegram Bot"):
    """Create a license; returns (license_uuid, cert_10char_id)."""
    s = _session()
    url = APP_BASE + "/item-licenses.data?_data=routes/item-licenses/route"
    try:
        r = s.post(url, data={"itemUuid": item_uuid,
                              "projectName": project_name},
                   timeout=30)
    except requests.RequestException as e:
        raise EnvatoError(f"Network error: {e}")
    if _is_guest_response(r):
        raise SessionExpired("Envato session expired or not accepted.")
    if r.status_code != 200:
        return None, None
    try:
        payload = decode_turbostream(r.json())
        lic = payload.get("data", {}).get("license") or {}
        lid = lic.get("id")
        # 10-char cert id is embedded in the file URL.
        cert_url = lic.get("licenseFileDownloadUrl") or ""
        short = cert_url.rsplit("/", 1)[-1].replace(".pdf", "") or None
        return lid, short
    except Exception:
        return None, None


def _download_license_pdf(license_uuid, dest_path):
    """Download the license certificate PDF; returns True on success."""
    s = _session()
    url = f"{APP_BASE}/license-certificate/{license_uuid}/download"
    try:
        with s.get(url, stream=True, timeout=60) as r:
            if r.status_code != 200:
                return False
            ctype = r.headers.get("Content-Type", "")
            if "pdf" not in ctype.lower():
                return False
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
            return os.path.getsize(dest_path) > 0
    except requests.RequestException:
        return False


def _stream_download(url, dest_path):
    """Stream a file URL to disk; returns bytes written."""
    s = _session()
    # Signed file URLs are on *.envatousercontent.com; cookie not needed
    # but harmless. Use a plain request without envato cookies.
    try:
        with requests.get(url, stream=True, timeout=60,
                          headers={"User-Agent": s.headers["User-Agent"]}) as r:
            r.raise_for_status()
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            total = 0
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            return total
    except requests.RequestException as e:
        raise EnvatoError(f"File download failed: {e}")


def _filename_from_url(url, fallback):
    # URLs carry response-content-disposition with the real filename.
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        cd = qs.get("response-content-disposition", [""])[0]
        # e.g. "attachment; filename*=UTF-8''business-presentation.zip"
        if "filename*=" in cd:
            name = cd.split("filename*=")[1].split("''")[-1]
            name = urllib.parse.unquote(name).strip().strip('"')
            if name:
                return name
    except Exception:
        pass
    return fallback


def download_item(item):
    """Downloads the item + license certificate.

    Returns (file_path, filename, license_pdf_path_or_None).
    """
    uuid = item["itemUuid"]
    itype = item["itemType"]
    title = item.get("title", "file")

    dl_url = _download_url(uuid, itype)
    fname = _filename_from_url(dl_url, f"{title}.zip")
    # Sanitize filename.
    fname = "".join(c for c in fname if c not in '<>:"/\\|?*').strip() or "file"
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    dest = os.path.join(DOWNLOADS_DIR, f"{uuid}_{fname}")
    if not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        _stream_download(dl_url, dest)

    # License certificate (auto-licensed on download; fetch the PDF).
    lic_pdf = None
    lic_uuid, _short = _create_license(uuid, project_name=title[:80])
    if lic_uuid:
        lic_pdf = dest + ".LICENSE.pdf"
        if not os.path.isfile(lic_pdf) or os.path.getsize(lic_pdf) == 0:
            if not _download_license_pdf(lic_uuid, lic_pdf):
                lic_pdf = None

    return dest, fname, lic_pdf
