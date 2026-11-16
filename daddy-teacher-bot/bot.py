"""DaddyTeacher — session-pack bot for Arkar's English class.

An English class for gay learners. 1-hour sessions, each teaching one
topic + 10 new phrases. Students buy session packs and the admin posts
sessions to the teaching group (t.me/DaddyTeachEnglish).

Session packs (anchor 1 USD = 5,000 Ks):
  1 session  — 15,000 Ks = $3  = 300 Stars = 3 USDT
  2 sessions — 20,000 Ks = $4  = 400 Stars = 4 USDT
  4 sessions — 30,000 Ks = $6  = 600 Stars = 6 USDT

Payment methods, in the bot's private chat:
  * Telegram Stars — native Stars invoice (XTR).
  * USDT on BSC (BEP20) — user pastes the transaction hash; the bot
    verifies it on-chain via a public BSC node. The address is shown
    with a one-tap "Copy USDT address" button (standing rule).
  * Myanmar pay — KBZPay / WavePay / AYAPay. The student sends a
    receipt screenshot; it is forwarded to every admin with
    Approve / Decline buttons. Approve adds the session credits.
  * Thai QR / PromptPay — the student messages @SirArkar, then sends
    the receipt here; same admin approve flow.

Admin (Arkar) posts from the bot's DM:
  /newsession <topic> | <date/time>   create + post a session card
  /newsession                         (no args) interactive prompt
  /post <text>                        plain announcement + pack buttons
  /setgroup <@group>                  where sessions go (or forward a
                                      group post / paste a t.me/c link)
  /sessions                           list posted sessions
  /users                              buyers, credits, packs bought
  /sales                              recent purchases (method + status)
  /id                                 the current chat's id

Students:
  /start                              welcome + the three packs
  /mysessions                         remaining session credits
  tap a pack button on a group post — it deep-links into the bot DM,
  where the payment choice happens (invoices go to private chat only)

State lives in JSON files under DATA_DIR (same pattern as daddy-bot):
  state.json      group id, sessions, pending payments, receipts, seq
  credits.json    user id -> session credits remaining
  purchases.json  purchase records (user, pack, method, status, time)
  used_tx.json    USDT transaction hashes already spent
  users.json      everyone who interacted (username + first/last seen)

No watermarking, no protect_content — these are plain text posts.
"""

import json
import os
import re
import time

import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "DaddyTeacherBot")
ADMIN_IDS = {
    x.strip()
    for x in os.environ.get("ADMIN_CHAT_IDS", "7061620871,8028025915").split(",")
    if x.strip()
}
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(DATA_DIR, "state.json")
CREDITS_PATH = os.path.join(DATA_DIR, "credits.json")
PURCHASES_PATH = os.path.join(DATA_DIR, "purchases.json")
USED_TX_PATH = os.path.join(DATA_DIR, "used_tx.json")
USERS_PATH = os.path.join(DATA_DIR, "users.json")
API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

# 1 USD = 5,000 Ks. Stars: 1 USD = 100 Stars. USDT: 1 USDT = $1.
PACKS = {
    "1": {"sessions": 1, "ks": 15000, "usd": 3, "stars": 300, "usdt": 3},
    "2": {"sessions": 2, "ks": 20000, "usd": 4, "stars": 400, "usdt": 4},
    "4": {"sessions": 4, "ks": 30000, "usd": 6, "stars": 600, "usdt": 6},
}

USDT_ADDRESS = os.environ.get(
    "USDT_ADDRESS", "0xffef0a1f5b075ed8763d7e0b13c9e3df04819222"
)  # Arkar's BSC address
USDT_BSCSCAN_URL = "https://bscscan.com/address/" + USDT_ADDRESS
USDT_CONTRACT = "0x55d398326f99059ff775485246999027b3197955"  # USDT on BSC
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BSC_RPC = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.bnbchain.org/",
    "https://bsc-dataseed2.bnbchain.org/",
]
USDT_MIN = 1_000_000  # 1 USDT = 1,000,000 units (6 decimals)

