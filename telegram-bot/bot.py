#!/usr/bin/env python3
"""
MasterClass English - Telegram auto-reply bot.

Fixed FAQ answers (English + Burmese). Anything it can't answer is
forwarded to the admin, and the admin's reply is relayed back to the student.

Group behaviour (owner rule, 2026-11-02, updated 2026-11-03): in
group/supergroup chats the bot stays silent except when a command is
used (/start or the Commands button) — and even then it does NOT post
the menu in the group. Instead it moves the conversation to the
tapper's private chat (see redirect_to_private): it tries to send the
menu straight to their private chat, and if Telegram blocks that
(the user has never started the bot privately), it posts one short
group message with a tap-to-open private-chat link. Group chatter,
FAQ keyword matches, fallback replies and photo receipts are all
ignored there — the bot must not interject into group conversations.
Private chats keep the full FAQ + fallback behaviour.

Admin block (private chat with the bot only): /block — reply to a
forwarded student message, or /block <user id> — makes the bot
silently ignore that user everywhere (no answer, no forward, no
group redirect). /unblock <user id> reverses it, /blocklist lists
blocked ids. The list lives in blocked.json next to forward_map.json.

Needs env vars:
    BOT_TOKEN     - from @BotFather
    ADMIN_CHAT_ID - your Telegram user id (get it from @userinfobot)
    BOT_USERNAME  - bot username without @ (default: SayarArkarBot),
                    used only for the private-chat deep link

Run:  pip install -r requirements.txt
      BOT_TOKEN=... ADMIN_CHAT_ID=... python bot.py
"""

import json
import os
import time
import unicodedata

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "SayarArkarBot").strip() or "SayarArkarBot"

if not BOT_TOKEN:
    raise SystemExit("Set the BOT_TOKEN env var (get it from @BotFather).")
if not ADMIN_CHAT_ID:
    print("WARNING: ADMIN_CHAT_ID not set - unanswered questions can't be forwarded.")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
STATE_FILE = os.path.join(BASE_DIR, "forward_map.json")

with open(os.path.join(BASE_DIR, "faq.json"), encoding="utf-8") as f:
    FAQ = json.load(f)["entries"]

WELCOME = (
    "Hello! Welcome to MasterClass English by Sayar Arkar. \U0001f64f\n"
    "I can answer common questions - tap a topic below or just type your question.\n\n"
    "\u1019\u1004\u103a\u1002\u101c\u102c\u1015\u102b! MasterClass English by Sayar Arkar \u1019\u103e \u1000\u103c\u102d\u102f\u1006\u102d\u102f\u1015\u102b\u1010\u100e\u103a\u104b \U0001f64f\n"
    "\u1019\u1031\u1038\u101c\u1031\u1037\u101b\u103e\u102d\u1019\u1032\u1037\u1019\u1031\u1038\u1001\u103d\u1014\u103a\u1038\u1004\u1032\u1000\u102d\u102f \u1016\u103c\u1031\u1015\u1038\u1031\u1014\u102d\u102f\u1004\u103a\u1015\u102b\u1010\u100e\u103a - "
    "\u1021\u1031\u102c\u102c\u103a\u1000\u1001\u101c\u102f\u1010\u103a\u1000\u102d\u102f\u1014\u103e\u102d\u1015\u103a\u1015\u102b \u101e\u102d\u102f\u1037\u1019\u101f\u103a \u1019\u1031\u1038\u1001\u103d\u1014\u103a\u1038\u101b\u102d\u102f\u1000\u103a\u1012\u100a\u103a\u1037\u1015\u102b\u104b"
    "\n\nDeveloped by Arkar Myowin"
)

KEYBOARD = {
    "keyboard": [
        [{"text": "\U0001f4da Courses / \u101e\u1004\u103a\u1010\u1014\u103a\u1038\u1019\u103b\u102c\u1038"},
         {"text": "\U0001f4b0 Fees / \u101e\u1004\u103a\u1010\u1014\u103a\u1038\u1000\u103c\u1031\u1038"}],
        [{"text": "\U0001f4dd Enroll / \u1021\u1015\u103a\u1014\u103e\u1036\u101b\u1014\u103a"},
         {"text": "\U0001f64b Talk to teacher / \u1006\u101b\u102c\u1014\u1036\u1037\u1015\u103c\u1031\u102c\u101b\u1014\u103a"}],
        [{"text": "\U0001f4cb Commands"}],
    ],
    "resize_keyboard": True,
}

COMMANDS_BTN = "\U0001f4cb Commands"
COMMANDS_TEXT = (
    "\U0001f4cb Commands — tap a button below or type your question.\n\n"
    "/start — show the main menu again\n\n"
    "\U0001f4cb လုပ်ဆောင်ချက်များ — အောက်က ခလုတ်များကို နှိပ်၍ဖြစ်စေ၊ "
    "မေးခွန်းကို ရိုက်၍ဖြစ်စေ မေးနိုင်ပါသည်။\n\n"
    "/start — main menu ကို ပြန်ပြရန်"
)

