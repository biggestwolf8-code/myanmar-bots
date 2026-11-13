"""Daddy3.0 — interactive game-board bot for Arkar's channel.

A board is a post: a text message with inline buttons. Each button is
tied to one photo or one video. In the channel, every tab is a LINK into
the bot's private chat: the user taps any tab, the bot chat opens with
the board's tabs ready, and they pick one there — the photo/video is
then sent to their PRIVATE chat (never to the channel). Opening a board
in the bot chat first shows a blurred sneak-peek photo for every tab,
each captioned with its label, so the user can see what each tab is
before choosing. Photos are blurred previews; videos show their
thumbnail, or a dark placeholder card when no thumbnail was stored.
Teasers are cached per viewer under DATA_DIR/teasers. The channel post
gets the same cover photos as an album above the board message (label
captions, no per-user tag on those).

Photos are free tabs. Videos are PAID tabs: one-time access, either
100 Telegram Stars (native Stars invoice) or 1 USDT on BSC (BEP20),
verified on-chain via a public BSC node from the transaction hash the
user pastes. Paid videos are sent with protect_content (no forward/save);
photos additionally carry a per-user watermark.

Balance: every board has a "💰 My Balance" button. A user's balance is
in dollars (stored as cents). Top-ups are $5 / $10 / $25 / $50 / $100,
paid in Telegram Stars at 1$ = 100 Stars or in USDT at 1 USDT = $1
(BSC/BEP20, verified on-chain). A video costs $1 of balance, so a
topped-up user can pay with balance instead of Stars or USDT.

Admin (Arkar) designs boards from the bot's DM:
  /newboard          start a draft (bot asks for the board title)
  <title text>       sets the draft title
  <photo + caption>  adds a FREE photo button; caption IS the label
  <video + caption>  adds a PAID video button; caption IS the label
  /done              save the draft, show a preview
  /post <id>         post the board to the channel
  /setchannel <@ch>  set the target channel (bot must be admin there)
  /boards            list saved boards
  /delboard <id>     delete a board
  /cancel            discard the current draft
  /help              admin help

Users:
  /start             welcome (or /start board_<id> via deep link)
  tap a tab in the channel — the bot chat opens with all tabs ready;
                     tap one there and the photo/video lands in the
                     private chat (video tabs ask for payment first)

Photos/videos are stored as Telegram file_ids only — Telegram hosts them.
Boards live in boards.json under DATA_DIR (Railway volume); unlocks in
unlocked.json, spent USDT transaction hashes in used_tx.json.

Every message the bot sends is logged in sent.json (chat, message id,
board, user). Admin revoke commands delete them again:
  /revoke user <telegram id>   everything sent to that user
  /revoke board <id>           that board's channel post + all media
                               sent from it
  /revoke all                  everything the bot ever sent (and logged)
Only messages sent AFTER this was added are logged — older ones cannot
be revoked. Deleting removes the message from the chat; it cannot undo
a screenshot or a screen recording.

Forward any post from the channel to the bot and it stores the channel's
numeric id as the target (more reliable than the invite link).
"""

import json
import io
import os
import random
import string
import time

import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {
    x.strip()
    for x in os.environ.get("ADMIN_CHAT_IDS", "7061620871,8028025915").split(",")
    if x.strip()
}
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
BOARDS_PATH = os.path.join(DATA_DIR, "boards.json")
UNLOCKED_PATH = os.path.join(DATA_DIR, "unlocked.json")
USED_TX_PATH = os.path.join(DATA_DIR, "used_tx.json")
SENT_PATH = os.path.join(DATA_DIR, "sent.json")
BALANCES_PATH = os.path.join(DATA_DIR, "balances.json")

# Balance: 1 USD = 100 Telegram Stars. Video = $1 of balance.
STARS_PER_USD = 100
VIDEO_PRICE_CENTS = 100
TOPUP_USD = [5, 10, 25, 50, 100]
API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

# Paid video tabs: 100 Telegram Stars, or 1 USDT on BSC (BEP20).
STARS_PRICE = 100
USDT_ADDRESS = "0xffef0a1f5b075ed8763d7e0b13c9e3df04819222"  # Arkar's BSC address
USDT_CONTRACT = "0x55d398326f99059ff775485246999027b3197955"  # USDT on BSC
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BSC_RPC = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.bnbchain.org/",
    "https://bsc-dataseed2.bnbchain.org/",
]
USDT_MIN = 1_000_000  # 1 USDT = 1,000,000 units (6 decimals)

FOOTER = "Developed by Arkar Myowin"