KBZPAY = "09403720481"
WAVEPAY = "09780695959"
AYAPAY = "09754926216"

FOOTER = "Developed by Arkar Myowin"


def pack_label(key):
    p = PACKS[key]
    return f"{p['sessions']} session{'s' if p['sessions'] > 1 else ''} — {p['ks']:,} Ks"


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


def load_state():
    return load_json_file(
        STATE_PATH,
        {
            "group": GROUP_CHAT_ID,
            "sessions": {},
            "seq": 0,
            "pending_usdt": {},
            "pending_mm": {},
            "receipts": {},
            "receipt_seq": 0,
            "draft_session": False,
        },
    )


def save_state(state):
    save_json_file(STATE_PATH, state)


def is_admin(chat_id):
    return str(chat_id) in ADMIN_IDS


def user_tag(user):
    username = (user or {}).get("username")
    uid = (user or {}).get("id", "?")
    return f"@{username} | ID {uid}" if username else f"ID {uid}"


def note_user(user):
    """Remember a user who interacted with the bot (username + first/last
    seen), so /users can list them. Admins are recorded too and filtered
    out at display time."""
    uid = (user or {}).get("id")
    if uid is None:
        return
    data = load_json_file(USERS_PATH, {})
    now = int(time.time())
    entry = data.get(str(uid), {"first_seen": now})
    username = (user or {}).get("username")
    if username:
        entry["username"] = username
    entry["last_seen"] = now
    data[str(uid)] = entry
    save_json_file(USERS_PATH, data)


def get_credits(user_id):
    return int(load_json_file(CREDITS_PATH, {}).get(str(user_id), 0))


def add_credits(user_id, sessions):
    data = load_json_file(CREDITS_PATH, {})
    total = int(data.get(str(user_id), 0)) + sessions
    data[str(user_id)] = total
    save_json_file(CREDITS_PATH, data)
    return total


def record_purchase(user_id, username, pack_key, method, status, tx_hash=None):
    data = load_json_file(PURCHASES_PATH, [])
    data.append(
        {
            "user": str(user_id),
            "username": username or "",
            "pack": pack_key,
            "sessions": PACKS[pack_key]["sessions"],
            "ks": PACKS[pack_key]["ks"],
            "method": method,
            "status": status,
            "tx": tx_hash or "",
            "ts": int(time.time()),
        }
    )
    save_json_file(PURCHASES_PATH, data)


def tx_used(tx_hash):
    return tx_hash.lower() in load_json_file(USED_TX_PATH, [])


def mark_tx_used(tx_hash):
    data = load_json_file(USED_TX_PATH, [])
    data.append(tx_hash.lower())
    save_json_file(USED_TX_PATH, data)


def fmt_time(ts):
    return time.strftime("%d-%m-%Y %H:%M", time.localtime(ts))


# ------------------------------------------------------------------ API ---


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


def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return api("sendMessage", payload)


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
        return r["result"].get("username", "") or BOT_USERNAME
    return BOT_USERNAME


def parse_group_link(text):
    """A copied group post link, https://t.me/c/<digits>/..., carries the
    group id: the chat id is -100<digits>."""
    m = re.search(r"t\.me/c/(\d+)", text or "")
    if not m:
        return None
    return "-100" + m.group(1)


# -------------------------------------------------------------- USDT ----


def looks_like_tx_hash(text):
    return (
        len(text) == 66
        and text.startswith("0x")
        and all(c in "0123456789abcdefABCDEF" for c in text[2:])
    )


def verify_usdt_tx(tx_hash, min_units):
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
            if to_addr.lower() != USDT_ADDRESS.lower():
                continue
            try:
                value = int(log.get("data", "0x0"), 16)
            except Exception:
                continue
            if value >= min_units:
                return True, "", value
            return (
                False,
                f"That transaction only sent {value / 1_000_000:g} USDT — "
                f"at least {min_units / 1_000_000:g} is needed.",
                value,
            )
        return False, "No USDT transfer to my address in that transaction.", 0
    if network_error:
        return False, "Could not reach the network — try again in a minute.", 0
    return False, "Transaction not confirmed yet — wait a bit and paste the hash again.", 0