FALLBACK_MSG = (
    "Thanks! I've passed your message to Sayar Arkar - he'll reply here soon. \U0001f64f\n"
    "\u1000\u103b\u1031\u1038\u1007\u1030\u1038\u1015\u102b! \u101e\u1004\u1037\u103a\u1019\u1031\u1038\u1001\u103d\u1014\u103a\u1038\u1000\u102d\u102f "
    "\u1006\u101b\u102c\u1011\u1036\u1015\u102d\u102f\u1037\u1015\u1031\u1038\u101c\u102d\u102f\u1000\u103a\u1015\u102b\u1010\u100e\u103a - "
    "\u1019\u1000\u103c\u102c\u1001\u1004\u103a \u1012\u102e\u1019\u103e\u102c\u1015\u1032 \u1015\u103c\u1014\u103a\u1016\u103c\u1031\u1015\u1038\u1031\u1014\u103a\u1015\u102b\u1010\u100e\u103a\u104b \U0001f64f"
)

RECEIPT_MSG = (
    "📸 Receipt received! The admin will check it and confirm here soon. 🙏\n"
    "📸 ပြေစာရရှိပါပြီ! Admin စစ်ဆေးပြီး ဒီမှာပဲ အတည်ပြုပေးပါမယ်။ 🙏"
)


def api(method, **params):
    r = requests.post(f"{API}/{method}", json=params, timeout=60)
    data = r.json()
    if not data.get("ok"):
        print("Telegram API error:", data)
    return data


def send_photo(chat_id, photo_file, caption, msg=None):
    path = os.path.join(BASE_DIR, photo_file)
    params = {"chat_id": chat_id, "caption": caption}
    if msg and msg.get("chat", {}).get("type") in ("group", "supergroup"):
        params["reply_to_message_id"] = msg["message_id"]
    with open(path, "rb") as f:
        r = requests.post(f"{API}/sendPhoto", data=params,
                          files={"photo": f}, timeout=60)
    data = r.json()
    if not data.get("ok"):
        print("Telegram API error:", data)
    return data


def send_threaded(chat_id, text, msg, reply_markup=None):
    """Send a message; in groups, thread it as a reply to the user's message."""
    params = {"chat_id": chat_id, "text": text}
    if msg.get("chat", {}).get("type") in ("group", "supergroup"):
        params["reply_to_message_id"] = msg["message_id"]
    # Persistent visible tab: keep the reply keyboard on every message unless
    # the caller passes an explicit markup.
    params["reply_markup"] = KEYBOARD if reply_markup is None else reply_markup
    return api("sendMessage", **params)


def redirect_to_private(msg):
    """Move a group command tap into the tapper's private chat.

    Telegram does not let a bot open a user's private chat for them,
    and it blocks a first private message to anyone who has never
    started the bot. So: try sending the menu straight to the tapper's
    private chat (works when they have started the bot before); if
    that fails, post one short group message with a deep link that
    opens the private chat when tapped. Either way, the menu and the
    follow-up conversation stay out of the group.
    """
    chat_id = str(msg["chat"]["id"])
    user_id = str(msg.get("from", {}).get("id", ""))
    link = f"https://t.me/{BOT_USERNAME}?start=from_group"
    private_text = COMMANDS_TEXT if msg.get("text") == COMMANDS_BTN else WELCOME
    inline = {"inline_keyboard": [[{"text": "\U0001f4ac Continue in private chat",
                                    "url": link}]]}
    dm_ok = False
    if user_id:
        try:
            dm_ok = bool(api("sendMessage", chat_id=user_id,
                             text=private_text,
                             reply_markup=KEYBOARD).get("ok"))
        except Exception:
            dm_ok = False
    if dm_ok:
        send_threaded(
            chat_id,
            "\u2705 I sent the menu to your private chat — please continue "
            "there, so your questions stay out of the group.",
            msg, reply_markup=inline)
    else:
        send_threaded(
            chat_id,
            "Tap below to continue in your private chat — I can't message "
            "you privately until you have started me there once.",
            msg, reply_markup=inline)


def load_map():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_map(mapping):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f)


BLOCKED_FILE = os.path.join(BASE_DIR, "blocked.json")


