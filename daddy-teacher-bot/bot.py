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
  /board                              post the live sellers board
  /setgroup <@group>                  where sessions go (or forward a
                                      group post / paste a t.me/c link)
  /sessions                           list posted sessions
  /users                              buyers, credits, packs bought
  /sales                              recent purchases (method + status)
  /id                                 the current chat's id

Students:
  /start                              welcome + the three packs
  /mysessions                         remaining session credits
  /profile                            make/edit your seller profile
  /myprofile                          your profile + its status
  /sellers                            live sellers + their products
  /balance                            your bot balance
  /topup                              top up by Stars or USDT
  tap a pack button on a group post — it deep-links into the bot DM,
  where the payment choice happens (invoices go to private chat only)

State lives in JSON files under DATA_DIR (same pattern as daddy-bot):
  state.json      group id, sessions, pending payments, receipts, seq,
                  profile drafts
  credits.json    user id -> session credits remaining
  purchases.json  purchase records — kind "pack" (session packs),
                  "market" (peer-to-peer product sales) and "topup"
  used_tx.json    USDT transaction hashes already spent
  users.json      everyone who interacted (username + first/last seen)
  profiles.json   seller profiles (products, prices, payment details,
                  status pending/live/declined)
  balances.json   user id -> bot balance in Ks (Stars/USDT top-ups;
                  balance payments debit the buyer, credit the seller)

v2 — seller profiles + peer-to-peer market:
  Members make a seller profile with /profile (products: milk,
  eggplant, peaches, donut, HD; price 5,000–50,000 Ks each; their own
  KBZPay / WavePay / AYAPay / USDT / bank details). A profile is
  PENDING until an admin approves it — the admin approves only after
  seeing the seller join the Zoom live (the bot cannot see Zoom
  attendance). /board posts the live sellers to the group.
  Buyers pay with their bot balance, Stars, USDT (to the bot, the
  seller gets the balance), or directly to the seller (receipt photo
  or USDT hash, confirmed by the seller or an admin). Top up with
  /topup (Stars $1/$2/$5/$10/$20 or USDT).

v3 — cash-out + sell USDT (rate 1 USDT = 4,500 Ks):
  /cashout — a member cashes out bot balance as USDT at 1 USDT =
  4,500 Ks (minimum 4,500 Ks, whole USDT only, leftovers stay in
  the balance). An admin approves only after sending the USDT from
  their own wallet; approving debits the balance.
  /sellusdt — a member sells USDT they already hold to Arkar at the
  same 4,500 rate: they send the USDT to Arkar's address, the bot
  verifies it on-chain, then an admin confirms the MMK is paid to
  the seller's profile payment details.
  THE 4,500 RATE IS FOR CASH-OUT / SELL-USDT ONLY. Product prices,
  packs, Stars and top-ups still use the 1 USD = 5,000 Ks anchor.