def usdt_copy_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📋 Copy USDT address", "copy_text": {"text": USDT_ADDRESS}}]
        ]
    }


# ----------------------------------------------------------- keyboards ----


def pack_deep_link(key):
    return f"https://t.me/{bot_username()}?start=pack_{key}"


def pack_keyboard(url_buttons=True):
    """The three pack buttons. In the group they are deep links into the
    bot DM (payment happens in private chat only); in the DM they are
    plain callback buttons."""
    rows = []
    for key in ("1", "2", "4"):
        p = PACKS[key]
        label = f"📦 {p['sessions']} session{'s' if p['sessions'] > 1 else ''} — {p['ks']:,} Ks"
        if url_buttons:
            rows.append([{"text": label, "url": pack_deep_link(key)}])
        else:
            rows.append([{"text": label, "callback_data": f"pack:{key}"}])
    if url_buttons:
        rows.append(
            [
                {
                    "text": "💬 My sessions",
                    "url": f"https://t.me/{bot_username()}?start=mysessions",
                }
            ]
        )
    else:
        rows.append([{"text": "💬 My sessions", "callback_data": "mysessions"}])
    return {"inline_keyboard": rows}


def payment_keyboard(key):
    p = PACKS[key]
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"⭐ Pay {p['stars']} Stars",
                    "callback_data": f"pay_stars:{key}",
                }
            ],
            [
                {
                    "text": f"💎 Pay {p['usdt']} USDT (crypto)",
                    "callback_data": f"pay_usdt:{key}",
                }
            ],
            [
                {
                    "text": "🇲🇲 KBZPay / WavePay / AYAPay",
                    "callback_data": f"pay_mm:{key}",
                }
            ],
            [
                {
                    "text": "🇹🇭 Thai QR / PromptPay",
                    "callback_data": f"pay_thai:{key}",
                }
            ],
        ]
    }


def session_text(session):
    return (
        "📚 DaddyTeacher — New Session\n\n"
        f"🎯 Topic: {session['topic']}\n"
        f"🕐 {session['when']}\n"
        "⏱ 1 hour · one topic + 10 new phrases\n\n"
        "Choose your pack — tap to pay in the bot:"
    )


# ------------------------------------------------------------ payments ----


def send_pack_options(user_id, key):
    p = PACKS[key]
    text = (
        f"📦 {pack_label(key)} (${p['usd']})\n\n"
        "How do you want to pay?\n\n"
        f"⭐ {p['stars']} Telegram Stars, or\n"
        f"💎 {p['usdt']} USDT on BSC (BEP20), or\n"
        "🇲🇲 KBZPay / WavePay / AYAPay (send a receipt), or\n"
        "🇹🇭 Thai QR / PromptPay (message @SirArkar, then send a receipt)."
    )
    send_message(user_id, text, reply_markup=payment_keyboard(key))


def mm_payment_text(key):
    p = PACKS[key]
    return (
        f"🇲🇲 Pay {p['ks']:,} Ks for {pack_label(key)} to any of these:\n\n"
        f"• KBZPay: {KBZPAY} (Arkar Myo Win)\n"
        f"• WavePay: {WAVEPAY} (Arkar Myo Win)\n"
        f"• AYAPay: {AYAPAY} (Arkar Myowin)\n\n"
        "Then send your payment receipt screenshot HERE, "
        "and the admin will confirm it and add your sessions."
    )


def credit_pack(user_id, username, key, method, tx_hash=None):
    """Add the pack's sessions and record the purchase. Returns the new
    total credit balance."""
    total = add_credits(user_id, PACKS[key]["sessions"])
    record_purchase(user_id, username, key, method, "paid", tx_hash)
    return total