def load_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json_file(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_boards():
    return load_json_file(
        BOARDS_PATH, {"channel": "", "boards": {}, "draft": None, "seq": 0}
    )


def save_boards(state):
    save_json_file(BOARDS_PATH, state)


def is_unlocked(user_id, bid, idx):
    data = load_json_file(UNLOCKED_PATH, {})
    return f"{bid}:{idx}" in data.get(str(user_id), [])


def mark_unlocked(user_id, bid, idx):
    data = load_json_file(UNLOCKED_PATH, {})
    key = f"{bid}:{idx}"
    lst = data.setdefault(str(user_id), [])
    if key not in lst:
        lst.append(key)
    save_json_file(UNLOCKED_PATH, data)


def tx_used(tx_hash):
    return tx_hash.lower() in load_json_file(USED_TX_PATH, [])


def mark_tx_used(tx_hash):
    data = load_json_file(USED_TX_PATH, [])
    data.append(tx_hash.lower())
    save_json_file(USED_TX_PATH, data)


def fmt_usd(cents):
    return f"${cents // 100}.{cents % 100:02d}"


def get_balance(user_id):
    return int(load_json_file(BALANCES_PATH, {}).get(str(user_id), 0))


def add_balance(user_id, cents):
    data = load_json_file(BALANCES_PATH, {})
    total = int(data.get(str(user_id), 0)) + cents
    data[str(user_id)] = total
    save_json_file(BALANCES_PATH, data)
    return total


def deduct_balance(user_id, cents):
    """Take cents from the balance if there is enough. Returns True/False."""
    data = load_json_file(BALANCES_PATH, {})
    total = int(data.get(str(user_id), 0))
    if total < cents:
        return False
    data[str(user_id)] = total - cents
    save_json_file(BALANCES_PATH, data)
    return True


def record_sent(chat_id, message_id, kind, board=None, user=None):
    """Log a message the bot sent, so it can be revoked later."""
    data = load_json_file(SENT_PATH, [])
    data.append(
        {
            "chat": str(chat_id),
            "msg": message_id,
            "kind": kind,
            "board": board,
            "user": str(user) if user is not None else None,
            "ts": int(time.time()),
        }
    )
    save_json_file(SENT_PATH, data)


def revoke_entries(entries):
    """Delete each recorded message. Returns (deleted, failed) and the
    list of entries that can be pruned from the log (deleted, or already
    gone). Failures stay logged so they can be retried."""
    pruned = []
    deleted = 0
    failed = 0
    for e in entries:
        r = api(
            "deleteMessage", {"chat_id": e["chat"], "message_id": e["msg"]}
        )
        if r.get("ok") or "message to delete not found" in str(
            r.get("description", "")
        ):
            deleted += 1
            pruned.append(e)
        else:
            failed += 1
        time.sleep(0.05)
    return deleted, failed, pruned


def new_board_id(state):
    state["seq"] = state.get("seq", 0) + 1
    return f"b{state['seq']}"


def api(method, payload=None, files=None, timeout=60):
    url = f"{API}/{method}"
    try:
        if files:
            r = requests.post(url, data=payload or {}, files=files, timeout=timeout)
        else:
            r = requests.post(url, json=payload or {}, timeout=timeout)
        return r.json()
    except Exception as e:
        print(f"api {method} error: {e}", flush=True)
        return {"ok": False}


def send_message(chat_id, text, reply_markup=None, parse_mode=None, meta=None):
    payload = {"chat_id": chat_id, "text": text, "protect_content": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    r = api("sendMessage", payload)
    if r.get("ok"):
        m = meta or {}
        record_sent(
            chat_id,
            r["result"]["message_id"],
            m.get("kind", "message"),
            board=m.get("board"),
            user=m.get("user", chat_id if isinstance(chat_id, int) else None),
        )
    return r


def send_photo(chat_id, file_id, caption=None, meta=None):
    payload = {"chat_id": chat_id, "photo": file_id, "protect_content": True}
    if caption:
        payload["caption"] = caption
    r = api("sendPhoto", payload)
    if r.get("ok"):
        m = meta or {}
        record_sent(
            chat_id,
            r["result"]["message_id"],
            m.get("kind", "photo"),
            board=m.get("board"),
            user=m.get("user"),
        )
    return r


def send_video(chat_id, file_id, caption=None, meta=None):
    payload = {"chat_id": chat_id, "video": file_id, "protect_content": True}
    if caption:
        payload["caption"] = caption
    r = api("sendVideo", payload)
    if r.get("ok"):
        m = meta or {}
        record_sent(
            chat_id,
            r["result"]["message_id"],
            m.get("kind", "video"),
            board=m.get("board"),
            user=m.get("user"),
        )
    return r


def get_file_bytes(file_id):
    """Download a Telegram file's bytes (for watermarking)."""
    r = api("getFile", {"file_id": file_id})
    if not r.get("ok"):
        return None
    path = r["result"].get("file_path")
    if not path:
        return None
    try:
        resp = requests.get(
            f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}", timeout=60
        )
        if resp.status_code == 200:
            return resp.content
    except Exception as e:
        print(f"file download error: {e}", flush=True)
    return None


def _load_font(size):
    from PIL import ImageFont

    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _safe_text(s):
    """ASCII-only text for PIL drawing (fonts lack emoji glyphs)."""
    return "".join(c for c in (s or "") if ord(c) < 128).strip()


def user_tag(user):
    username = (user or {}).get("username")
    uid = (user or {}).get("id", "?")
    return f"@{username} | ID {uid}" if username else f"ID {uid}"


def make_teaser_image(data, label, tag):
    """Blurred sneak-peek of a photo: small, heavily blurred, with a
    bottom bar carrying the tab label and the viewer's tag."""
    from PIL import Image, ImageDraw, ImageFilter
    import io

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((480, 480))
    im = im.filter(ImageFilter.GaussianBlur(10))
    d = ImageDraw.Draw(im)
    w, h = im.size
    bar_h = max(44, h // 5)
    d.rectangle([0, h - bar_h, w, h], fill=(0, 0, 0, 170))
    f_label = _load_font(max(18, bar_h // 3))
    f_tag = _load_font(max(12, bar_h // 5))
    lines = [(_safe_text(label), f_label, (255, 255, 255, 255))]
    if (tag or "").strip():
        lines.append((_safe_text(tag), f_tag, (200, 200, 200, 255)))
    heights = [d.textbbox((0, 0), t, font=f)[3] for t, f, _c in lines]
    y = h - bar_h + max(4, (bar_h - sum(heights) - 4 * (len(lines) - 1)) // 2)
    for (t, f, c), th in zip(lines, heights):
        d.text((10, y), t, font=f, fill=c)
        y += th + 4
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def make_video_placeholder(label, tag):
    """Teaser for a video with no stored thumbnail: dark card with the
    label, so the tab still gets a visible sneak peek."""
    from PIL import Image, ImageDraw
    import io

    im = Image.new("RGB", (480, 360), (24, 24, 32))
    d = ImageDraw.Draw(im)
    d.text(
        (24, 120), _safe_text(label), font=_load_font(28), fill=(255, 255, 255, 255)
    )
    d.text(
        (24, 165), "VIDEO - PAID", font=_load_font(20), fill=(200, 200, 200, 255)
    )
    d.text((24, 200), _safe_text(tag), font=_load_font(16), fill=(160, 160, 160, 255))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def send_photo_bytes(chat_id, jpeg_bytes, caption=None, meta=None):
    payload = {"chat_id": str(chat_id), "protect_content": "true"}
    if caption:
        payload["caption"] = caption
    files = {"photo": ("teaser.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
    r = api("sendPhoto", payload, files=files)
    if r.get("ok"):
        m = meta or {}
        record_sent(
            chat_id,
            r["result"]["message_id"],
            m.get("kind", "teaser"),
            board=m.get("board"),
            user=m.get("user"),
        )
    return r


def get_teaser_bytes(btn, tag):
    """Build (or load from cache) the teaser JPEG for one tab.
    Returns None when the source can't be fetched."""
    import hashlib

    label = btn["label"]
    kind = btn.get("kind", "photo")
    key = f"{btn.get('file_id')}:{label}:{tag}"
    cache_dir = os.path.join(DATA_DIR, "teasers")
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(
        cache_dir, hashlib.sha256(key.encode()).hexdigest()[:20] + ".jpg"
    )
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read()
    if kind == "video":
        thumb_id = btn.get("thumb")
        data = get_file_bytes(thumb_id) if thumb_id else None
        teaser = (
            make_teaser_image(data, label, tag)
            if data
            else make_video_placeholder(label, tag)
        )
    else:
        data = get_file_bytes(btn["file_id"])
        if not data:
            return None
        teaser = make_teaser_image(data, label, tag)
    with open(path, "wb") as fh:
        fh.write(teaser)
    return teaser


def send_board_teasers(chat_id, board, tag):
    """One blurred teaser photo per tab, each captioned with its label,
    sent just above the board message."""
    for btn in board["buttons"]:
        label = btn["label"]
        kind = btn.get("kind", "photo")
        caption = label + (" 🔒" if kind == "video" else "")
        try:
            teaser = get_teaser_bytes(btn, tag)
            if teaser is None:
                continue
            send_photo_bytes(
                chat_id,
                teaser,
                caption=caption,
                meta={"kind": "teaser", "board": board["id"], "user": chat_id},
            )
        except Exception as e:
            print(f"teaser error for {label}: {e}", flush=True)
            continue


def send_media_group(chat_id, items, meta=None):
    """Send 2-10 photos as one album. items: list of (jpeg_bytes, caption)."""
    media = []
    files = {}
    for i, (data, caption) in enumerate(items):
        key = f"photo{i}"
        files[key] = (f"teaser{i}.jpg", io.BytesIO(data), "image/jpeg")
        entry = {"type": "photo", "media": f"attach://{key}"}
        if caption:
            entry["caption"] = caption
        media.append(entry)
    r = api(
        "sendMediaGroup",
        {
            "chat_id": str(chat_id),
            "media": json.dumps(media),
            "protect_content": "true",
        },
        files=files,
    )
    if r.get("ok"):
        m = meta or {}
        for msg in r["result"]:
            record_sent(
                chat_id,
                msg["message_id"],
                m.get("kind", "teaser"),
                board=m.get("board"),
                user=m.get("user"),
            )
    return r


def send_channel_teasers(channel, board):
    """The channel post gets the same cover photos: one album of teasers
    (label captions, no per-user tag) above the board message."""
    items = []
    for btn in board["buttons"]:
        label = btn["label"]
        kind = btn.get("kind", "photo")
        try:
            teaser = get_teaser_bytes(btn, "")
            if teaser is None:
                continue
            items.append((teaser, label + (" 🔒" if kind == "video" else "")))
        except Exception as e:
            print(f"channel teaser error for {label}: {e}", flush=True)
            continue
    meta = {"kind": "teaser", "board": board["id"]}
    for start in range(0, len(items), 10):
        chunk = items[start : start + 10]
        if len(chunk) == 1:
            send_photo_bytes(channel, chunk[0][0], caption=chunk[0][1], meta=meta)
        else:
            send_media_group(channel, chunk, meta=meta)


def send_board_view(chat_id, board, tag, include_open=False):
    """Teasers first, then the board text with its tab buttons."""
    send_board_teasers(chat_id, board, tag)
    send_message(
        chat_id,
        board_text(board),
        reply_markup=board_keyboard(board, include_open=include_open),
    )


def watermark_image(data, tag):
    """Burn a per-user tag into a photo: faint diagonal repeat + a
    readable bottom bar. Tag must be ASCII (fonts may lack other glyphs)."""
    from PIL import Image, ImageDraw

    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    base = im.convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # faint diagonal repeat (hard to crop out)
    f_diag = _load_font(max(20, w // 26))
    tile = Image.new("RGBA", (w // 2, h // 4), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.text((10, 10), tag, font=f_diag, fill=(255, 255, 255, 70))
    tile = tile.rotate(30, expand=True, resample=Image.BICUBIC)
    tw, th = tile.size
    for x in range(-tw, w + tw, tw):
        for y in range(-th, h + th, th):
            overlay.alpha_composite(tile, (x, y))
    # readable bottom bar
    bar_h = max(30, h // 14)
    d.rectangle([0, h - bar_h, w, h], fill=(0, 0, 0, 150))
    f_bar = _load_font(max(16, bar_h // 2))
    d.text((12, h - bar_h + bar_h // 4), tag, font=f_bar, fill=(255, 255, 255, 255))
    out = Image.alpha_composite(base, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def send_watermarked_photo(chat_id, file_id, tag, meta=None):
    """Send a photo with the user's tag burned in. Falls back to the
    original (still protected) photo if anything fails, so a tap never
    silently breaks."""
    data = get_file_bytes(file_id)
    if data:
        try:
            wm = watermark_image(data, tag)
            files = {"photo": ("photo.jpg", io.BytesIO(wm), "image/jpeg")}
            payload = {"chat_id": str(chat_id), "protect_content": "true"}
            r = api("sendPhoto", payload, files=files)
            if r.get("ok"):
                m = meta or {}
                record_sent(
                    chat_id,
                    r["result"]["message_id"],
                    m.get("kind", "photo"),
                    board=m.get("board"),
                    user=m.get("user"),
                )
                return r
            print(f"watermarked send failed, falling back: {r}", flush=True)
        except Exception as e:
            print(f"watermark error, falling back: {e}", flush=True)
    return send_photo(chat_id, file_id, meta=meta)


def looks_like_tx_hash(text):
    return (
        len(text) == 66
        and text.startswith("0x")
        and all(c in "0123456789abcdefABCDEF" for c in text[2:])
    )


def verify_usdt_tx(tx_hash, min_units=USDT_MIN):
    """Check a BSC transaction for a USDT transfer to Arkar of at least
    min_units. Returns (True, '', value_units) or (False, reason, value).
    Uses public BSC nodes, no key."""
    network_error = False
    for url in BSC_RPC:
        try:
            r = requests.post(
                url,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionReceipt",
                    "params": [tx_hash],
                    "id": 1,
                },
                timeout=15,
            )
            res = r.json().get("result")
        except Exception:
            network_error = True
            continue
        if not res:
            continue  # not mined yet on this node; try the next
        if res.get("status") != "0x1":
            return False, "That transaction failed on-chain — no payment arrived.", 0
        for log in res.get("logs", []):
            if log.get("address", "").lower() != USDT_CONTRACT:
                continue
            topics = log.get("topics", [])
            if len(topics) < 3 or topics[0].lower() != TRANSFER_TOPIC:
                continue
            to_addr = "0x" + topics[2][-40:]
            if to_addr.lower() != USDT_ADDRESS:
                continue
            try:
                value = int(log.get("data", "0x0"), 16)
            except Exception:
                continue
            if value >= min_units:
                return True, "", value
            return (
                False,
                f"That transaction only sent {fmt_usd(value // 10_000)} USDT — "
                f"at least {fmt_usd(min_units // 10_000)} is needed.",
                value,
            )
        return False, "No USDT transfer to my address in that transaction.", 0
    if network_error:
        return False, "Could not reach the network — try again in a minute.", 0
    return False, "Transaction not confirmed yet — wait a bit and paste the hash again.", 0


def send_balance_view(user_id):
    """Show the user's balance + top-up buttons (Stars or USDT)."""
    balance = get_balance(user_id)
    rows = []
    for usd in TOPUP_USD:
        stars = usd * STARS_PER_USD
        rows.append(
            [
                {
                    "text": f"⭐ ${usd} ({stars:,} Stars)",
                    "callback_data": f"topup:{usd * 100}",
                },
                {
                    "text": f"💎 ${usd} USDT",
                    "callback_data": f"topup_usdt:{usd * 100}",
                },
            ]
        )
    return send_message(
        user_id,
        f"💰 Your balance: {fmt_usd(balance)}\n\n"
        f"Top up with Telegram Stars (1$ = {STARS_PER_USD} Stars) "
        "or USDT (1 USDT = $1, BSC/BEP20).\n"
        f"A video costs {fmt_usd(VIDEO_PRICE_CENTS)} of balance.",
        reply_markup={"inline_keyboard": rows},
    )


def send_payment_options(user_id, board, idx, btn):
    rows = [
        [
            {
                "text": f"⭐ Pay {STARS_PRICE} Stars",
                "callback_data": f"pay_stars:{board['id']}:{idx}",
            }
        ],
        [
            {
                "text": "💎 Pay 1 USDT (crypto)",
                "callback_data": f"pay_usdt:{board['id']}:{idx}",
            }
        ],
    ]
    balance = get_balance(user_id)
    if balance >= VIDEO_PRICE_CENTS:
        rows.append(
            [
                {
                    "text": f"💰 Pay {fmt_usd(VIDEO_PRICE_CENTS)} from balance ({fmt_usd(balance)})",
                    "callback_data": f"pay_balance:{board['id']}:{idx}",
                }
            ]
        )
    kb = {"inline_keyboard": rows}
    text = (
        f"This video is paid — one-time access:\n\n\"{btn['label']}\"\n\n"
        f"⭐ {STARS_PRICE} Telegram Stars, or\n"
        "💎 1 USDT on BSC (BEP20)"
    )
    if balance >= VIDEO_PRICE_CENTS:
        text += f", or\n💰 {fmt_usd(VIDEO_PRICE_CENTS)} from your balance ({fmt_usd(balance)})."
    else:
        text += ".\n\nTop up your balance from the 💰 My Balance button on the board."
    text += "\n\nPay once and it is yours to watch."
    send_message(user_id, text, reply_markup=kb)


def handle_successful_payment(chat_id, user_id, sp, state):
    payload = sp.get("invoice_payload", "")
    parts = payload.split(":")
    if len(parts) == 3 and parts[0] == "topup" and parts[2] == str(user_id):
        # Credit the Stars actually received (1 Star = 1 cent at 1$ = 100 Stars).
        cents = int(sp.get("total_amount", 0) or 0)
        if cents <= 0:
            return
        total = add_balance(user_id, cents)
        send_message(
            user_id,
            f"Topped up {fmt_usd(cents)} — your balance is now {fmt_usd(total)}.",
        )
        return
    if len(parts) != 4 or parts[0] != "video" or parts[3] != str(user_id):
        return
    _, bid, idx, _ = parts
    board = state["boards"].get(bid)
    if not board:
        return
    try:
        btn = board["buttons"][int(idx)]
    except (ValueError, IndexError):
        return
    mark_unlocked(user_id, bid, int(idx))
    r = send_video(
        user_id, btn["file_id"], meta={"kind": "video", "board": bid, "user": user_id}
    )
    if r.get("ok"):
        send_message(user_id, "Payment received — enjoy the video.")
    else:
        send_message(
            user_id,
            "Payment received, but I could not send the video — "
            "tap the button again and it will come through (already paid).",
        )


def handle_usdt_hash(chat_id, user_id, tx_hash, state):
    pending = (state.get("pending_usdt") or {}).get(str(user_id))
    if not pending:
        send_message(
            chat_id,
            "I don't have a pending USDT payment for you — "
            "tap a 🔒 video button first, or a 💎 USDT top-up in your balance.",
        )
        return
    if tx_used(tx_hash):
        send_message(chat_id, "That transaction was already used.")
        return
    kind = pending.get("kind", "video")
    if kind == "topup":
        cents = pending["cents"]
        ok, reason, value = verify_usdt_tx(tx_hash, cents * 10_000)
        if not ok:
            send_message(chat_id, f"Not verified yet: {reason}")
            return
        mark_tx_used(tx_hash)
        credited = value // 10_000  # USDT units -> USD cents (1 USDT = $1)
        total = add_balance(user_id, credited)
        state["pending_usdt"].pop(str(user_id), None)
        save_boards(state)
        send_message(
            user_id,
            f"USDT received — topped up {fmt_usd(credited)}. "
            f"Your balance is now {fmt_usd(total)}.",
        )
        return
    ok, reason, _value = verify_usdt_tx(tx_hash)
    if not ok:
        send_message(chat_id, f"Not verified yet: {reason}")
        return
    bid, idx = pending["board"], pending["idx"]
    board = state["boards"].get(bid)
    if not board:
        send_message(chat_id, "That board is gone.")
        return
    try:
        btn = board["buttons"][idx]
    except IndexError:
        send_message(chat_id, "That video is gone.")
        return
    mark_tx_used(tx_hash)
    mark_unlocked(user_id, bid, idx)
    state["pending_usdt"].pop(str(user_id), None)
    save_boards(state)
    r = send_video(
        user_id, btn["file_id"], meta={"kind": "video", "board": bid, "user": user_id}
    )
    if r.get("ok"):
        send_message(user_id, "USDT received — enjoy the video.")
    else:
        send_message(
            user_id,
            "USDT received, but I could not send the video — "
            "tap the button again and it will come through (already paid).",
        )


def answer_callback(callback_id, text=None, show_alert=False, url=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    if url:
        payload["url"] = url
    return api("answerCallbackQuery", payload)


def bot_username():
    r = api("getMe")
    if r.get("ok"):
        return r["result"].get("username", "")
    return ""


def board_keyboard(board, include_open=True):
    """Channel post (include_open=True): every tab is a deep link that
    opens the bot chat, where the board's tabs are shown for choosing.
    DM view / admin preview (include_open=False): real callback buttons
    that deliver the photo/video right there. If the bot's username
    cannot be read, fall back to callback buttons."""
    rows = []
    uname = bot_username() if include_open else ""
    for i, btn in enumerate(board["buttons"]):
        label = btn["label"]
        if btn.get("kind", "photo") == "video":
            label = f"{label} 🔒"
        if uname:
            rows.append(
                [
                    {
                        "text": label,
                        "url": f"https://t.me/{uname}?start=board_{board['id']}",
                    }
                ]
            )
        else:
            rows.append(
                [{"text": label, "callback_data": f"reveal:{board['id']}:{i}"}]
            )
    if uname:
        rows.append(
            [
                {
                    "text": "💰 My Balance",
                    "url": f"https://t.me/{uname}?start=balance",
                }
            ]
        )
    else:
        rows.append([{"text": "💰 My Balance", "callback_data": "balance"}])
    return {"inline_keyboard": rows}


def board_text(board):
    lines = [
        board["title"],
        "",
        "Tap a tab — it opens the bot chat, where you pick and the photo comes to your private chat.",
    ]
    if any(b.get("kind", "photo") == "video" for b in board["buttons"]):
        lines.append(
            f"🔒 Video tabs are paid: {STARS_PRICE} ⭐, 1 USDT, or "
            f"{fmt_usd(VIDEO_PRICE_CENTS)} balance — one-time."
        )
    return "\n".join(lines)


def is_admin(chat_id):
    return str(chat_id) in ADMIN_IDS


def handle_start(chat_id, text, state, user=None):
    parts = text.split()
    if len(parts) > 1 and parts[1] == "balance":
        send_balance_view(chat_id)
        return
    if len(parts) > 1 and parts[1].startswith("board_"):
        bid = parts[1][len("board_"):]
        board = state["boards"].get(bid)
        if board:
            send_board_view(chat_id, board, user_tag(user), include_open=False)
            return
        send_message(chat_id, "That board is gone. Check the channel for the latest one.")
        return
    if is_admin(chat_id):
        send_message(
            chat_id,
            "Daddy3.0 admin.\n\n"
            "/newboard — design a new board\n"
            "/boards — list your boards\n"
            "/post <id> — post a board to the channel\n"
            "/setchannel <@channel> — where boards go\n"
            "/delboard <id> — delete a board\n"
            "/help — full help",
        )
        return
    send_message(
        chat_id,
        "Welcome to Daddy3.0.\n\n"
        "The game boards live in the channel — tap a button there and "
        "the photo comes straight to this private chat.\n"
        "💰 My Balance on any board shows your balance and lets you top up.",
    )


def handle_help(chat_id):
    send_message(
        chat_id,
        "Design a board:\n\n"
        "1. /newboard — I ask for a title, you send it.\n"
        "2. Send photos, one by one — FREE tabs. The CAPTION on each "
        "photo becomes its button label — e.g. caption \"Show his balls\".\n"
        "   Send a VIDEO instead for a PAID tab — same caption rule. "
        f"Video tabs cost {STARS_PRICE} Stars or 1 USDT, one-time.\n"
        "3. /done — saves the board and shows a preview.\n"
        "4. /post <id> — posts it to the channel.\n\n"
        "Other commands:\n"
        "/boards — list boards\n"
        "/delboard <id> — delete one\n"
        "/revoke user <id> / board <id> / all — delete what the bot sent\n"
        "/setchannel <@channel> — where boards go (or forward any channel\n"
        "  post to me and I take the channel's id from it)\n"
        "/cancel — throw the draft away",
    )


def handle_message(msg, state):
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"].get("type", "private")
    text = (msg.get("text") or "").strip()
    user_id = msg.get("from", {}).get("id")

    if chat_type != "private":
        return

    if text.startswith("/start"):
        handle_start(chat_id, text, state, user=msg.get("from", {}))
        return

    sp = msg.get("successful_payment")
    if sp:
        handle_successful_payment(chat_id, user_id, sp, state)
        return

    if not is_admin(chat_id):
        if looks_like_tx_hash(text):
            handle_usdt_hash(chat_id, user_id, text, state)
            return
        if text == "/balance":
            send_balance_view(chat_id)
            return
        if text.startswith("/"):
            send_message(
                chat_id,
                "Boards live in the channel — tap a button there and the "
                "photo comes to this private chat.",
            )
        return

    # ---- admin ----
    # forwarded channel post -> store the channel's numeric id as target
    fwd = msg.get("forward_from_chat")
    if fwd and fwd.get("type") == "channel":
        state["channel"] = str(fwd["id"])
        save_boards(state)
        send_message(
            chat_id,
            f"Channel set to {fwd.get('title', fwd['id'])} ({fwd['id']}). "
            "Boards will post there now.",
        )
        return

    if text == "/help":
        handle_help(chat_id)
        return

    if text == "/cancel":
        state["draft"] = None
        save_boards(state)
        send_message(chat_id, "Draft discarded.")
        return

    if text == "/newboard":
        state["draft"] = {"title": None, "buttons": []}
        save_boards(state)
        send_message(chat_id, "New board. Send me the board title (the text on the post).")
        return

    if text == "/done":
        draft = state.get("draft")
        if not draft or not draft.get("title"):
            send_message(chat_id, "No draft yet — /newboard first, then send a title.")
            return
        if not draft["buttons"]:
            send_message(chat_id, "The board has no buttons yet — send at least one photo (or a video) with a caption.")
            return
        bid = new_board_id(state)
        board = {"id": bid, "title": draft["title"], "buttons": draft["buttons"]}
        state["boards"][bid] = board
        state["draft"] = None
        save_boards(state)
        send_message(chat_id, f"Saved as {bid} — preview:")
        send_board_view(chat_id, board, user_tag(msg.get("from", {})), include_open=False)
        send_message(chat_id, f"Post it with: /post {bid}")
        return

    if text == "/boards":
        boards = state["boards"]
        if not boards:
            send_message(chat_id, "No boards yet. /newboard to make one.")
            return
        lines = ["Your boards:"]
        for bid, b in boards.items():
            lines.append(f"{bid} — {b['title']} ({len(b['buttons'])} buttons)")
        lines.append("\nPost one with /post <id>")
        send_message(chat_id, "\n".join(lines))
        return

    if text.startswith("/delboard"):
        parts = text.split()
        if len(parts) < 2 or parts[1] not in state["boards"]:
            send_message(chat_id, "Usage: /delboard <id> — see /boards for ids.")
            return
        title = state["boards"][parts[1]]["title"]
        del state["boards"][parts[1]]
        save_boards(state)
        send_message(chat_id, f"Deleted {parts[1]} ({title}).")
        return

    if text.startswith("/revoke"):
        parts = text.split()
        sent = load_json_file(SENT_PATH, [])
        if len(parts) < 2:
            send_message(
                chat_id,
                "Usage:\n"
                "/revoke user <telegram id> — everything sent to that user\n"
                "/revoke board <id> — that board's channel post + all media sent from it\n"
                "/revoke all — everything the bot ever sent (and logged)",
            )
            return
        scope = parts[1]
        if scope == "all":
            targets = sent
        elif scope == "user" and len(parts) >= 3:
            targets = [e for e in sent if e.get("user") == parts[2]]
        elif scope == "board" and len(parts) >= 3:
            targets = [e for e in sent if e.get("board") == parts[2]]
        else:
            send_message(
                chat_id,
                "Usage:\n/revoke user <telegram id>\n/revoke board <id>\n/revoke all",
            )
            return
        if not targets:
            send_message(chat_id, "Nothing recorded for that — nothing to revoke.")
            return
        send_message(chat_id, f"Revoking {len(targets)} messages…")
        deleted, failed, pruned = revoke_entries(targets)
        remaining = [e for e in sent if e not in pruned]
        save_json_file(SENT_PATH, remaining)
        send_message(
            chat_id,
            f"Revoked {deleted} messages."
            + (f" {failed} could not be deleted." if failed else ""),
        )
        return

    if text.startswith("/setchannel"):
        parts = text.split()
        if len(parts) < 2:
            cur = state.get("channel") or "(not set)"
            send_message(chat_id, f"Current channel: {cur}\nUsage: /setchannel <@channel>")
            return
        target = parts[1]
        if target.startswith("https://t.me/+") or "joinchat" in target:
            # An invite link is not a chat id — Telegram will refuse every
            # post with "chat not found". The fix is a forwarded post.
            send_message(
                chat_id,
                "That's an invite link — Telegram won't let me post to it.\n"
                "Instead, open the channel, long-press any post, Forward it "
                "to me, and I'll pick up the channel's real ID. Then /post again.",
            )
            return
        state["channel"] = target
        save_boards(state)
        send_message(
            chat_id,
            f"Channel set to {target}.\n"
            "Make sure the bot is an admin in that channel, or posting will fail.",
        )
        return

    if text.startswith("/post"):
        parts = text.split()
        channel = state.get("channel")
        if not channel:
            send_message(chat_id, "No channel set yet — /setchannel <@channel> first.")
            return
        if channel.startswith("https://t.me/+") or "joinchat" in channel:
            send_message(
                chat_id,
                "The channel is still set to an invite link, which Telegram "
                "won't accept — that's why posting fails.\n"
                "Open the channel, long-press any post, Forward it to me, "
                "and I'll set the real channel ID. Then send /post "
                f"{parts[1] if len(parts) > 1 else '<id>'} again.",
            )
            return
        bid = parts[1] if len(parts) > 1 else None
        if not bid or bid not in state["boards"]:
            send_message(chat_id, "Usage: /post <id> — see /boards for ids.")
            return
        board = state["boards"][bid]
        send_channel_teasers(channel, board)
        r = send_message(
            channel,
            board_text(board),
            reply_markup=board_keyboard(board),
            meta={"kind": "board", "board": bid},
        )
        if r.get("ok"):
            send_message(chat_id, f"Posted {bid} to {channel}.")
        else:
            send_message(
                chat_id,
                "Posting failed — is the bot an admin in the channel? "
                f"Telegram said: {r.get('description', 'unknown error')}",
            )
        return

    # photo with caption -> add a FREE button to the draft
    if msg.get("photo"):
        draft = state.get("draft")
        if not draft:
            send_message(chat_id, "No draft open — /newboard first.")
            return
        if draft.get("title") is None:
            send_message(chat_id, "Send the board title first (plain text), then the photos.")
            return
        label = (msg.get("caption") or "").strip()
        if not label:
            send_message(chat_id, "That photo has no caption — the caption becomes the button label. Send it again with a caption.")
            return
        file_id = msg["photo"][-1]["file_id"]
        draft["buttons"].append({"label": label, "file_id": file_id, "kind": "photo"})
        save_boards(state)
        send_message(
            chat_id,
            f"Added button \"{label}\" ({len(draft['buttons'])} on this board). "
            "Send another photo, or a video for a paid tab, or /done to save.",
        )
        return

    # video with caption -> add a PAID button to the draft
    if msg.get("video"):
        draft = state.get("draft")
        if not draft:
            send_message(chat_id, "No draft open — /newboard first.")
            return
        if draft.get("title") is None:
            send_message(chat_id, "Send the board title first (plain text), then the video.")
            return
        label = (msg.get("caption") or "").strip()
        if not label:
            send_message(chat_id, "That video has no caption — the caption becomes the button label. Send it again with a caption.")
            return
        file_id = msg["video"]["file_id"]
        thumb_id = (msg["video"].get("thumb") or {}).get("file_id")
        draft["buttons"].append(
            {"label": label, "file_id": file_id, "kind": "video", "thumb": thumb_id}
        )
        save_boards(state)
        send_message(
            chat_id,
            f"Added PAID video tab \"{label}\" ({len(draft['buttons'])} on this board). "
            f"Watching it costs {STARS_PRICE} Stars or 1 USDT. "
            "Send another photo or video, or /done to save.",
        )
        return

    # plain text while a draft is open and title not set -> title
    draft = state.get("draft")
    if draft is not None and draft.get("title") is None and text and not text.startswith("/"):
        draft["title"] = text
        save_boards(state)
        send_message(
            chat_id,
            f"Title set: {text}\n\nNow send the photos, one by one — "
            "caption each one with its button label. "
            "Send a VIDEO instead for a paid tab.",
        )
        return

    if text.startswith("/"):
        send_message(chat_id, "Unknown command. /help for the list.")
    else:
        send_message(chat_id, "Nothing to do with that — /newboard to start a board, /help for the list.")


def handle_callback(query, state):
    data = query.get("data", "")
    user_id = query["from"]["id"]
    qid = query["id"]

    if data == "balance":
        r = send_balance_view(user_id)
        if r and r.get("ok"):
            answer_callback(qid, "Balance sent to your private chat.")
        else:
            uname = bot_username()
            url = f"https://t.me/{uname}?start=balance" if uname else None
            answer_callback(
                qid,
                "Tap START on the bot first, then tap the button again.",
                show_alert=True,
                url=url,
            )
        return

    if data.startswith("topup:"):
        try:
            cents = int(data.split(":")[1])
        except (IndexError, ValueError):
            answer_callback(qid, "Unknown button.")
            return
        if cents not in [usd * 100 for usd in TOPUP_USD]:
            answer_callback(qid, "Unknown top-up amount.")
            return
        usd = cents // 100
        r = api(
            "sendInvoice",
            {
                "chat_id": user_id,
                "title": f"Top up ${usd}",
                "description": f"Add ${usd} to your Daddy3.0 balance.",
                "payload": f"topup:{cents}:{user_id}",
                "provider_token": "",
                "currency": "XTR",
                "prices": [{"label": f"Top up ${usd}", "amount": cents}],
                "protect_content": True,
            },
        )
        if r.get("ok"):
            record_sent(
                user_id,
                r["result"]["message_id"],
                "invoice",
                user=user_id,
            )
            answer_callback(qid, "Top-up invoice sent — check your private chat.")
        else:
            answer_callback(
                qid,
                "Stars payment is not available right now — try again later.",
                show_alert=True,
            )
        return

    if data.startswith("topup_usdt:"):
        try:
            cents = int(data.split(":")[1])
        except (IndexError, ValueError):
            answer_callback(qid, "Unknown button.")
            return
        if cents not in [usd * 100 for usd in TOPUP_USD]:
            answer_callback(qid, "Unknown top-up amount.")
            return
        usd = cents // 100
        state.setdefault("pending_usdt", {})[str(user_id)] = {
            "kind": "topup",
            "cents": cents,
        }
        send_message(
            user_id,
            f"Top up {fmt_usd(cents)} with USDT on BSC (BEP20):\n\n"
            f"<code>{USDT_ADDRESS}</code>\n\n"
            f"Send {fmt_usd(cents)} USDT to that address, then paste your "
            "transaction hash here (starts with 0x, 66 characters). "
            "I will check it on-chain and add it to your balance.",
            parse_mode="HTML",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "📋 Copy USDT address",
                            "copy_text": {"text": USDT_ADDRESS},
                        }
                    ]
                ]
            },
        )
        answer_callback(qid, "USDT address sent — check your private chat.")
        return

    parts = data.split(":")
    if len(parts) != 3:
        answer_callback(qid, "Unknown button.")
        return
    action, bid, idx = parts
    board = state["boards"].get(bid)
    if not board:
        answer_callback(qid, "That board is gone.", show_alert=True)
        return
    try:
        i = int(idx)
        btn = board["buttons"][i]
    except (ValueError, IndexError):
        answer_callback(qid, "Unknown button.", show_alert=True)
        return

    if action == "pay_balance":
        if btn.get("kind", "photo") != "video":
            answer_callback(qid, "Unknown button.")
            return
        if not deduct_balance(user_id, VIDEO_PRICE_CENTS):
            answer_callback(
                qid,
                "Not enough balance — top up from the 💰 My Balance button.",
                show_alert=True,
            )
            return
        mark_unlocked(user_id, bid, i)
        r = send_video(
            user_id,
            btn["file_id"],
            meta={"kind": "video", "board": bid, "user": user_id},
        )
        if r.get("ok"):
            answer_callback(
                qid,
                f"Paid {fmt_usd(VIDEO_PRICE_CENTS)} from your balance — video sent.",
            )
        else:
            add_balance(user_id, VIDEO_PRICE_CENTS)  # refund: video never arrived
            answer_callback(
                qid,
                "Could not send the video — your balance was refunded.",
                show_alert=True,
            )
        return

    if action == "pay_stars":
        r = api(
            "sendInvoice",
            {
                "chat_id": user_id,
                "title": f"Video: {btn['label'][:24]}",
                "description": "One-time access to this video.",
                "payload": f"video:{bid}:{i}:{user_id}",
                "provider_token": "",
                "currency": "XTR",
                "prices": [{"label": "Video access", "amount": STARS_PRICE}],
                "protect_content": True,
            },
        )
        if r.get("ok"):
            record_sent(
                user_id,
                r["result"]["message_id"],
                "invoice",
                board=bid,
                user=user_id,
            )
            answer_callback(qid, "Invoice sent — check your private chat.")
        else:
            answer_callback(
                qid,
                "Stars payment is not available right now — try the USDT option.",
                show_alert=True,
            )
        return

    if action == "pay_usdt":
        state.setdefault("pending_usdt", {})[str(user_id)] = {
            "kind": "video",
            "board": bid,
            "idx": i,
        }
        send_message(
            user_id,
            "Pay 1 USDT on BSC (BEP20) to:\n\n"
            f"<code>{USDT_ADDRESS}</code>\n\n"
            "Then paste your transaction hash here "
            "(starts with 0x, 66 characters). "
            "I will check it on-chain and send the video.",
            parse_mode="HTML",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "📋 Copy USDT address",
                            "copy_text": {"text": USDT_ADDRESS},
                        }
                    ]
                ]
            },
        )
        answer_callback(qid, "USDT address sent — check your private chat.")
        return

    if action != "reveal":
        answer_callback(qid, "Unknown button.")
        return

    # ---- reveal: photo (free) or video (paid) ----
    if btn.get("kind", "photo") == "video":
        if is_unlocked(user_id, bid, i):
            r = send_video(
                user_id,
                btn["file_id"],
                meta={"kind": "video", "board": bid, "user": user_id},
            )
            if r.get("ok"):
                answer_callback(qid, "Sent to your private chat.")
            else:
                answer_callback(
                    qid,
                    "Could not send the video — tap START on the bot first, then tap again.",
                    show_alert=True,
                )
        else:
            send_payment_options(user_id, board, i, btn)
            answer_callback(qid, "This video is paid — choose how to pay.")
        return

    user = query.get("from", {})
    tag = user_tag(user)
    r = send_watermarked_photo(
        user_id,
        btn["file_id"],
        tag,
        meta={"kind": "photo", "board": bid, "user": user_id},
    )
    if r.get("ok"):
        answer_callback(qid, "Sent to your private chat.")
    else:
        uname = bot_username()
        url = f"https://t.me/{uname}?start=board_{bid}" if uname else None
        answer_callback(
            qid,
            "Tap START on the bot first, then tap the button again.",
            show_alert=True,
            url=url,
        )


def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN not set", flush=True)
        return
    print("Daddy3.0 started. Polling for updates...", flush=True)
    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset:
                params["offset"] = offset
            r = requests.get(f"{API}/getUpdates", params=params, timeout=60)
            data = r.json()
        except Exception as e:
            print(f"getUpdates error: {e}", flush=True)
            time.sleep(5)
            continue
        if not data.get("ok"):
            print(f"getUpdates not ok: {data}", flush=True)
            time.sleep(5)
            continue
        state = load_boards()
        dirty = False
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            try:
                if "pre_checkout_query" in upd:
                    q = upd["pre_checkout_query"]
                    api(
                        "answerPreCheckoutQuery",
                        {"pre_checkout_query_id": q["id"], "ok": True},
                    )
                elif "message" in upd:
                    before = json.dumps(state, sort_keys=True)
                    handle_message(upd["message"], state)
                    if json.dumps(state, sort_keys=True) != before:
                        dirty = True
                elif "callback_query" in upd:
                    before = json.dumps(state, sort_keys=True)
                    handle_callback(upd["callback_query"], state)
                    if json.dumps(state, sort_keys=True) != before:
                        dirty = True
            except Exception as e:
                print(f"update error: {e}", flush=True)
        if dirty:
            save_boards(state)


if __name__ == "__main__":
    main()