def load_blocked():
    try:
        with open(BLOCKED_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return set(str(x) for x in data) if isinstance(data, list) else set()
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_blocked(blocked):
    with open(BLOCKED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(blocked), f)


def norm(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


def find_answer(text):
    """Best FAQ entry by keyword hits (substring match), ties broken by
    keyword coverage so more specific entries win. None if no keyword hit."""
    t = norm(text)
    best, best_key = None, (0, 0)
    for entry in FAQ:
        kws = entry["keywords"]
        hits = sum(1 for kw in kws if norm(kw) and norm(kw) in t)
        if not hits:
            continue
        key = (hits, hits / len(kws))
        if key > best_key:
            best, best_key = entry, key
    return best


def forward_to_admin(chat_id, message_id, fwd_map):
    if not ADMIN_CHAT_ID:
        return
    res = api("forwardMessage", chat_id=ADMIN_CHAT_ID,
              from_chat_id=chat_id, message_id=message_id)
    if res.get("ok"):
        fwd_map[str(res["result"]["message_id"])] = str(chat_id)
        save_map(fwd_map)


def handle_update(upd, fwd_map, blocked):
    msg = upd.get("message")
    if not msg:
        return
    chat_id = str(msg["chat"]["id"])
    is_admin = bool(ADMIN_CHAT_ID) and chat_id == ADMIN_CHAT_ID
    chat_type = msg["chat"].get("type", "")
    user_id = str(msg.get("from", {}).get("id", ""))

    # Blocked users are ignored entirely: no FAQ answer, no forward to
    # the admin, no group redirect, no receipt acknowledgement. The
    # admin is never blocked.
    if not is_admin and user_id and user_id in blocked:
        return

    # Groups: commands only, and commands move to private chat.
    # Anything else — chatter, FAQ keywords, photos — is ignored
    # silently, so the bot never interjects into a group conversation
    # uninvited. (Admin relay below is a private chat flow and is
    # unaffected.)
    if chat_type in ("group", "supergroup"):
        if "text" not in msg:
            return
        if msg["text"].startswith("/start") or msg["text"] == COMMANDS_BTN:
            redirect_to_private(msg)
            return
        return

    # Photo (e.g. payment receipt screenshot): forward to admin, acknowledge.
    if "photo" in msg:
        if not is_admin:
            forward_to_admin(chat_id, msg["message_id"], fwd_map)
            send_threaded(chat_id, RECEIPT_MSG, msg)
        return

    if "text" not in msg:
        return
    text = msg["text"]

    # Admin block commands (private chat only). /block with no argument
    # blocks the student of the forwarded message being replied to.
    if is_admin:
        parts = text.split()
        cmd = parts[0] if parts else ""
        if cmd in ("/block", "/unblock", "/blocklist"):
            if cmd == "/blocklist":
                if blocked:
                    send_threaded(chat_id,
                        "🚫 Blocked users:\n" + "\n".join(sorted(blocked)), msg)
                else:
                    send_threaded(chat_id, "No users are blocked.", msg)
                return
            target = parts[1].strip() if len(parts) > 1 else None
            if target is None and msg.get("reply_to_message"):
                target = fwd_map.get(str(msg["reply_to_message"]["message_id"]))
            if not target:
                send_threaded(chat_id,
                    "Usage: /block <user id> — or reply to a forwarded "
                    "message with /block. /unblock <user id> removes one.",
                    msg)
                return
            if cmd == "/block":
                if target == ADMIN_CHAT_ID:
                    send_threaded(chat_id, "You can't block yourself.", msg)
                    return
                blocked.add(target)
                save_blocked(blocked)
                send_threaded(chat_id, f"🚫 Blocked user {target}. The bot "
                    "will ignore all their messages from now on.", msg)
            elif target in blocked:
                blocked.discard(target)
                save_blocked(blocked)
                send_threaded(chat_id, f"✅ Unblocked user {target}.", msg)
            else:
                send_threaded(chat_id, f"User {target} was not blocked.", msg)
            return

    # Admin replying to a forwarded student message -> relay it back.
    if is_admin and msg.get("reply_to_message"):
        student_id = fwd_map.get(str(msg["reply_to_message"]["message_id"]))
        if student_id:
            api("sendMessage", chat_id=student_id, text=text)
            return
        # Not a forwarded message: fall through to normal handling so the
        # admin can also try out the bot.

    if text.startswith("/start"):
        send_threaded(chat_id, WELCOME, msg, reply_markup=KEYBOARD)
        return

    if text == COMMANDS_BTN:
        send_threaded(chat_id, COMMANDS_TEXT, msg)
        return

    entry = find_answer(text)
    if entry and not entry.get("forward"):
        if entry.get("photo"):
            send_photo(chat_id, entry["photo"], entry["answer"], msg)
        else:
            send_threaded(chat_id, entry["answer"], msg)
    elif is_admin:
        # Never forward the admin's own messages back to themselves.
        send_threaded(chat_id,
            "(Admin note: no FAQ answer matched this, so nothing was "
            "forwarded — you're the admin. A student asking this would "
            "be forwarded to you.)", msg)
    else:
        forward_to_admin(chat_id, msg["message_id"], fwd_map)
        send_threaded(chat_id, FALLBACK_MSG, msg)


def main():
    print("Bot started. Polling for updates...")
    fwd_map = load_map()
    blocked = load_blocked()
    offset = 0
    while True:
        try:
            data = api("getUpdates", offset=offset, timeout=50,
                       allowed_updates=["message"])
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                handle_update(upd, fwd_map, blocked)
        except Exception as e:  # keep polling through network blips
            print("Polling error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