def handle_successful_payment(chat_id, user_id, sp, user=None):
    payload = sp.get("invoice_payload", "")
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != "pack" or parts[2] != str(user_id):
        return
    key = parts[1]
    if key not in PACKS:
        return
    username = (user or {}).get("username", "")
    total = credit_pack(user_id, username, key, "Stars")
    send_message(
        user_id,
        f"✅ Payment received — {PACKS[key]['sessions']} session"
        f"{'s' if PACKS[key]['sessions'] > 1 else ''} added.\n"
        f"You now have {total} session{'s' if total != 1 else ''}. "
        "See you in class! 🎉",
    )


def handle_usdt_hash(chat_id, user_id, tx_hash, state, user=None):
    pending = (state.get("pending_usdt") or {}).get(str(user_id))
    if not pending:
        send_message(
            chat_id,
            "I don't have a pending USDT payment for you — "
            "tap a pack first, then choose USDT.",
        )
        return
    if tx_used(tx_hash):
        send_message(chat_id, "That transaction was already used.")
        return
    key = pending["pack"]
    p = PACKS[key]
    ok, reason, _value = verify_usdt_tx(tx_hash, p["usdt"] * USDT_MIN)
    if not ok:
        send_message(chat_id, f"Not verified yet: {reason}")
        return
    mark_tx_used(tx_hash)
    state["pending_usdt"].pop(str(user_id), None)
    save_state(state)
    username = (user or {}).get("username", "")
    total = credit_pack(user_id, username, key, "USDT", tx_hash)
    send_message(
        user_id,
        f"✅ USDT received — {p['sessions']} session"
        f"{'s' if p['sessions'] > 1 else ''} added.\n"
        f"You now have {total} session{'s' if total != 1 else ''}. "
        "See you in class! 🎉",
    )


def forward_receipt_to_admins(user_id, user, key, message_id):
    """Forward the receipt photo to every admin with Approve / Decline
    buttons. One receipt id per photo, so only the first decision
    counts — a second admin tapping later gets 'already handled'."""
    state = load_state()
    state["receipt_seq"] = state.get("receipt_seq", 0) + 1
    rid = f"r{state['receipt_seq']}"
    state.setdefault("receipts", {})[rid] = {
        "user": str(user_id),
        "username": (user or {}).get("username", ""),
        "pack": key,
        "status": "pending",
        "ts": int(time.time()),
    }
    save_state(state)
    for admin_id in sorted(ADMIN_IDS):
        api(
            "forwardMessage",
            {
                "chat_id": admin_id,
                "from_chat_id": user_id,
                "message_id": message_id,
            },
        )
        send_message(
            admin_id,
            f"📸 Receipt from {user_tag(user)} — "
            f"{pack_label(key)} ({PACKS[key]['ks']:,} Ks).\n"
            "Tap to add the sessions, or decline.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Approve — add sessions",
                            "callback_data": f"mmok:{rid}",
                        },
                        {
                            "text": "❌ Decline",
                            "callback_data": f"mmno:{rid}",
                        },
                    ]
                ]
            },
        )
    return rid


def handle_receipt_photo(msg, state):
    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id")
    pending = (state.get("pending_mm") or {}).get(str(user_id))
    if not pending:
        send_message(
            chat_id,
            "Got your photo — but tap a pack first, then choose "
            "KBZPay / WavePay / AYAPay (or Thai QR), and send the "
            "receipt after that so I know what it's for.",
        )
        return
    key = pending["pack"]
    state["pending_mm"].pop(str(user_id), None)
    save_state(state)
    forward_receipt_to_admins(user_id, msg.get("from", {}), key, msg["message_id"])
    send_message(
        chat_id,
        "Receipt sent to the admin — your sessions will be added "
        "as soon as it's confirmed. 🙏",
    )


# ------------------------------------------------------------- start ------