No watermarking, no protect_content — these are plain text posts.
"""

import html
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
PROFILES_PATH = os.path.join(DATA_DIR, "profiles.json")
BALANCES_PATH = os.path.join(DATA_DIR, "balances.json")
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

# ---------------------------------------------------------- marketplace ----

KS_PER_USD = 5000
STARS_PER_USD = 100
PRICE_MIN_KS = 5000
PRICE_MAX_KS = 50000
TOPUP_USD_AMOUNTS = (1, 2, 5, 10, 20)

# Cash-out / sell-USDT rate ONLY: 1 USDT = 4,500 Ks. This is NOT the
# pricing anchor (KS_PER_USD = 5,000) — never use one for the other.
KS_PER_USDT_CASHOUT = 4500
CASHOUT_MIN_KS = 4500  # minimum cash-out: 1 USDT

PRODUCTS = {
    "milk": "🥛 Milk",
    "eggplant": "🍆 Eggplant",
    "peaches": "🍑 Peaches",
    "donut": "🍩 Donut",
    "hd": "🎬 HD",
}

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
            "profile_draft": {},
            "cashouts": {},
            "cashout_seq": 0,
            "cashout_draft": {},
            "sellusdt": {},
            "sell_seq": 0,
            "sell_draft": {},
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
            "kind": "pack",
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


# ---------------------------------------------------------- marketplace ----


def load_profiles():
    return load_json_file(PROFILES_PATH, {})


def save_profiles(data):
    save_json_file(PROFILES_PATH, data)


def get_profile(user_id):
    return load_profiles().get(str(user_id))


def get_balance(user_id):
    return int(load_json_file(BALANCES_PATH, {}).get(str(user_id), 0))


def change_balance(user_id, delta_ks):
    """Add delta_ks (may be negative) to a member's bot balance.
    Returns the new balance, or None if a debit would go below zero
    (nothing is changed then). Balances are kept in integer Ks."""
    data = load_json_file(BALANCES_PATH, {})
    total = int(data.get(str(user_id), 0)) + delta_ks
    if total < 0:
        return None
    data[str(user_id)] = total
    save_json_file(BALANCES_PATH, data)
    return total


def fmt_ks(ks):
    return f"{int(ks):,} Ks"


def fmt_usd_from_ks(ks):
    return f"${int(ks) / KS_PER_USD:g}"


def parse_price_ks(text):
    """A seller-typed price. Returns the Ks int, or None if it is not a
    whole number inside 5,000–50,000 Ks."""
    cleaned = (text or "").replace(",", "").replace(" ", "").strip()
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    if value < PRICE_MIN_KS or value > PRICE_MAX_KS:
        return None
    return value


def looks_like_usdt_address(text):
    t = (text or "").strip()
    return (
        len(t) == 42
        and t.startswith("0x")
        and all(c in "0123456789abcdefABCDEF" for c in t[2:])
    )


def looks_like_mm_number(text):
    t = (text or "").replace(" ", "").replace("-", "").strip()
    if t.startswith("+"):
        t = t[1:]
    return t.isdigit() and 9 <= len(t) <= 15


def record_event(entry):
    data = load_json_file(PURCHASES_PATH, [])
    data.append(entry)
    save_json_file(PURCHASES_PATH, data)


def record_market_sale(buyer_id, buyer_username, seller_id, seller_name,
                       product, ks, method, status, tx_hash=None):
    record_event(
        {
            "kind": "market",
            "buyer": str(buyer_id),
            "buyer_username": buyer_username or "",
            "seller": str(seller_id),
            "seller_name": seller_name or "",
            "product": product,
            "ks": ks,
            "method": method,
            "status": status,
            "tx": tx_hash or "",
            "ts": int(time.time()),
        }
    )


def record_topup(user_id, username, usd, ks, method, tx_hash=None):
    record_event(
        {
            "kind": "topup",
            "user": str(user_id),
            "username": username or "",
            "usd": usd,
            "ks": ks,
            "method": method,
            "status": "paid",
            "tx": tx_hash or "",
            "ts": int(time.time()),
        }
    )


def seller_pay_methods(profile):
    pay = profile.get("pay", {})
    methods = []
    if pay.get("kbz"):
        methods.append("KBZPay")
    if pay.get("wave"):
        methods.append("WavePay")
    if pay.get("aya"):
        methods.append("AYAPay")
    if pay.get("usdt"):
        methods.append("USDT")
    if pay.get("bank_name") or pay.get("bank_acct"):
        methods.append("Bank transfer")
    return methods


def profile_summary_text(profile):
    lines = [f"👤 {profile.get('name', 'Seller')}"]
    if profile.get("username"):
        lines.append(
            f"@{profile['username']} | ID {profile.get('user_id', '?')}"
        )
    lines.append("Products:")
    for key, price in (profile.get("products") or {}).items():
        lines.append(f"• {PRODUCTS.get(key, key)} — {fmt_ks(price)}")
    methods = seller_pay_methods(profile)
    lines.append("Payment: " + (", ".join(methods) if methods else "none"))
    return "\n".join(lines)


def seller_card_text(profile):
    lines = [f"🛍 {html.escape(str(profile.get('name', 'Seller')))}"]
    if profile.get("username"):
        lines.append(f"@{profile['username']}")
    lines.append("")
    lines.append("Products:")
    for key, price in (profile.get("products") or {}).items():
        lines.append(f"• {PRODUCTS.get(key, key)} — {fmt_ks(price)}")
    lines.append("")
    methods = seller_pay_methods(profile)
    if methods:
        lines.append("Accepts: " + " · ".join(methods))
    pay = profile.get("pay", {})
    details = []
    if pay.get("kbz"):
        details.append(f"KBZPay: <code>{html.escape(pay['kbz'])}</code>")
    if pay.get("wave"):
        details.append(f"WavePay: <code>{html.escape(pay['wave'])}</code>")
    if pay.get("aya"):
        details.append(f"AYAPay: <code>{html.escape(pay['aya'])}</code>")
    if pay.get("usdt"):
        details.append(f"USDT (BEP20): <code>{html.escape(pay['usdt'])}</code>")
    if pay.get("bank_name") or pay.get("bank_acct"):
        details.append(
            f"Bank: {html.escape(str(pay.get('bank_name', '')))} — "
            f"<code>{html.escape(str(pay.get('bank_acct', '')))}</code>"
        )
    if details:
        lines.append("")
        lines.append("Pay the seller directly:")
        lines.extend(details)
    lines.append("")
    lines.append("Tap a product below to buy it.")
    return "\n".join(lines)


def seller_card_keyboard(profile):
    rows = []
    uid = profile.get("user_id", "")
    for key in (profile.get("products") or {}):
        price = profile["products"][key]
        rows.append(
            [
                {
                    "text": f"Buy {PRODUCTS.get(key, key)} — {fmt_ks(price)}",
                    "callback_data": f"buy:{uid}:{key}",
                }
            ]
        )
    if (profile.get("pay", {}) or {}).get("usdt"):
        rows.append(
            [
                {
                    "text": "📋 Copy seller's USDT address",
                    "copy_text": {"text": profile["pay"]["usdt"]},
                }
            ]
        )
    return {"inline_keyboard": rows}


def sellers_board_text(live_profiles):
    lines = ["🛍 DaddyTeacher Market — live sellers\n"]
    lines.append(
        "Every seller below joined the Zoom live and has an approved "
        "profile. Tap a seller to see their products and pay them."
    )
    for profile in live_profiles:
        lines.append("")
        lines.append(f"👤 {profile.get('name', 'Seller')}")
        for key, price in (profile.get("products") or {}).items():
            lines.append(f"   • {PRODUCTS.get(key, key)} — {fmt_ks(price)}")
    lines.append("")
    lines.append(
        "Buy in the bot — balance, Stars, USDT, or pay the seller directly."
    )
    return "\n".join(lines)


def sellers_board_keyboard(live_profiles):
    rows = []
    for profile in live_profiles:
        rows.append(
            [
                {
                    "text": f"🛍 {profile.get('name', 'Seller')}",
                    "url": f"https://t.me/{bot_username()}?start=seller_{profile['user_id']}",
                }
            ]
        )
    rows.append(
        [
            {
                "text": "💰 My balance / top up",
                "url": f"https://t.me/{bot_username()}?start=balance",
            }
        ]
    )
    return {"inline_keyboard": rows}


def send_sellers_list(chat_id):
    profiles = load_profiles()
    live = [p for p in profiles.values() if p.get("status") == "live"]
    if not live:
        send_message(
            chat_id,
            "No live sellers yet — profiles go live once an admin "
            "approves them after the Zoom live.\n\n"
            "Want to sell? Make your profile with /profile.",
        )
        return
    lines = ["🛍 Live sellers:\n"]
    rows = []
    for p in live:
        products = ", ".join(
            f"{PRODUCTS.get(k, k)} {fmt_ks(v)}"
            for k, v in (p.get("products") or {}).items()
        )
        lines.append(f"👤 {p.get('name', 'Seller')} — {products}")
        rows.append(
            [
                {
                    "text": f"🛍 {p.get('name', 'Seller')}",
                    "callback_data": f"seller:{p['user_id']}",
                }
            ]
        )
    send_message(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": rows})


def show_balance(user_id):
    total = get_balance(user_id)
    send_message(
        user_id,
        f"💰 Your balance: {fmt_ks(total)} ({fmt_usd_from_ks(total)}).\n\n"
        "Spend it on any live seller's products, or top it up below.",
        reply_markup={
            "inline_keyboard": [
                [{"text": "💰 Top up", "callback_data": "topup"}],
                [{"text": "🛍 Browse sellers", "callback_data": "browse"}],
            ]
        },
    )


def send_topup_options(user_id):
    rows = [
        [{"text": f"⭐ Stars — ${usd}", "callback_data": f"topup_stars:{usd}"}]
        for usd in TOPUP_USD_AMOUNTS
    ]
    rows += [
        [{"text": f"💎 USDT — ${usd}", "callback_data": f"topup_usdt:{usd}"}]
        for usd in TOPUP_USD_AMOUNTS
    ]
    send_message(
        user_id,
        "Top up your balance — pick an amount and a method.\n\n"
        "Stars: a native invoice from the bot.\n"
        "USDT: send it on BSC, paste the hash, I'll verify on-chain.",
        reply_markup={"inline_keyboard": rows},
    )


def send_buy_options(user_id, profile, product, price):
    seller_name = profile.get("name", "Seller")
    balance = get_balance(user_id)
    stars = max(1, round(price / 50))
    usd = price / KS_PER_USD
    rows = []
    if balance >= price:
        rows.append(
            [
                {
                    "text": f"💰 Pay from balance ({fmt_ks(balance)})",
                    "callback_data": f"buypay:balance:{profile['user_id']}:{product}",
                }
            ]
        )
    else:
        rows.append([{"text": "💰 Top up balance", "callback_data": "topup"}])
    rows.append(
        [
            {
                "text": f"⭐ Pay {stars} Stars now",
                "callback_data": f"buypay:stars:{profile['user_id']}:{product}",
            }
        ]
    )
    rows.append(
        [
            {
                "text": f"💎 Pay {usd:g} USDT now",
                "callback_data": f"buypay:usdt:{profile['user_id']}:{product}",
            }
        ]
    )
    rows.append(
        [
            {
                "text": "🇲🇲 Pay seller directly",
                "callback_data": f"buypay:direct:{profile['user_id']}:{product}",
            }
        ]
    )
    text = (
        f"🛍 {PRODUCTS.get(product, product)} from {seller_name} — "
        f"{fmt_ks(price)} (${usd:g})\n\n"
        "How do you want to pay?\n"
        f"💰 Balance: you have {fmt_ks(balance)}.\n"
        f"⭐ Stars: {stars} Stars go to the bot, the seller gets the balance.\n"
        f"💎 USDT: {usd:g} USDT to the bot, the seller gets the balance.\n"
        "🇲🇲 Direct: pay the seller's own KBZPay / WavePay / AYAPay / "
        "bank / USDT and send a receipt."
    )
    send_message(user_id, text, reply_markup={"inline_keyboard": rows})


# ------------------------------------------------- cash-out + sell USDT ----


def cashout_usdt_for_ks(ks):
    """Whole USDT a Ks amount cashes out to at the 4,500 rate, rounded
    down. Any leftover Ks stays in the balance. (The 5,000 pricing
    anchor is NOT used here.)"""
    return int(ks) // KS_PER_USDT_CASHOUT


def record_cashout(user_id, username, ks, usdt, address, status):
    record_event(
        {
            "kind": "cashout",
            "user": str(user_id),
            "username": username or "",
            "ks": ks,
            "usdt": usdt,
            "address": address or "",
            "status": status,
            "ts": int(time.time()),
        }
    )


def record_sell_usdt(user_id, username, usdt, mmk, tx_hash, status):
    record_event(
        {
            "kind": "sellusdt",
            "user": str(user_id),
            "username": username or "",
            "usdt": usdt,
            "mmk": mmk,
            "tx": tx_hash or "",
            "status": status,
            "ts": int(time.time()),
        }
    )


def start_cashout(chat_id, user_id, state):
    balance = get_balance(user_id)
    if balance < CASHOUT_MIN_KS:
        send_message(
            chat_id,
            f"💸 Cash out your balance as USDT — 1 USDT = "
            f"{CASHOUT_MIN_KS:,} Ks.\n\n"
            f"Your balance is {fmt_ks(balance)} — you need at least "
            f"{fmt_ks(CASHOUT_MIN_KS)} (1 USDT) to cash out.\n\n"
            "Top up with /topup, or earn balance by selling in the market.",
        )
        return
    usdt = cashout_usdt_for_ks(balance)
    state.setdefault("cashout_draft", {})[str(user_id)] = {"step": "amount"}
    save_state(state)
    send_message(
        chat_id,
        f"💸 Cash out — your balance is {fmt_ks(balance)} "
        f"(up to {usdt} USDT at 1 USDT = {CASHOUT_MIN_KS:,} Ks).\n\n"
        "How many Ks do you want to cash out? Send the amount in Ks "
        f"(minimum {CASHOUT_MIN_KS:,} — whole USDT only, so 4,500 Ks = "
        "1 USDT, 9,000 = 2, and so on). Anything left over stays in "
        "your balance.\n\n"
        "Or /cancel.",
    )


def handle_cashout_step(chat_id, user_id, text, state, user=None):
    """One step of the guided /cashout flow. Returns True if the
    message was consumed by the flow."""
    draft = (state.get("cashout_draft") or {}).get(str(user_id))
    if not draft:
        return False
    step = draft.get("step")

    if step == "amount":
        cleaned = (text or "").replace(",", "").replace(" ", "").strip()
        if not cleaned.isdigit():
            send_message(
                chat_id,
                "Send the amount in Ks as a number (e.g. 45000), or /cancel.",
            )
            return True
        amount = int(cleaned)
        balance = get_balance(user_id)
        if amount < CASHOUT_MIN_KS:
            send_message(
                chat_id,
                f"Minimum cash-out is {fmt_ks(CASHOUT_MIN_KS)} (1 USDT) — "
                "send a bigger amount, or /cancel.",
            )
            return True
        if amount > balance:
            send_message(
                chat_id,
                f"That's more than your balance ({fmt_ks(balance)}) — "
                "send a smaller amount, or /cancel.",
            )
            return True
        usdt = cashout_usdt_for_ks(amount)
        ks_used = usdt * KS_PER_USDT_CASHOUT
        leftover = amount - ks_used
        draft.update(
            {
                "step": "address",
                "amount_ks": amount,
                "usdt": usdt,
                "ks_used": ks_used,
            }
        )
        save_state(state)
        profile = get_profile(user_id)
        profile_usdt = (profile or {}).get("pay", {}).get("usdt", "")
        note = (
            f"Cashing out {fmt_ks(amount)} → {usdt} USDT "
            f"({fmt_ks(ks_used)} at 1 USDT = {CASHOUT_MIN_KS:,} Ks)."
        )
        if leftover:
            note += (
                f"\n{fmt_ks(leftover)} stays in your balance "
                "(only whole USDT amounts pay out)."
            )
        if profile_usdt:
            note += (
                "\n\nWhere should I send the USDT?\nYour profile address "
                f"is <code>{html.escape(profile_usdt)}</code> — send /keep "
                "to use it, or send a new address."
            )
        else:
            note += (
                "\n\nWhere should I send the USDT? Send your USDT address "
                "(BSC, starts with 0x, 42 characters)."
            )
        send_message(chat_id, note, parse_mode="HTML")
        return True

    if step == "address":
        profile = get_profile(user_id)
        profile_usdt = (profile or {}).get("pay", {}).get("usdt", "")
        if text == "/keep":
            if not profile_usdt:
                send_message(
                    chat_id,
                    "No address on your profile — send your USDT address "
                    "(starts with 0x, 42 characters).",
                )
                return True
            address = profile_usdt
        elif looks_like_usdt_address(text):
            address = text.strip()
        else:
            send_message(
                chat_id,
                "That doesn't look like a USDT address — it starts with "
                "0x and is 42 characters. Send it again, or /cancel.",
            )
            return True
        usdt = draft["usdt"]
        ks_used = draft["ks_used"]
        state["cashout_seq"] = state.get("cashout_seq", 0) + 1
        cid = f"co{state['cashout_seq']}"
        state.setdefault("cashouts", {})[cid] = {
            "id": cid,
            "user": str(user_id),
            "username": (user or {}).get("username", ""),
            "ks": ks_used,
            "usdt": usdt,
            "address": address,
            "status": "pending",
            "ts": int(time.time()),
        }
        state.get("cashout_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(
            chat_id,
            f"✅ Cash-out request sent — {usdt} USDT to "
            f"<code>{html.escape(address)}</code>.\n"
            "An admin will send the USDT and confirm it here. I'll tell "
            "you when it's paid.",
            parse_mode="HTML",
        )
        for admin_id in sorted(ADMIN_IDS):
            send_message(
                admin_id,
                f"💸 Cash-out request {cid} from {user_tag(user)}:\n\n"
                f"• {fmt_ks(ks_used)} → {usdt} USDT\n"
                f"• Send to: <code>{html.escape(address)}</code>\n"
                f"• Balance now: {fmt_ks(get_balance(user_id))}\n\n"
                "Approve ONLY after you have sent the USDT from your "
                "wallet — approving debits the seller's balance.",
                parse_mode="HTML",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Paid — USDT sent",
                                "callback_data": f"cook:{cid}",
                            },
                            {
                                "text": "❌ Decline",
                                "callback_data": f"cono:{cid}",
                            },
                        ]
                    ]
                },
            )
        return True
    return False


def start_sell_usdt(chat_id, user_id, state):
    state.setdefault("sell_draft", {})[str(user_id)] = {"step": "amount"}
    save_state(state)
    send_message(
        chat_id,
        "💎 Sell your USDT to Arkar — 1 USDT = "
        f"{KS_PER_USDT_CASHOUT:,} Ks.\n\n"
        "How much USDT do you want to sell? Send a whole number "
        "(e.g. 5 for 5 USDT = 22,500 Ks).\n\n"
        "Or /cancel.",
    )


def handle_sell_step(chat_id, user_id, text, state, user=None):
    """One step of the guided /sellusdt flow. Returns True if the
    message was consumed by the flow."""
    draft = (state.get("sell_draft") or {}).get(str(user_id))
    if not draft:
        return False
    step = draft.get("step")

    if step == "amount":
        cleaned = (text or "").replace(",", "").replace(" ", "").strip()
        if not cleaned.isdigit() or int(cleaned) < 1:
            send_message(
                chat_id,
                "Send the USDT amount as a whole number (1 or more), "
                "or /cancel.",
            )
            return True
        usdt = int(cleaned)
        mmk = usdt * KS_PER_USDT_CASHOUT
        state["sell_seq"] = state.get("sell_seq", 0) + 1
        sid = f"su{state['sell_seq']}"
        state.setdefault("sellusdt", {})[sid] = {
            "id": sid,
            "user": str(user_id),
            "username": (user or {}).get("username", ""),
            "usdt": usdt,
            "mmk": mmk,
            "tx": "",
            "status": "awaiting_payment",
            "ts": int(time.time()),
        }
        state.setdefault("pending_usdt", {})[str(user_id)] = {
            "kind": "sellusdt",
            "sell_id": sid,
            "usdt": usdt,
        }
        draft.update({"step": "hash", "sell_id": sid, "usdt": usdt, "mmk": mmk})
        save_state(state)
        send_message(
            chat_id,
            f"Send {usdt} USDT on BSC (BEP20) to Arkar:\n\n"
            f"<code>{USDT_ADDRESS}</code>\n\n"
            f"🔗 <a href=\"{USDT_BSCSCAN_URL}\">View on BscScan</a>\n"
            "⚠️ Send on BSC (BEP20) only.\n\n"
            f"You'll get {fmt_ks(mmk)} for it ({usdt} USDT × "
            f"{KS_PER_USDT_CASHOUT:,} Ks).\n\n"
            "Then paste your transaction hash here (starts with 0x, "
            "66 characters).",
            parse_mode="HTML",
            reply_markup=usdt_copy_keyboard(),
        )
        return True

    if step == "hash":
        if looks_like_tx_hash(text):
            handle_usdt_hash(chat_id, user_id, text, state, user=user)
            return True
        send_message(
            chat_id,
            "Send the transaction hash (starts with 0x, 66 characters), "
            "or /cancel.",
        )
        return True
    return False


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


def verify_usdt_tx(tx_hash, min_units, to_address=None):
    """Check a BSC transaction for a USDT transfer to to_address (Arkar's
    bot address by default) of at least min_units. Returns (True, '',
    value_units) or (False, reason, value). Uses public BSC nodes, no key."""
    target = (to_address or USDT_ADDRESS).lower()
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
            if to_addr.lower() != target:
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
        return False, "No USDT transfer to that address in that transaction.", 0
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


# ------------------------------------------------------ seller profiles ----


def profile_draft_keyboard(draft):
    selected = set(draft.get("selected", []))
    rows = []
    for key, label in PRODUCTS.items():
        mark = "✅ " if key in selected else "⬜ "
        rows.append(
            [{"text": mark + label, "callback_data": f"prodtoggle:{key}"}]
        )
    rows.append(
        [{"text": "✅ Done — continue", "callback_data": "proddone"}]
    )
    return {"inline_keyboard": rows}


def start_profile(chat_id, user, state):
    existing = get_profile(chat_id)
    data = {}
    if existing:
        data = {
            "name": existing.get("name", ""),
            "products": dict(existing.get("products", {})),
            "pay": dict(existing.get("pay", {})),
        }
    state.setdefault("profile_draft", {})[str(chat_id)] = {
        "step": "name",
        "data": data,
        "editing": bool(existing),
    }
    save_state(state)
    if existing:
        send_message(
            chat_id,
            f"Let's update your seller profile (currently "
            f"{existing.get('status', '?')}).\n\n"
            "What's your display name? Send a new one, or /skip to keep "
            f"\"{existing.get('name', '')}\".",
        )
    else:
        send_message(
            chat_id,
            "Let's set up your seller profile — this is how other "
            "members find you and pay you on the show.\n\n"
            "What's your display name?",
        )


def send_profile_confirm(chat_id, data, username=""):
    text = "Check your profile:\n\n" + profile_summary_text(
        {
            "name": data.get("name", ""),
            "username": username,
            "products": data.get("products", {}),
            "pay": data.get("pay", {}),
        }
    )
    text += (
        "\n\nSubmit it for approval? An admin approves it once "
        "they've seen you join the Zoom live."
    )
    send_message(
        chat_id,
        text,
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Submit for approval",
                        "callback_data": "profconfirm",
                    },
                    {
                        "text": "✏️ Start over",
                        "callback_data": "profedit",
                    },
                    {
                        "text": "❌ Cancel",
                        "callback_data": "profcancel",
                    },
                ]
            ]
        },
    )


def handle_profile_step(chat_id, text, state, user=None):
    """One step of the guided /profile flow. Returns True if the message
    was consumed by the flow."""
    draft = (state.get("profile_draft") or {}).get(str(chat_id))
    if not draft:
        return False
    step = draft.get("step")
    data = draft.setdefault("data", {})
    username = (user or {}).get("username", "")

    if text == "/cancel":
        state.get("profile_draft", {}).pop(str(chat_id), None)
        save_state(state)
        send_message(chat_id, "Profile setup cancelled — nothing was saved.")
        return True

    if step == "name":
        if text == "/skip":
            if not draft.get("editing") or not data.get("name"):
                send_message(chat_id, "Please send a display name first.")
                return True
        elif len(text) < 2 or len(text) > 50:
            send_message(
                chat_id,
                "That name doesn't look right — send a display name "
                "(2–50 characters).",
            )
            return True
        else:
            data["name"] = text
        draft["step"] = "products"
        save_state(state)
        send_message(
            chat_id,
            "What do you sell? Tap each product you offer, then Done.",
            reply_markup=profile_draft_keyboard(draft),
        )
        return True

    if step == "products":
        send_message(
            chat_id,
            "Tap the products above to pick them, then press Done.",
            reply_markup=profile_draft_keyboard(draft),
        )
        return True

    if step == "price":
        current = draft.get("price_for")
        price = parse_price_ks(text)
        if price is None:
            send_message(
                chat_id,
                f"Price must be a whole number from "
                f"{PRICE_MIN_KS:,} to {PRICE_MAX_KS:,} Ks — try again for "
                f"{PRODUCTS.get(current, current)}.",
            )
            return True
        data.setdefault("products", {})[current] = price
        queue = draft.get("price_queue", [])
        if queue:
            nxt = queue.pop(0)
            draft["price_for"] = nxt
            draft["price_queue"] = queue
            save_state(state)
            send_message(
                chat_id,
                f"Price for {PRODUCTS.get(nxt, nxt)} in Ks "
                f"({PRICE_MIN_KS:,}–{PRICE_MAX_KS:,}):",
            )
        else:
            draft["step"] = "pay_kbz"
            save_state(state)
            send_message(
                chat_id,
                "Payment details — buyers pay YOU directly, so these "
                "are your own accounts.\n\n"
                "KBZPay number? Send it, or /skip if you don't use KBZPay.",
            )
        return True

    pay_steps = [
        ("pay_kbz", "kbz", "KBZPay number",
         "WavePay number? Send it, or /skip."),
        ("pay_wave", "wave", "WavePay number",
         "AYAPay number? Send it, or /skip."),
        ("pay_aya", "aya", "AYAPay number",
         "USDT address (BSC, starts with 0x)? Send it, or /skip."),
        ("pay_usdt", "usdt", "USDT address",
         "Bank name? Send it, or /skip if you don't take bank transfer."),
        ("pay_bank_name", "bank_name", "bank name",
         "Bank account number? Send it, or /skip."),
        ("pay_bank_acct", "bank_acct", "bank account number", None),
    ]
    for idx, (step_name, field, label, next_prompt) in enumerate(pay_steps):
        if step != step_name:
            continue
        if text == "/skip":
            # Keep the existing value when editing; record empty for a
            # brand-new profile.
            data.setdefault("pay", {}).setdefault(field, "")
        elif field in ("kbz", "wave", "aya"):
            if not looks_like_mm_number(text):
                send_message(
                    chat_id,
                    f"That doesn't look like a {label} — send just the "
                    "number, or /skip.",
                )
                return True
            data.setdefault("pay", {})[field] = (
                text.replace(" ", "").replace("-", "")
            )
        elif field == "usdt":
            if not looks_like_usdt_address(text):
                send_message(
                    chat_id,
                    "That doesn't look like a USDT address — it starts "
                    "with 0x and is 42 characters. Try again, or /skip.",
                )
                return True
            data.setdefault("pay", {})[field] = text.strip()
        else:
            data.setdefault("pay", {})[field] = text
        if idx + 1 < len(pay_steps):
            draft["step"] = pay_steps[idx + 1][0]
            save_state(state)
            send_message(chat_id, next_prompt)
        else:
            pay = data.get("pay", {})
            if not any(
                pay.get(k)
                for k in ("kbz", "wave", "aya", "usdt", "bank_acct")
            ):
                draft["step"] = "pay_kbz"
                save_state(state)
                send_message(
                    chat_id,
                    "You need at least one payment method so buyers can "
                    "pay you. Let's go through them again.\n\n"
                    "KBZPay number? Send it, or /skip.",
                )
            else:
                draft["step"] = "confirm"
                save_state(state)
                send_profile_confirm(chat_id, data, username)
        return True

    if step == "confirm":
        send_message(
            chat_id,
            "Tap Submit below to send your profile for approval, "
            "or /cancel to drop it.",
        )
        return True
    return False


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
    if not parts or parts[0] not in ("pack", "topup", "mkt"):
        return
    username = (user or {}).get("username", "")

    if parts[0] == "topup":
        if len(parts) != 3 or parts[2] != str(user_id):
            return
        try:
            usd = int(parts[1])
        except ValueError:
            return
        ks = usd * KS_PER_USD
        change_balance(user_id, ks)
        record_topup(user_id, username, usd, ks, "Stars")
        total = get_balance(user_id)
        send_message(
            user_id,
            f"✅ Balance topped up +{fmt_ks(ks)}.\n"
            f"Your balance is now {fmt_ks(total)} "
            f"({fmt_usd_from_ks(total)}).",
        )
        return

    if parts[0] == "mkt":
        if len(parts) != 5 or parts[4] != str(user_id):
            return
        seller_id, product, price_s = parts[1], parts[2], parts[3]
        try:
            price = int(price_s)
        except ValueError:
            return
        profile = get_profile(seller_id)
        if not profile or profile.get("status") != "live":
            send_message(
                user_id,
                "That seller is not live any more — the Stars were "
                "charged, so please message @SirArkar and we'll sort it out.",
            )
            return
        seller_name = profile.get("name", "Seller")
        change_balance(seller_id, price)
        record_market_sale(
            user_id, username, seller_id, seller_name, product, price,
            "Stars", "paid",
        )
        seller_total = get_balance(seller_id)
        send_message(
            user_id,
            f"✅ Paid {fmt_ks(price)} with Stars for "
            f"{PRODUCTS.get(product, product)} from {seller_name}.",
        )
        send_message(
            seller_id,
            f"💰 {user_tag(user)} bought your "
            f"{PRODUCTS.get(product, product)} for {fmt_ks(price)} (Stars).\n"
            "Credited to your bot balance — now "
            f"{fmt_ks(seller_total)}. You can spend it on other sellers' "
            "products in the bot.",
        )
        return

    # pack:<key>:<user_id>
    if len(parts) != 3 or parts[2] != str(user_id):
        return
    key = parts[1]
    if key not in PACKS:
        return
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
            "tap a pack or a product first, then choose USDT.",
        )
        return
    if tx_used(tx_hash):
        send_message(chat_id, "That transaction was already used.")
        return
    kind = pending.get("kind", "pack")
    username = (user or {}).get("username", "")

    if kind == "topup":
        usd = int(pending.get("usd", 0))
        ok, reason, value = verify_usdt_tx(tx_hash, usd * USDT_MIN)
        if not ok:
            send_message(chat_id, f"Not verified yet: {reason}")
            return
        mark_tx_used(tx_hash)
        state["pending_usdt"].pop(str(user_id), None)
        save_state(state)
        # Credit what actually arrived (1 USDT = 5,000 Ks).
        ks = int(value * KS_PER_USD / 1_000_000)
        if ks <= 0:
            ks = usd * KS_PER_USD
        change_balance(user_id, ks)
        record_topup(user_id, username, usd, ks, "USDT", tx_hash)
        total = get_balance(user_id)
        send_message(
            user_id,
            f"✅ USDT received — balance topped up +{fmt_ks(ks)}.\n"
            f"Your balance is now {fmt_ks(total)} "
            f"({fmt_usd_from_ks(total)}).",
        )
        return

    if kind in ("market", "market_direct"):
        seller_id = pending.get("seller")
        product = pending.get("product")
        price = int(pending.get("price_ks", 0))
        profile = get_profile(seller_id)
        if not profile or profile.get("status") != "live":
            state["pending_usdt"].pop(str(user_id), None)
            save_state(state)
            send_message(
                chat_id,
                "That seller is not live any more — no payment was made. "
                "Pick another seller.",
            )
            return
        seller_name = profile.get("name", "Seller")
        if kind == "market_direct":
            seller_usdt = (profile.get("pay", {}) or {}).get("usdt", "")
            if not seller_usdt:
                send_message(chat_id, "That seller has no USDT address.")
                return
            to_addr = seller_usdt
            method = "USDT direct"
        else:
            to_addr = None  # the bot's address — seller gets bot balance
            method = "USDT"
        min_units = price * 200  # 1 Ks = 200 USDT units (6 decimals)
        ok, reason, _value = verify_usdt_tx(tx_hash, min_units, to_address=to_addr)
        if not ok:
            send_message(chat_id, f"Not verified yet: {reason}")
            return
        mark_tx_used(tx_hash)
        state["pending_usdt"].pop(str(user_id), None)
        save_state(state)
        if kind == "market":
            change_balance(seller_id, price)
            send_message(
                seller_id,
                f"💰 {user_tag(user)} bought your "
                f"{PRODUCTS.get(product, product)} for {fmt_ks(price)} (USDT).\n"
                "Credited to your bot balance — now "
                f"{fmt_ks(get_balance(seller_id))}.",
            )
        else:
            send_message(
                seller_id,
                f"💰 {user_tag(user)} paid you {fmt_ks(price)} in USDT for "
                f"{PRODUCTS.get(product, product)} (direct, verified on-chain).",
            )
        record_market_sale(
            user_id, username, seller_id, seller_name, product, price,
            method, "paid", tx_hash,
        )
        send_message(
            user_id,
            f"✅ USDT confirmed on-chain — you bought "
            f"{PRODUCTS.get(product, product)} for {fmt_ks(price)} from "
            f"{seller_name}.",
        )
        return

    if kind == "sellusdt":
        sell_id = pending.get("sell_id")
        usdt = int(pending.get("usdt", 0))
        ok, reason, _value = verify_usdt_tx(tx_hash, usdt * USDT_MIN)
        if not ok:
            send_message(chat_id, f"Not verified yet: {reason}")
            return
        mark_tx_used(tx_hash)
        state["pending_usdt"].pop(str(user_id), None)
        state.get("sell_draft", {}).pop(str(user_id), None)
        sell = (state.get("sellusdt") or {}).get(sell_id)
        if sell:
            sell["tx"] = tx_hash
            sell["status"] = "awaiting_mmk"
            sell["verified_ts"] = int(time.time())
        save_state(state)
        mmk = usdt * KS_PER_USDT_CASHOUT
        profile = get_profile(user_id)
        pay = (profile or {}).get("pay", {})
        pay_lines = []
        if pay.get("kbz"):
            pay_lines.append(f"KBZPay: <code>{html.escape(pay['kbz'])}</code>")
        if pay.get("wave"):
            pay_lines.append(f"WavePay: <code>{html.escape(pay['wave'])}</code>")
        if pay.get("aya"):
            pay_lines.append(f"AYAPay: <code>{html.escape(pay['aya'])}</code>")
        if pay.get("bank_name") or pay.get("bank_acct"):
            pay_lines.append(
                f"Bank: {html.escape(str(pay.get('bank_name', '')))} — "
                f"<code>{html.escape(str(pay.get('bank_acct', '')))}</code>"
            )
        note = (
            f"💎 {user_tag(user)} sold {usdt} USDT to Arkar (verified "
            f"on-chain, hash <code>{tx_hash[:10]}…</code>).\n\n"
            f"Pay them {fmt_ks(mmk)} ({usdt} USDT × "
            f"{KS_PER_USDT_CASHOUT:,} Ks) via their profile details:"
        )
        if pay_lines:
            note += "\n" + "\n".join(pay_lines)
        else:
            note += (
                "\nNo payment details on their profile — ask them how "
                "to pay the MMK."
            )
        for admin_id in sorted(ADMIN_IDS):
            send_message(
                admin_id,
                note,
                parse_mode="HTML",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": f"✅ Paid {fmt_ks(mmk)} MMK",
                                "callback_data": f"supaid:{sell_id}",
                            }
                        ]
                    ]
                },
            )
        send_message(
            chat_id,
            f"✅ USDT received and verified — {usdt} USDT.\n"
            f"Arkar will send you {fmt_ks(mmk)}. I'll tell you when "
            "it's paid.",
        )
        return

    # kind == "pack": original class-pack flow
    key = pending["pack"]
    p = PACKS[key]
    ok, reason, _value = verify_usdt_tx(tx_hash, p["usdt"] * USDT_MIN)
    if not ok:
        send_message(chat_id, f"Not verified yet: {reason}")
        return
    mark_tx_used(tx_hash)
    state["pending_usdt"].pop(str(user_id), None)
    save_state(state)
    total = credit_pack(user_id, username, key, "USDT", tx_hash)
    send_message(
        user_id,
        f"✅ USDT received — {p['sessions']} session"
        f"{'s' if p['sessions'] > 1 else ''} added.\n"
        f"You now have {total} session{'s' if total != 1 else ''}. "
        "See you in class! 🎉",
    )


def forward_receipt_to_admins(user_id, user, key, message_id, state, market=None):
    """Forward the receipt photo with Approve / Decline buttons. For a
    class pack it goes to every admin; for a marketplace sale it also
    goes to the seller, and the seller or an admin may confirm it.
    One receipt id per photo, so only the first decision counts — a
    second tap later gets 'already handled'.

    Takes the caller's `state` and saves it — it must NOT load its own
    fresh copy, or the main loop's end-of-batch save would overwrite
    the new receipt record with the stale in-memory state."""
    state["receipt_seq"] = state.get("receipt_seq", 0) + 1
    rid = f"r{state['receipt_seq']}"
    entry = {
        "user": str(user_id),
        "username": (user or {}).get("username", ""),
        "status": "pending",
        "ts": int(time.time()),
    }
    if market:
        entry.update(
            {
                "kind": "market",
                "seller": str(market["seller"]),
                "product": market["product"],
                "price_ks": market["price_ks"],
                "method": market.get("method", "Myanmar pay"),
            }
        )
        note = (
            f"📸 Receipt from {user_tag(user)} — buying your "
            f"{PRODUCTS.get(market['product'], market['product'])} for "
            f"{fmt_ks(market['price_ks'])} via "
            f"{market.get('method', 'Myanmar pay')}.\n"
            "Tap to confirm the payment, or decline."
        )
        button = "✅ Confirm payment"
        targets = [str(market["seller"])] + [
            a for a in sorted(ADMIN_IDS) if a != str(market["seller"])
        ]
    else:
        entry.update({"kind": "pack", "pack": key})
        note = (
            f"📸 Receipt from {user_tag(user)} — "
            f"{pack_label(key)} ({PACKS[key]['ks']:,} Ks).\n"
            "Tap to add the sessions, or decline."
        )
        button = "✅ Approve — add sessions"
        targets = sorted(ADMIN_IDS)
    state.setdefault("receipts", {})[rid] = entry
    save_state(state)
    for target_id in targets:
        api(
            "forwardMessage",
            {
                "chat_id": target_id,
                "from_chat_id": user_id,
                "message_id": message_id,
            },
        )
        send_message(
            target_id,
            note,
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": button,
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
            "Got your photo — but tap a pack or a product first, then "
            "choose how to pay, and send the receipt after that so I "
            "know what it's for.",
        )
        return
    state["pending_mm"].pop(str(user_id), None)
    save_state(state)
    if pending.get("kind") == "market":
        forward_receipt_to_admins(
            user_id, msg.get("from", {}), None, msg["message_id"], state,
            market=pending,
        )
    else:
        forward_receipt_to_admins(
            user_id, msg.get("from", {}), pending["pack"], msg["message_id"],
            state,
        )
    send_message(
        chat_id,
        "Receipt sent — it will be confirmed as soon as the seller or "
        "an admin checks it. 🙏",
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

    if arg.startswith("seller_"):
        target = arg[len("seller_"):]
        profile = get_profile(target)
        if not profile or profile.get("status") != "live":
            send_message(chat_id, "That seller is not live right now.")
            return
        send_message(
            chat_id,
            seller_card_text(profile),
            parse_mode="HTML",
            reply_markup=seller_card_keyboard(profile),
        )
        return

    if arg == "balance":
        show_balance(chat_id)
        return

    if arg == "topup":
        send_topup_options(chat_id)
        return

    if is_admin(chat_id):
        send_message(
            chat_id,
            "DaddyTeacher admin.\n\n"
            "/newsession <topic> | <date/time> — create + post a session\n"
            "/newsession — interactive prompt\n"
            "/post <text> — announcement + pack buttons\n"
            "/board — post the live sellers board\n"
            "/setgroup <@group> — where sessions go\n"
            "/sessions — list posted sessions\n"
            "/users — buyers, credits, packs bought\n"
            "/sales — recent purchases\n"
            "/sellers — live sellers\n"
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
        "Tap a pack to pay — Stars, USDT, or KBZPay / WavePay / AYAPay.\n\n"
        "🛍 Plus the market — members sell products (milk, eggplant, "
        "peaches, donut, HD). Make your seller profile with /profile, "
        "browse with /sellers, check your balance with /balance.\n\n"
        "💸 Cash out your balance as USDT with /cashout, or sell your "
        "USDT to Arkar with /sellusdt — both at 1 USDT = 4,500 Ks.",
        reply_markup=pack_keyboard(url_buttons=False),
    )


def handle_help(chat_id):
    send_message(
        chat_id,
        "DaddyTeacher — how it works:\n\n"
        "Students buy session packs (1 / 2 / 4 sessions) and pay by "
        "Stars, USDT (BSC), KBZPay / WavePay / AYAPay, or Thai QR.\n"
        "Receipts go to the admins for approval.\n\n"
        "Market — members sell products (milk, eggplant, peaches, "
        "donut, HD, 5,000–50,000 Ks each). Make a profile with "
        "/profile; an admin approves it once they've seen you join "
        "the Zoom live. Buyers pay from their bot balance, with "
        "Stars, with USDT, or directly to the seller (receipt photo "
        "or USDT hash). Top up with /topup.\n\n"
        "Admin:\n"
        "/newsession <topic> | <date/time> — post a session card\n"
        "/post <text> — announcement with pack buttons\n"
        "/board — post the live sellers board\n"
        "/setgroup <@group> — set the teaching group\n"
        "/sessions — list sessions\n"
        "/users — buyers and credits\n"
        "/sales — recent purchases\n"
        "/id — this chat's id\n\n"
        "Everyone:\n"
        "/mysessions — sessions left\n"
        "/profile — make/edit your seller profile\n"
        "/myprofile — your profile + its status\n"
        "/sellers — live sellers\n"
        "/balance — your bot balance\n"
        "/topup — top up by Stars or USDT\n"
        "/cashout — cash out your balance as USDT (1 USDT = 4,500 Ks)\n"
        "/sellusdt — sell your USDT to Arkar (1 USDT = 4,500 Ks)\n"
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

    # ---- shared commands: everyone, admins included ----
    if text == "/cancel":
        state.get("profile_draft", {}).pop(str(user_id), None)
        state.get("cashout_draft", {}).pop(str(user_id), None)
        state.get("sell_draft", {}).pop(str(user_id), None)
        pending = (state.get("pending_usdt") or {}).get(str(user_id))
        if pending and pending.get("kind") == "sellusdt":
            state["pending_usdt"].pop(str(user_id), None)
        state["draft_session"] = False
        save_state(state)
        send_message(chat_id, "Cancelled.")
        return

    if text == "/profile":
        start_profile(chat_id, msg.get("from", {}), state)
        return

    if text == "/myprofile":
        profile = get_profile(user_id)
        if not profile:
            send_message(
                chat_id,
                "You don't have a seller profile yet — make one with /profile.",
            )
            return
        status = {
            "pending": "⏳ Pending approval",
            "live": "✅ Live",
            "declined": "❌ Declined",
        }.get(profile.get("status"), profile.get("status", "?"))
        send_message(
            chat_id,
            f"Your profile — {status}:\n\n" + profile_summary_text(profile),
        )
        return

    if text == "/sellers":
        send_sellers_list(chat_id)
        return

    if text == "/balance":
        show_balance(user_id)
        return

    if text == "/topup":
        send_topup_options(user_id)
        return

    if text == "/cashout":
        start_cashout(chat_id, user_id, state)
        return

    if text == "/sellusdt":
        start_sell_usdt(chat_id, user_id, state)
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

    co_draft = (state.get("cashout_draft") or {}).get(str(user_id))
    if co_draft and (not text.startswith("/") or text == "/keep"):
        handle_cashout_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    su_draft = (state.get("sell_draft") or {}).get(str(user_id))
    if su_draft and not text.startswith("/"):
        handle_sell_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    draft = (state.get("profile_draft") or {}).get(str(user_id))
    if draft and (not text.startswith("/") or text == "/skip"):
        handle_profile_step(chat_id, text, state, user=msg.get("from", {}))
        return

    if not is_admin(chat_id):
        if looks_like_tx_hash(text):
            handle_usdt_hash(chat_id, user_id, text, state, user=msg.get("from", {}))
            return
        if text.startswith("/"):
            send_message(
                chat_id,
                "Sessions and sellers live in the group — tap a pack or "
                "a seller there and pay here in this private chat.\n"
                "/mysessions for sessions left, /balance for your "
                "balance, /sellers to browse.",
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

    if text == "/board":
        group = state.get("group") or GROUP_CHAT_ID
        if not group:
            send_message(chat_id, "No group set yet — /setgroup <@group> first.")
            return
        live = [
            p for p in load_profiles().values() if p.get("status") == "live"
        ]
        if not live:
            send_message(
                chat_id, "No live sellers yet — approve a profile first."
            )
            return
        mid, err = post_to_group(
            state,
            sellers_board_text(live),
            reply_markup=sellers_board_keyboard(live),
        )
        if err:
            send_message(
                chat_id,
                "Posting failed — is the bot an admin in the group? "
                f"Telegram said: {err}",
            )
            return
        send_message(
            chat_id,
            f"Posted the sellers board ({len(live)} live sellers) to the group.",
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
        sellers = [
            p for p in load_profiles().values() if p.get("status") == "live"
        ]
        if sellers:
            lines.append("")
            lines.append(f"Sellers live ({len(sellers)}):")
            for p in sellers:
                prods = ", ".join(
                    f"{PRODUCTS.get(k, k)} {fmt_ks(v)}"
                    for k, v in (p.get("products") or {}).items()
                )
                lines.append(
                    f"@{p.get('username', p['user_id'])} — "
                    f"{p.get('name', '')} — {prods}"
                )
        send_message(chat_id, "\n".join(lines))
        return

    if text == "/sales":
        purchases = load_json_file(PURCHASES_PATH, [])
        if not purchases:
            send_message(chat_id, "No sales yet.")
            return
        lines = ["Recent sales:"]
        for p in purchases[-20:][::-1]:
            kind = p.get("kind", "pack")
            if kind == "market":
                buyer = (
                    f"@{p['buyer_username']}"
                    if p.get("buyer_username")
                    else p["buyer"]
                )
                lines.append(
                    f"{fmt_time(p['ts'])} — {buyer} → "
                    f"{p.get('seller_name', p['seller'])} — "
                    f"{PRODUCTS.get(p['product'], p['product'])} — "
                    f"{fmt_ks(p['ks'])} — {p['method']} — {p['status']}"
                )
            elif kind == "topup":
                name = (
                    f"@{p['username']}" if p.get("username") else p["user"]
                )
                lines.append(
                    f"{fmt_time(p['ts'])} — {name} — top-up "
                    f"${p.get('usd')} ({fmt_ks(p.get('ks', 0))}) — "
                    f"{p['method']} — {p['status']}"
                )
            elif kind == "cashout":
                name = (
                    f"@{p['username']}" if p.get("username") else p["user"]
                )
                lines.append(
                    f"{fmt_time(p['ts'])} — {name} — cash-out "
                    f"{fmt_ks(p.get('ks', 0))} → {p.get('usdt')} USDT — "
                    f"{p['status']}"
                )
            elif kind == "sellusdt":
                name = (
                    f"@{p['username']}" if p.get("username") else p["user"]
                )
                lines.append(
                    f"{fmt_time(p['ts'])} — {name} — sold "
                    f"{p.get('usdt')} USDT → {fmt_ks(p.get('mmk', 0))} — "
                    f"{p['status']}"
                )
            else:
                name = (
                    f"@{p['username']}" if p.get("username") else p["user"]
                )
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

    # ---- receipt decisions (packs + marketplace) ----
    if data.startswith("mmok:") or data.startswith("mmno:"):
        rid = data.split(":", 1)[1]
        receipt = (state.get("receipts") or {}).get(rid)
        if not receipt:
            answer_callback(qid, "Unknown receipt.", show_alert=True)
            return
        if receipt.get("status") != "pending":
            answer_callback(qid, "Already handled.", show_alert=True)
            return
        # A marketplace receipt may be confirmed by the seller or an
        # admin; a pack receipt is admin-only.
        allowed = is_admin(user_id) or (
            receipt.get("kind") == "market"
            and str(user_id) == str(receipt.get("seller"))
        )
        if not allowed:
            answer_callback(
                qid, "Only the seller or an admin can confirm this.",
                show_alert=True,
            )
            return
        cust_id = int(receipt["user"])
        if receipt.get("kind") == "market":
            seller_id = receipt["seller"]
            product = receipt["product"]
            price = int(receipt["price_ks"])
            method = receipt.get("method", "Myanmar pay")
            profile = get_profile(seller_id)
            seller_name = (
                profile.get("name", "Seller") if profile else "Seller"
            )
            if data.startswith("mmok:"):
                receipt["status"] = "approved"
                save_state(state)
                record_market_sale(
                    cust_id, receipt.get("username", ""), seller_id,
                    seller_name, product, price, method, "paid",
                )
                send_message(
                    cust_id,
                    f"✅ Payment confirmed — you bought "
                    f"{PRODUCTS.get(product, product)} for {fmt_ks(price)} "
                    f"from {seller_name}.",
                )
                send_message(
                    seller_id,
                    f"💰 Payment confirmed: {user_tag(query.get('from', {}))} "
                    f"bought your {PRODUCTS.get(product, product)} for "
                    f"{fmt_ks(price)} via {method}.",
                )
                answer_callback(qid, "Confirmed.")
            else:
                receipt["status"] = "declined"
                save_state(state)
                record_market_sale(
                    cust_id, receipt.get("username", ""), seller_id,
                    seller_name, product, price, method, "declined",
                )
                send_message(
                    cust_id,
                    "❌ Your receipt was declined. If you think this is "
                    "a mistake, message @SirArkar.",
                )
                answer_callback(qid, "Declined.")
            return
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

    # ---- cash-out decisions (admin confirms after sending USDT) ----
    if data.startswith("cook:") or data.startswith("cono:"):
        if not is_admin(user_id):
            answer_callback(qid, "Admin only.", show_alert=True)
            return
        cid = data.split(":", 1)[1]
        req = (state.get("cashouts") or {}).get(cid)
        if not req:
            answer_callback(qid, "Unknown cash-out request.", show_alert=True)
            return
        if req.get("status") != "pending":
            answer_callback(qid, "Already handled.", show_alert=True)
            return
        seller_id = req["user"]
        if data.startswith("cook:"):
            ks_used = int(req["ks"])
            if get_balance(seller_id) < ks_used:
                req["status"] = "failed"
                save_state(state)
                send_message(
                    seller_id,
                    "Your cash-out request was cancelled — your balance "
                    "no longer covers it. Please try again with /cashout.",
                )
                answer_callback(
                    qid, "Balance no longer covers it — request cancelled.",
                    show_alert=True,
                )
                return
            change_balance(seller_id, -ks_used)
            req["status"] = "paid"
            req["decided_ts"] = int(time.time())
            save_state(state)
            record_cashout(
                seller_id, req.get("username", ""), ks_used,
                int(req["usdt"]), req.get("address", ""), "paid",
            )
            send_message(
                seller_id,
                f"✅ Paid: {req['usdt']} USDT sent to "
                f"<code>{html.escape(req.get('address', ''))}</code>.\n"
                f"Your balance is now {fmt_ks(get_balance(seller_id))}.",
                parse_mode="HTML",
            )
            answer_callback(qid, "Paid — seller notified, balance debited.")
        else:
            req["status"] = "declined"
            req["decided_ts"] = int(time.time())
            save_state(state)
            record_cashout(
                seller_id, req.get("username", ""), int(req["ks"]),
                int(req["usdt"]), req.get("address", ""), "declined",
            )
            send_message(
                seller_id,
                "❌ Your cash-out request was declined — your balance "
                "is untouched. If you think this is a mistake, message "
                "@SirArkar.",
            )
            answer_callback(qid, "Declined — balance untouched.")
        return

    # ---- sell-USDT: admin confirms the MMK is paid ----
    if data.startswith("supaid:"):
        if not is_admin(user_id):
            answer_callback(qid, "Admin only.", show_alert=True)
            return
        sid = data.split(":", 1)[1]
        sell = (state.get("sellusdt") or {}).get(sid)
        if not sell:
            answer_callback(qid, "Unknown sale.", show_alert=True)
            return
        if sell.get("status") != "awaiting_mmk":
            answer_callback(qid, "Already handled.", show_alert=True)
            return
        sell["status"] = "paid"
        sell["decided_ts"] = int(time.time())
        save_state(state)
        record_sell_usdt(
            sell["user"], sell.get("username", ""), int(sell["usdt"]),
            int(sell["mmk"]), sell.get("tx", ""), "paid",
        )
        send_message(
            sell["user"],
            f"✅ Paid — Arkar sent you {fmt_ks(sell['mmk'])} for "
            f"{int(sell['usdt'])} USDT. Thanks! 🙏",
        )
        answer_callback(qid, "Seller notified.")
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

    # ---- seller profile approval (admin gate = Zoom live) ----
    if data.startswith("profok:") or data.startswith("profno:"):
        if not is_admin(user_id):
            answer_callback(qid, "Admin only.", show_alert=True)
            return
        target = data.split(":", 1)[1]
        profiles = load_profiles()
        profile = profiles.get(str(target))
        if not profile:
            answer_callback(qid, "Unknown profile.", show_alert=True)
            return
        if profile.get("status") != "pending":
            answer_callback(qid, "Already handled.", show_alert=True)
            return
        if data.startswith("profok:"):
            profile["status"] = "live"
            save_profiles(profiles)
            send_message(
                target,
                "✅ Your seller profile is LIVE! Other members can now "
                "find you with /sellers and buy your products.",
            )
            answer_callback(qid, "Approved — profile is live.")
        else:
            profile["status"] = "declined"
            save_profiles(profiles)
            send_message(
                target,
                "❌ Your seller profile was declined. If you think this "
                "is a mistake, message @SirArkar.",
            )
            answer_callback(qid, "Declined.")
        return

    # ---- profile setup: product picker ----
    if data.startswith("prodtoggle:"):
        key = data.split(":", 1)[1]
        draft = (state.get("profile_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "products":
            answer_callback(qid, "No product picker open — /profile to start.")
            return
        selected = draft.setdefault("selected", [])
        if key in selected:
            selected.remove(key)
        elif key in PRODUCTS:
            selected.append(key)
        save_state(state)
        api(
            "editMessageReplyMarkup",
            {
                "chat_id": user_id,
                "message_id": query.get("message", {}).get("message_id"),
                "reply_markup": profile_draft_keyboard(draft),
            },
        )
        answer_callback(qid)
        return

    if data == "proddone":
        draft = (state.get("profile_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "products":
            answer_callback(qid, "No product picker open — /profile to start.")
            return
        selected = draft.get("selected", [])
        if not selected:
            answer_callback(qid, "Pick at least one product first.", show_alert=True)
            return
        draft["step"] = "price"
        draft["price_for"] = selected[0]
        draft["price_queue"] = selected[1:]
        save_state(state)
        send_message(
            user_id,
            f"Price for {PRODUCTS.get(selected[0], selected[0])} in Ks "
            f"({PRICE_MIN_KS:,}–{PRICE_MAX_KS:,}):",
        )
        answer_callback(qid)
        return

    # ---- profile submit / restart / cancel ----
    if data == "profconfirm":
        draft = (state.get("profile_draft") or {}).get(str(user_id))
        if not draft:
            answer_callback(qid, "No profile draft — /profile to start one.")
            return
        pdata = draft.get("data", {})
        profiles = load_profiles()
        profiles[str(user_id)] = {
            "user_id": str(user_id),
            "username": username,
            "name": pdata.get("name", ""),
            "products": pdata.get("products", {}),
            "pay": pdata.get("pay", {}),
            "status": "pending",
            "ts": int(time.time()),
        }
        save_profiles(profiles)
        state.get("profile_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(
            user_id,
            "✅ Profile submitted — an admin will approve it once "
            "they've seen you join the Zoom live. I'll tell you when "
            "it's live.",
        )
        profile = profiles[str(user_id)]
        for admin_id in sorted(ADMIN_IDS):
            send_message(
                admin_id,
                "🆕 New seller profile to approve:\n\n"
                + profile_summary_text(profile)
                + f"\n\nSeller: {user_tag(query.get('from', {}))}\n"
                "Approve only if you've seen them join the Zoom live.",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Approve — make live",
                                "callback_data": f"profok:{user_id}",
                            },
                            {
                                "text": "❌ Decline",
                                "callback_data": f"profno:{user_id}",
                            },
                        ]
                    ]
                },
            )
        answer_callback(qid, "Submitted for approval.")
        return

    if data == "profedit":
        state.get("profile_draft", {}).pop(str(user_id), None)
        save_state(state)
        start_profile(user_id, query.get("from", {}), state)
        answer_callback(qid, "Starting over.")
        return

    if data == "profcancel":
        state.get("profile_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(user_id, "Profile setup cancelled — nothing was saved.")
        answer_callback(qid, "Cancelled.")
        return

    # ---- marketplace: browse / buy ----
    if data == "browse":
        send_sellers_list(user_id)
        answer_callback(qid)
        return

    if data.startswith("seller:"):
        target = data.split(":", 1)[1]
        profile = get_profile(target)
        if not profile or profile.get("status") != "live":
            answer_callback(qid, "That seller is not live right now.", show_alert=True)
            return
        send_message(
            user_id,
            seller_card_text(profile),
            parse_mode="HTML",
            reply_markup=seller_card_keyboard(profile),
        )
        answer_callback(qid, "Seller card sent.")
        return

    if data.startswith("buy:"):
        parts = data.split(":")
        if len(parts) != 3:
            answer_callback(qid, "Unknown button.")
            return
        _, seller_id, product = parts
        profile = get_profile(seller_id)
        if not profile or profile.get("status") != "live":
            answer_callback(qid, "That seller is not live right now.", show_alert=True)
            return
        if str(user_id) == str(seller_id):
            answer_callback(qid, "That's your own product.", show_alert=True)
            return
        price = (profile.get("products") or {}).get(product)
        if price is None:
            answer_callback(qid, "That product is no longer listed.", show_alert=True)
            return
        send_buy_options(user_id, profile, product, price)
        answer_callback(qid, "Payment choices sent.")
        return

    if data.startswith("buypay:"):
        parts = data.split(":")
        if len(parts) != 4:
            answer_callback(qid, "Unknown button.")
            return
        _, method, seller_id, product = parts
        profile = get_profile(seller_id)
        if not profile or profile.get("status") != "live":
            answer_callback(qid, "That seller is not live right now.", show_alert=True)
            return
        if str(user_id) == str(seller_id):
            answer_callback(qid, "That's your own product.", show_alert=True)
            return
        price = (profile.get("products") or {}).get(product)
        if price is None:
            answer_callback(qid, "That product is no longer listed.", show_alert=True)
            return
        seller_name = profile.get("name", "Seller")
        if method == "balance":
            new_buyer = change_balance(user_id, -price)
            if new_buyer is None:
                answer_callback(
                    qid,
                    "Not enough balance — top up with /topup first.",
                    show_alert=True,
                )
                return
            new_seller = change_balance(seller_id, price)
            record_market_sale(
                user_id, username, seller_id, seller_name, product, price,
                "Balance", "paid",
            )
            send_message(
                user_id,
                f"✅ Paid {fmt_ks(price)} from your balance for "
                f"{PRODUCTS.get(product, product)} from {seller_name}.\n"
                f"Your balance is now {fmt_ks(new_buyer)}.",
            )
            send_message(
                seller_id,
                f"💰 {user_tag(query.get('from', {}))} bought your "
                f"{PRODUCTS.get(product, product)} for {fmt_ks(price)} — "
                "paid from their bot balance.\n"
                f"Your balance is now {fmt_ks(new_seller)}. You can spend "
                "it on other sellers' products.",
            )
            answer_callback(qid, "Paid from balance.")
            return
        if method == "stars":
            stars = max(1, round(price / 50))
            r = api(
                "sendInvoice",
                {
                    "chat_id": user_id,
                    "title": f"DaddyTeacher Market: {PRODUCTS.get(product, product)}",
                    "description": (
                        f"{PRODUCTS.get(product, product)} from "
                        f"{seller_name} — {fmt_ks(price)}."
                    ),
                    "payload": f"mkt:{seller_id}:{product}:{price}:{user_id}",
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [
                        {
                            "label": f"{PRODUCTS.get(product, product)} — {fmt_ks(price)}",
                            "amount": stars,
                        }
                    ],
                },
            )
            if r.get("ok"):
                answer_callback(qid, "Invoice sent — check your private chat.")
            else:
                answer_callback(
                    qid,
                    "Stars payment is not available right now — try another option.",
                    show_alert=True,
                )
            return
        if method == "usdt":
            usd = price / KS_PER_USD
            state.setdefault("pending_usdt", {})[str(user_id)] = {
                "kind": "market",
                "seller": str(seller_id),
                "product": product,
                "price_ks": price,
            }
            save_state(state)
            send_message(
                user_id,
                f"Pay {usd:g} USDT on BSC (BEP20) to the bot:\n\n"
                f"<code>{USDT_ADDRESS}</code>\n\n"
                f"🔗 <a href=\"{USDT_BSCSCAN_URL}\">View on BscScan</a>\n"
                "⚠️ Send on BSC (BEP20) only.\n\n"
                "Then paste your transaction hash here (starts with 0x, "
                "66 characters). The seller gets the amount in their bot "
                "balance once it's verified.",
                parse_mode="HTML",
                reply_markup=usdt_copy_keyboard(),
            )
            answer_callback(qid, "USDT address sent — check your private chat.")
            return
        if method == "direct":
            pay = profile.get("pay", {})
            rows = []
            if pay.get("kbz"):
                rows.append(
                    [
                        {
                            "text": "🇲🇲 KBZPay",
                            "callback_data": f"dirpay:kbz:{seller_id}:{product}",
                        }
                    ]
                )
            if pay.get("wave"):
                rows.append(
                    [
                        {
                            "text": "🇲🇲 WavePay",
                            "callback_data": f"dirpay:wave:{seller_id}:{product}",
                        }
                    ]
                )
            if pay.get("aya"):
                rows.append(
                    [
                        {
                            "text": "🇲🇲 AYAPay",
                            "callback_data": f"dirpay:aya:{seller_id}:{product}",
                        }
                    ]
                )
            if pay.get("bank_acct"):
                rows.append(
                    [
                        {
                            "text": "🏦 Bank transfer",
                            "callback_data": f"dirpay:bank:{seller_id}:{product}",
                        }
                    ]
                )
            if pay.get("usdt"):
                rows.append(
                    [
                        {
                            "text": "💎 USDT (direct to seller)",
                            "callback_data": f"dirpay:usdt:{seller_id}:{product}",
                        }
                    ]
                )
            if not rows:
                answer_callback(
                    qid,
                    "This seller has no direct payment method listed.",
                    show_alert=True,
                )
                return
            send_message(
                user_id,
                f"Pay {seller_name} directly for "
                f"{PRODUCTS.get(product, product)} ({fmt_ks(price)}).\n"
                "Choose how:",
                reply_markup={"inline_keyboard": rows},
            )
            answer_callback(qid, "Choose how to pay the seller.")
            return
        answer_callback(qid, "Unknown button.")
        return

    if data.startswith("dirpay:"):
        parts = data.split(":")
        if len(parts) != 4:
            answer_callback(qid, "Unknown button.")
            return
        _, method, seller_id, product = parts
        profile = get_profile(seller_id)
        if not profile or profile.get("status") != "live":
            answer_callback(qid, "That seller is not live right now.", show_alert=True)
            return
        price = (profile.get("products") or {}).get(product)
        if price is None:
            answer_callback(qid, "That product is no longer listed.", show_alert=True)
            return
        pay = profile.get("pay", {})
        seller_name = profile.get("name", "Seller")
        if method == "usdt":
            addr = pay.get("usdt", "")
            if not addr:
                answer_callback(qid, "No USDT address for this seller.", show_alert=True)
                return
            usd = price / KS_PER_USD
            state.setdefault("pending_usdt", {})[str(user_id)] = {
                "kind": "market_direct",
                "seller": str(seller_id),
                "product": product,
                "price_ks": price,
            }
            save_state(state)
            send_message(
                user_id,
                f"Pay {usd:g} USDT on BSC (BEP20) straight to {seller_name}:\n\n"
                f"<code>{addr}</code>\n\n"
                "⚠️ Send on BSC (BEP20) only.\n\n"
                "Then paste your transaction hash here — I'll verify it "
                "on-chain and mark the sale paid.",
                parse_mode="HTML",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "📋 Copy seller's USDT address",
                                "copy_text": {"text": addr},
                            }
                        ]
                    ]
                },
            )
            answer_callback(qid, "Seller's USDT address sent.")
            return
        labels = {
            "kbz": ("KBZPay", pay.get("kbz", "")),
            "wave": ("WavePay", pay.get("wave", "")),
            "aya": ("AYAPay", pay.get("aya", "")),
            "bank": (pay.get("bank_name", "Bank"), pay.get("bank_acct", "")),
        }
        label, number = labels.get(method, ("", ""))
        if not number:
            answer_callback(qid, "No details for that method.", show_alert=True)
            return
        state.setdefault("pending_mm", {})[str(user_id)] = {
            "kind": "market",
            "seller": str(seller_id),
            "product": product,
            "price_ks": price,
            "method": label,
        }
        save_state(state)
        send_message(
            user_id,
            f"Pay {fmt_ks(price)} for {PRODUCTS.get(product, product)} to "
            f"{seller_name} via {label}:\n\n"
            f"<code>{number}</code>\n\n"
            "Then send your receipt screenshot HERE — I'll forward it to "
            f"{seller_name} and the admins to confirm.",
            parse_mode="HTML",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": f"📋 Copy {label}",
                            "copy_text": {"text": number},
                        }
                    ]
                ]
            },
        )
        answer_callback(qid, "Payment details sent.")
        return

    # ---- balance top-ups ----
    if data == "topup":
        send_topup_options(user_id)
        answer_callback(qid, "Top-up choices sent.")
        return

    if data == "balance":
        show_balance(user_id)
        answer_callback(qid)
        return

    if data.startswith("topup_stars:") or data.startswith("topup_usdt:"):
        method, usd_s = data.split(":", 1)
        try:
            usd = int(usd_s)
        except ValueError:
            answer_callback(qid, "Unknown amount.")
            return
        if usd not in TOPUP_USD_AMOUNTS:
            answer_callback(qid, "Unknown amount.")
            return
        if method == "topup_stars":
            r = api(
                "sendInvoice",
                {
                    "chat_id": user_id,
                    "title": f"DaddyTeacher: top up ${usd}",
                    "description": (
                        f"Add {fmt_ks(usd * KS_PER_USD)} to your "
                        "DaddyTeacher balance."
                    ),
                    "payload": f"topup:{usd}:{user_id}",
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [
                        {"label": f"Top up ${usd}", "amount": usd * STARS_PER_USD}
                    ],
                },
            )
            if r.get("ok"):
                answer_callback(qid, "Invoice sent — check your private chat.")
            else:
                answer_callback(
                    qid, "Stars payment is not available right now.", show_alert=True
                )
            return
        state.setdefault("pending_usdt", {})[str(user_id)] = {
            "kind": "topup",
            "usd": usd,
        }
        save_state(state)
        send_message(
            user_id,
            f"Top up ${usd} ({fmt_ks(usd * KS_PER_USD)}) with USDT on BSC "
            f"(BEP20):\n\n<code>{USDT_ADDRESS}</code>\n\n"
            f"🔗 <a href=\"{USDT_BSCSCAN_URL}\">View on BscScan</a>\n"
            f"⚠️ Send on BSC (BEP20) only — send at least {usd} USDT.\n\n"
            "Then paste your transaction hash here.",
            parse_mode="HTML",
            reply_markup=usdt_copy_keyboard(),
        )
        answer_callback(qid, "USDT address sent.")
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