def handle_start(chat_id, text, state, user=None):
    parts = text.split()
    arg = parts[1] if len(parts) > 1 else ""

    if arg == "mysessions":
        total = get_credits(chat_id)
        send_message(
            chat_id,
            f"💬 You have {total} session{'s' if total != 1 else ''} left.\n\n"
            "Buy more below:",
            reply_markup=pack_keyboard(url_buttons=False),
        )
        return

    if arg.startswith("pack_"):
        key = arg[len("pack_"):]
        if key in PACKS:
            send_pack_options(chat_id, key)
            return

    if arg.startswith("session_"):
        sid = arg[len("session_"):]
        session = state.get("sessions", {}).get(sid)
        if session:
            send_message(
                chat_id,
                session_text(session),
                reply_markup=pack_keyboard(url_buttons=False),
            )
            return
        send_message(chat_id, "That session is gone — check the group for the latest one.")
        return

    if is_admin(chat_id):
        send_message(
            chat_id,
            "DaddyTeacher admin.\n\n"
            "/newsession <topic> | <date/time> — create + post a session\n"
            "/newsession — interactive prompt\n"
            "/post <text> — announcement + pack buttons\n"
            "/setgroup <@group> — where sessions go\n"
            "/sessions — list posted sessions\n"
            "/users — buyers, credits, packs bought\n"
            "/sales — recent purchases\n"
            "/id — this chat's id\n"
            "/help — full help",
        )
        return

    send_message(
        chat_id,
        "Welcome to DaddyTeacher! 🏳️‍🌈\n\n"
        "English class for gay learners — 1-hour sessions, "
        "each one topic + 10 new phrases.\n\n"
        "Packs:\n"
        "• 1 session — 15,000 Ks ($3)\n"
        "• 2 sessions — 20,000 Ks ($4)\n"
        "• 4 sessions — 30,000 Ks ($6)\n\n"
        "Tap a pack to pay — Stars, USDT, or KBZPay / WavePay / AYAPay.",
        reply_markup=pack_keyboard(url_buttons=False),
    )


def handle_help(chat_id):
    send_message(
        chat_id,
        "DaddyTeacher — how it works:\n\n"
        "Students buy session packs (1 / 2 / 4 sessions) and pay by "
        "Stars, USDT (BSC), KBZPay / WavePay / AYAPay, or Thai QR.\n"
        "Receipts go to the admins for approval.\n\n"
        "Admin:\n"
        "/newsession <topic> | <date/time> — post a session card\n"
        "/post <text> — announcement with pack buttons\n"
        "/setgroup <@group> — set the teaching group\n"
        "/sessions — list sessions\n"
        "/users — buyers and credits\n"
        "/sales — recent purchases\n"
        "/id — this chat's id\n\n"
        "Students:\n"
        "/mysessions — sessions left\n"
        f"{FOOTER}",
    )


# ------------------------------------------------------------ messages ----


def post_to_group(state, text, reply_markup=None):
    group = state.get("group") or GROUP_CHAT_ID
    if not group:
        return None, "no group set"
    r = send_message(group, text, reply_markup=reply_markup)
    if not r.get("ok"):
        return None, r.get("description", "unknown error")
    return r["result"]["message_id"], None


def create_session(state, topic, when):
    state["seq"] = state.get("seq", 0) + 1
    sid = f"s{state['seq']}"
    session = {"id": sid, "topic": topic, "when": when, "ts": int(time.time())}
    state.setdefault("sessions", {})[sid] = session
    return session


def handle_message(msg, state):
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"].get("type", "private")
    text = (msg.get("text") or "").strip()
    user_id = msg.get("from", {}).get("id")

    # /id works everywhere — this is how the group chat id is found
    # after the bot is added to the group.
    if text == "/id":
        send_message(
            chat_id,
            f"This chat's id is: <code>{chat_id}</code>",
            parse_mode="HTML",
        )
        return

    if chat_type != "private":
        return

    note_user(msg.get("from", {}))

    if text.startswith("/start"):
        handle_start(chat_id, text, state, user=msg.get("from", {}))
        return

    sp = msg.get("successful_payment")
    if sp:
        handle_successful_payment(chat_id, user_id, sp, user=msg.get("from", {}))
        return

    if msg.get("photo") and not is_admin(chat_id):
        handle_receipt_photo(msg, state)
        return

    if not is_admin(chat_id):
        if looks_like_tx_hash(text):
            handle_usdt_hash(chat_id, user_id, text, state, user=msg.get("from", {}))
            return
        if text == "/mysessions":
            total = get_credits(user_id)
            send_message(
                chat_id,
                f"💬 You have {total} session{'s' if total != 1 else ''} left.\n\n"
                "Buy more below:",
                reply_markup=pack_keyboard(url_buttons=False),
            )
            return
        if text.startswith("/"):
            send_message(
                chat_id,
                "Sessions live in the group — tap a pack button there "
                "and pay here in this private chat.\n"
                "Use /mysessions to see your sessions left.",
            )
        return

    # ---- admin ----
    fwd = msg.get("forward_from_chat")
    if fwd and fwd.get("type") in ("group", "supergroup", "channel"):
        state["group"] = str(fwd["id"])
        save_state(state)
        send_message(
            chat_id,
            f"Group set to {fwd.get('title', fwd['id'])} ({fwd['id']}). "
            "Sessions will post there now.",
        )
        return

    link_id = parse_group_link(text)
    if link_id:
        state["group"] = link_id
        save_state(state)
        send_message(
            chat_id,
            f"Group set to {link_id}. Sessions will post there now.",
        )
        return

    if text == "/help":
        handle_help(chat_id)
        return

    if text == "/cancel":
        state["draft_session"] = False
        save_state(state)
        send_message(chat_id, "Cancelled.")
        return

    if text == "/newsession":
        state["draft_session"] = True
        save_state(state)
        send_message(
            chat_id,
            "New session. Send me the topic and date/time like this:\n\n"
            "Ordering food | Sat 21 Nov, 8pm\n\n"
            "(topic, then |, then the date and time)",
        )
        return

    if text.startswith("/newsession "):
        rest = text[len("/newsession "):].strip()
        if "|" in rest:
            topic, when = [p.strip() for p in rest.split("|", 1)]
        else:
            topic, when = rest, "To be announced"
        if not topic:
            send_message(chat_id, "Give me a topic: /newsession <topic> | <date/time>")
            return
        session = create_session(state, topic, when)
        save_state(state)
        mid, err = post_to_group(
            state, session_text(session), reply_markup=pack_keyboard(url_buttons=True)
        )
        if err:
            send_message(
                chat_id,
                "Session saved but posting failed — "
                f"is the group set (/setgroup) and the bot an admin there? "
                f"Telegram said: {err}",
            )
            return
        session["message_id"] = mid
        save_state(state)
        send_message(chat_id, f"Posted session {session['id']} ({topic}) to the group.")
        return

    if text.startswith("/post"):
        group = state.get("group") or GROUP_CHAT_ID
        if not group:
            send_message(chat_id, "No group set yet — /setgroup <@group> first.")
            return
        body = text[len("/post"):].strip()
        if not body:
            send_message(chat_id, "Usage: /post <your announcement text>")
            return
        mid, err = post_to_group(
            state, body, reply_markup=pack_keyboard(url_buttons=True)
        )
        if err:
            send_message(
                chat_id,
                "Posting failed — is the bot an admin in the group? "
                f"Telegram said: {err}",
            )
            return
        send_message(chat_id, "Posted to the group.")
        return

    if text.startswith("/setgroup"):
        parts = text.split()
        if len(parts) < 2:
            cur = state.get("group") or GROUP_CHAT_ID or "(not set)"
            send_message(
                chat_id,
                f"Current group: {cur}\nUsage: /setgroup <@group>",
            )
            return
        target = parts[1]
        link_id = parse_group_link(target)
        if link_id:
            state["group"] = link_id
            save_state(state)
            send_message(
                chat_id, f"Group set to {link_id}. Sessions will post there now."
            )
            return
        if target.startswith("https://t.me/+") or "joinchat" in target:
            send_message(
                chat_id,
                "That's an invite link — Telegram won't let me post to it.\n"
                "Instead, forward any message from the group to me, or "
                "long-press a message there → Copy Link and paste it here, "
                "and I'll pick up the group's real ID. Then post again.",
            )
            return
        state["group"] = target
        save_state(state)
        send_message(
            chat_id,
            f"Group set to {target}.\n"
            "Make sure the bot is an admin in that group, or posting will fail.",
        )
        return

    if text == "/sessions":
        sessions = state.get("sessions", {})
        if not sessions:
            send_message(chat_id, "No sessions yet. /newsession to make one.")
            return
        lines = ["Your sessions:"]
        for sid, s in sessions.items():
            lines.append(f"{sid} — {s['topic']} ({s['when']})")
        send_message(chat_id, "\n".join(lines))
        return

    if text == "/users":
        users = load_json_file(USERS_PATH, {})
        credits = load_json_file(CREDITS_PATH, {})
        purchases = load_json_file(PURCHASES_PATH, [])
        packs_bought = {}
        for p in purchases:
            if p.get("status") == "paid":
                packs_bought[p["user"]] = packs_bought.get(p["user"], 0) + 1
        rows = []
        for uid, u in users.items():
            if uid in ADMIN_IDS:
                continue
            name = f"@{u['username']}" if u.get("username") else uid
            rows.append(
                (
                    u.get("last_seen", 0),
                    f"{name} — {credits.get(uid, 0)} sessions left, "
                    f"{packs_bought.get(uid, 0)} pack(s) bought",
                )
            )
        if not rows:
            send_message(chat_id, "No users yet — nobody has opened the bot.")
            return
        rows.sort(key=lambda r: r[0], reverse=True)  # most recent first
        lines = [f"Buyers ({len(rows)}):"] + [r[1] for r in rows[:50]]
        if len(rows) > 50:
            lines.append(f"…(+{len(rows) - 50} more)")
        send_message(chat_id, "\n".join(lines))
        return

    if text == "/sales":
        purchases = load_json_file(PURCHASES_PATH, [])
        if not purchases:
            send_message(chat_id, "No sales yet.")
            return
        lines = ["Recent sales:"]
        for p in purchases[-20:][::-1]:
            name = f"@{p['username']}" if p.get("username") else p["user"]
            lines.append(
                f"{fmt_time(p['ts'])} — {name} — "
                f"{pack_label(p['pack'])} — {p['method']} — {p['status']}"
            )
        send_message(chat_id, "\n".join(lines))
        return

    # plain text while an interactive /newsession draft is open
    if state.get("draft_session") and text and not text.startswith("/"):
        if "|" in text:
            topic, when = [p.strip() for p in text.split("|", 1)]
        else:
            topic, when = text, "To be announced"
        state["draft_session"] = False
        session = create_session(state, topic, when)
        save_state(state)
        mid, err = post_to_group(
            state, session_text(session), reply_markup=pack_keyboard(url_buttons=True)
        )
        if err:
            send_message(
                chat_id,
                "Session saved but posting failed — "
                f"is the group set (/setgroup) and the bot an admin there? "
                f"Telegram said: {err}",
            )
            return
        session["message_id"] = mid
        save_state(state)
        send_message(chat_id, f"Posted session {session['id']} ({topic}) to the group.")
        return

    if text.startswith("/"):
        send_message(chat_id, "Unknown command. /help for the list.")
    else:
        send_message(chat_id, "Nothing to do with that — /newsession to post a session, /help for the list.")


# ------------------------------------------------------------ callbacks ----


def handle_callback(query, state):
    data = query.get("data", "")
    user_id = query["from"]["id"]
    qid = query["id"]
    username = query.get("from", {}).get("username", "")

    note_user(query.get("from", {}))

    # ---- admin receipt decisions ----
    if data.startswith("mmok:") or data.startswith("mmno:"):
        if not is_admin(user_id):
            answer_callback(qid, "Admin only.", show_alert=True)
            return
        rid = data.split(":", 1)[1]
        receipt = (state.get("receipts") or {}).get(rid)
        if not receipt:
            answer_callback(qid, "Unknown receipt.", show_alert=True)
            return
        if receipt.get("status") != "pending":
            answer_callback(qid, "Already handled.", show_alert=True)
            return
        cust_id = int(receipt["user"])
        key = receipt["pack"]
        if data.startswith("mmok:"):
            receipt["status"] = "approved"
            save_state(state)
            # credit_pack adds the sessions AND records the purchase.
            total = credit_pack(cust_id, receipt.get("username", ""), key, "Myanmar pay")
            send_message(
                cust_id,
                f"✅ Payment confirmed — {PACKS[key]['sessions']} session"
                f"{'s' if PACKS[key]['sessions'] > 1 else ''} added.\n"
                f"You now have {total} session{'s' if total != 1 else ''}. "
                "See you in class! 🎉",
            )
            answer_callback(qid, "Approved — sessions added.")
        else:
            receipt["status"] = "declined"
            save_state(state)
            record_purchase(
                cust_id, receipt.get("username", ""), key, "Myanmar pay", "declined"
            )
            send_message(
                cust_id,
                "❌ Your receipt was declined. If you think this is a "
                "mistake, message @SirArkar.",
            )
            answer_callback(qid, "Declined.")
        return

    if data == "mysessions":
        total = get_credits(user_id)
        send_message(
            user_id,
            f"💬 You have {total} session{'s' if total != 1 else ''} left.\n\n"
            "Buy more below:",
            reply_markup=pack_keyboard(url_buttons=False),
        )
        answer_callback(qid, "Sessions sent to your private chat.")
        return

    parts = data.split(":")
    if len(parts) != 2:
        answer_callback(qid, "Unknown button.")
        return
    action, key = parts
    if key not in PACKS:
        answer_callback(qid, "Unknown button.")
        return
    p = PACKS[key]

    if action == "pack":
        send_pack_options(user_id, key)
        answer_callback(qid, "Choose how to pay.")
        return

    if action == "pay_stars":
        r = api(
            "sendInvoice",
            {
                "chat_id": user_id,
                "title": f"DaddyTeacher: {pack_label(key)}",
                "description": f"{p['sessions']} English class session"
                f"{'s' if p['sessions'] > 1 else ''} — 1 hour each, "
                "one topic + 10 new phrases.",
                "payload": f"pack:{key}:{user_id}",
                "provider_token": "",
                "currency": "XTR",
                "prices": [
                    {"label": pack_label(key), "amount": p["stars"]}
                ],
            },
        )
        if r.get("ok"):
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
            "kind": "pack",
            "pack": key,
            "usdt": p["usdt"],
        }
        save_state(state)
        send_message(
            user_id,
            f"Pay {p['usdt']} USDT on BSC (BEP20) to:\n\n"
            f"<code>{USDT_ADDRESS}</code>\n\n"
            f"🔗 <a href=\"{USDT_BSCSCAN_URL}\">View on BscScan</a>\n"
            "⚠️ Send on BSC (BEP20) only — other networks may lose "
            "your payment.\n\n"
            "Then paste your transaction hash here "
            "(starts with 0x, 66 characters). "
            "I will check it on-chain and add your sessions.",
            parse_mode="HTML",
            reply_markup=usdt_copy_keyboard(),
        )
        answer_callback(qid, "USDT address sent — check your private chat.")
        return

    if action == "pay_mm":
        state.setdefault("pending_mm", {})[str(user_id)] = {"pack": key}
        save_state(state)
        send_message(user_id, mm_payment_text(key))
        answer_callback(qid, "Payment details sent — check your private chat.")
        return

    if action == "pay_thai":
        state.setdefault("pending_mm", {})[str(user_id)] = {"pack": key}
        save_state(state)
        send_message(
            user_id,
            f"🇹🇭 For Thai QR / PromptPay, message @SirArkar for "
            f"{p['ks']:,} Ks ({pack_label(key)}), then send your receipt "
            "screenshot HERE and the admin will confirm it.",
        )
        answer_callback(qid, "Thai payment details sent — check your private chat.")
        return

    answer_callback(qid, "Unknown button.")


# ---------------------------------------------------------------- main ----


def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN not set", flush=True)
        return
    print("DaddyTeacher started. Polling for updates...", flush=True)
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
        state = load_state()
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
            save_state(state)


if __name__ == "__main__":
    main()
