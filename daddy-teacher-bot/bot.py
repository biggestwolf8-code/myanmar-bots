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
                  status live/pending/declined/removed)
  balances.json   user id -> bot balance in Ks (Stars/USDT top-ups;
                  balance payments debit the buyer, credit the seller)

v2 — seller profiles + peer-to-peer market:
  Members make a seller profile with /profile (products: milk,
  eggplant, peaches, donut, HD; price 5,000–50,000 Ks each; their own
  KBZPay / WavePay / AYAPay / USDT / bank details). Profiles go LIVE
  immediately on creation — no approval gate (the Zoom-live gate was
  dropped 2026-11-16: members can start posting without the Zoom
  class). Both admins get an FYI notification for each new profile
  with a "Remove seller" button (moderation, not a gate); a removed
  seller's cards are taken down and they must make a new profile to
  sell again. /board posts the live sellers to the group.
  Buyers pay with their bot balance, Stars, USDT (to the bot, the
  seller gets the balance), or directly to the seller (receipt photo
  or USDT hash, confirmed by the seller or an admin). Top up with
  /topup (Stars $1/$2/$5/$10/$20 or USDT).

v4 — member self-service product cards (/sell):
  Any member with a live profile can post their own product to the
  group as a shopping card: /sell → pick one of their profile
  products → name up to 4 options (A, B, C, D — seller types the
  names) with a typed price each (5,000–50,000 Ks), or "Use profile
  price" for a single option at the profile price → confirm preview
  → the bot posts the card to the group. Each option is a Buy button
  ("<name> — <price> Ks") that deep-links into the bot and opens the
  v2 buy flow for that option at that price; the card also has a
  "Seller profile" button. The seller (or an admin) can remove their
  card with the "Remove" button on it.

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

v6 — auction house + seller titles:
  /auction posts a video auction instead of a fixed-price card:
  starting bid fixed at 5,000 Ks, 15 minutes only, bids from bot
  balance only (escrowed; outbid bidders are refunded at once).
  The cover is the video's own thumbnail, UNBLURRED. The highest
  bidder wins the video privately in DM — never revealed in the
  group, unless an admin wins (then it IS revealed in the group).
  Unsold auction posts stay up 24 hours, then are deleted; a sold
  auction's post is deleted at once. The deadline + 24-hour sweeps
  run inside the polling loop — no external cron.
  Seller titles by completed sales (market + auction, packs don't
  count), computed live at render time: 0 New Seller, 1–4 Seller,
  5–9 Rising Star, 10–24 Top Seller, 25–49 Star Seller, 50+ Legend.
  Shown as "<title> • <N> sold" on profiles, cards, /sellers and
  /board.

v7 — group-buy pool ("fundraiser pool"):
  /pool posts a group-buy pool instead of a fixed-price card: an
  expensive video at a seller-set price of 50,000–500,000 Ks.
  Members join from their bot balance (any amount from 1,000 Ks,
  as often as they like — each member keeps one running total,
  escrowed). When the pool fills, the seller gets the full
  set price and the video is sent PRIVATELY to every contributor's
  DM — it is NEVER revealed in the group. The pool card is deleted
  at once. No deadline — a pool stays open until it fills; if the
  seller or an admin removes it, every contributor is refunded
  what they put in. Pool videos must be 1 to 5 minutes (same rule
  as auctions); the cover is the video's own thumbnail, UNBLURRED.
  A completed pool counts as ONE sale for the seller's title.

v7.2 — flexible pool contributions:
  Each member chooses the amount: minimum 1,000 Ks, any amount
  above that. The pool
  fills when the total raised hits the set price — however many
  people that takes. The FINAL contribution is capped at exactly
  what's left, so the pool always totals exactly the set price and
  the seller always gets exactly the set price. The meter is
  money-based (Ks raised / set price); the contributor count is
  shown on its own line. Joining asks for the amount first ("How
  much do you want to put in?"), then debits min(amount,
  remaining).

v7.1 — cash out by Myanmar payment too:
  /cashout now offers two methods: USDT (unchanged — 1 USDT =
  4,500 Ks, minimum 4,500 Ks, whole USDT only) or KBZPay / WavePay
  / AYAPay in Ks, 1:1, minimum 5,000 Ks. For Myanmar the member
  picks one of their saved profile accounts (or types a different
  service + number), types the amount, and both admins get the
  request with "Paid — Ks sent" / "Decline" buttons. Approve means
  the admin has ALREADY sent the Ks; approving debits the exact
  amount (the request is marked handled + saved BEFORE the debit,
  so a second Approve answers "Already handled." and debits
  nothing — same guard as the Myanmar top-up approve).

v7.3 — admin announcement list + repeat pool contributions:
  /announce (admin DM only) shows three tappable options — Main
  intro, Fundraiser pool, Both — that post the matching
  announcement(s) to the group on tap (MAIN_ANNOUNCEMENT /
  POOL_ANNOUNCEMENT constants; Arkar's drafts, still awaiting his
  Burmese corrections). Pool members can now contribute MORE than
  once to the same pool: every top-up is at least 1,000 Ks and adds
  to their running total (one contributor entry per member). The
  pool card shows a contributor list under the meter — one line per
  member with their total, highest first, top 10 plus an "…and N
  more people (see /poolinfo <id>)" line; /poolinfo <pool id> shows
  the full list in a DM. On completion the video goes privately to
  each contributor ONCE; on cancel/remove each member is refunded
  their total.

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

# Myanmar top-up: pay the admin by KBZPay / WavePay / AYAPay, send
# the receipt, an admin approves and the balance is credited.
# Minimum 5,000 Ks.
TOPUP_MM_MIN_KS = 5000
TOPUP_MM_METHOD = "Myanmar (KBZPay/WavePay/AYAPay)"

# Cash-out / sell-USDT rate ONLY: 1 USDT = 4,500 Ks. This is NOT the
# pricing anchor (KS_PER_USD = 5,000) — never use one for the other.
KS_PER_USDT_CASHOUT = 4500
CASHOUT_MIN_KS = 4500  # minimum cash-out: 1 USDT

# Myanmar cash-out: the admin sends the Ks to the member's own
# KBZPay / WavePay / AYAPay account. 1:1 in Ks — no conversion, no
# fee, no USDT maths in this path. Minimum 5,000 Ks (same as the
# Myanmar top-up minimum).
CASHOUT_MM_MIN_KS = 5000
CASHOUT_MM_METHOD = "Myanmar (KBZPay/WavePay/AYAPay)"
MM_SERVICES = {
    "kbzpay": "KBZPay",
    "kbz": "KBZPay",
    "wavepay": "WavePay",
    "wave": "WavePay",
    "ayapay": "AYAPay",
    "aya": "AYAPay",
}

PRODUCTS = {
    "milk": "🥛 Milk",
    "eggplant": "🍆 Eggplant",
    "peaches": "🍑 Peaches",
    "donut": "🍩 Donut",
    "hd": "🎬 HD",
}

FOOTER = "Developed by Arkar Myowin"

# ------------------------------------------------------- announcements ----
# Admin announcement texts for /announce. These are Arkar's drafts —
# still awaiting his Burmese corrections — so copy them verbatim and
# do NOT edit the Burmese here; when he corrects them, update these
# two constants and the posting logic stays the same.
MAIN_ANNOUNCEMENT = """📢 DaddyTeacher Bot မိတ်ဆက် — အားလုံးဖတ်ပေးပါ 🙏

@DaddyTeacherBot ကို သုံးပြီး ဒီ group ထဲမှာ ကိုယ့်ပစ္စည်းတွေ ရောင်းလို့ရပါပြီ။

🛍 သင်ဘာတွေလုပ်နိုင်လဲ
• /profile — ကိုယ့် profile လုပ်ပါ။ နာမည်၊ အသက်၊ role (Top / Bottom / Verse)၊ ဓာတ်ပုံ ၃ ပုံ၊ ရောင်းမယ့်ပစ္စည်း၊ ဈေးနှုန်းနဲ့ ငွေလက်ခံမယ့် အကောင့်တွေ ဖြည့်ပါ။
• /sell — group ထဲမှာ ပစ္စည်းကတ်တင်ပါ။ option ၄ ခုအထိ ကိုယ့်ဈေးနဲ့ သတ်မှတ်လို့ရပါတယ်။ ဝယ်သူဝယ်ပြီးမှ အပြည့်အစုံကို group ထဲမှာ ဖော်ပြပေးပါတယ်။
• /auction — ဗီဒီယို လေလံတင်ပါ။ 5,000 ကျပ်က စပြီး 15 မိနစ်သာ။ အမြင့်ဆုံးဈေးပေးသူက ဗီဒီယိုကို သီးသန့်ရပါတယ်။
• /sellers — ရောင်းနေသူတွေကို ကြည့်ပါ။
• /balance — ကိုယ့် balance ကြည့်ပါ။ /cashout — balance ကို USDT နဲ့ ထုတ်လို့ရပါတယ်။

📸 အစစ်အမှန် ဓာတ်ပုံနဲ့ ဗီဒီယိုကိုပဲ သုံးပါ
ကိုယ့်ပစ္စည်းရဲ့ အစစ်အမှန် ဓာတ်ပုံနဲ့ ဗီဒီယိုကိုပဲ တင်ပါ။ သူများပုံ၊ အတုပုံတွေ မသုံးပါနဲ့။ အစစ်မှန်တာက ဝယ်သူတွေရဲ့ ယုံကြည်မှုကို ရစေပါတယ်။

🏆 နာမည်ကောင်း (Reputation) က ရောင်းအားနဲ့ တည်ဆောက်ပါတယ်
ရောင်းလေလေ သင့်ရဲ့ title က မြင့်လေလေပါ — New Seller → Seller → Rising Star → Top Seller → Star Seller → Legend။ Title မြင့်လေ ဝယ်သူတွေ ပိုယုံလေ၊ ပစ္စည်းတွေ ပိုမြန်မြန် ကုန်လေပါ။

💰 ဝယ်ဖို့ balance ဖြည့်ပါ — 5,000 ကျပ်က စပြီး
1. Bot ထဲမှာ /topup ကို နှိပ်ပါ။
2. "🇲🇲 KBZPay / WavePay / AYAPay" tab ကို ရွေးပါ။
3. ဖြည့်မယ့် ငွေပမာဏ (အနည်းဆုံး 5,000 ကျပ်) ရိုက်ထည့်ပါ။
4. Admin ရဲ့ KBZPay / WavePay / AYAPay ကို ငွေလွှဲပြီး receipt screenshot ကို bot ထဲမှာ ပို့ပါ။
5. Admin အတည်ပြုပြီးရင် balance ထဲကို ငွေရောက်ပါပြီ။

KBZPay: 09403720481
WavePay: 09780695959
AYAPay: 09754926216

Stars နဲ့ USDT နဲ့လည်း ဖြည့်လို့ရပါတယ်။

🛒 ဝယ်နည်း — ကတ်ပေါ်က option ကို နှိပ်ပြီး balance / Stars / USDT / seller ကို တိုက်ရိုက်ပေးပြီး ဝယ်လို့ရပါတယ်။

မေးစရာရှိရင် @HenryRealGood ကို ဆက်သွယ်ပါ။"""

POOL_ANNOUNCEMENT = """🤝 Fundraiser Pool — အတူတူစုဝယ်လို့ရပါပြီ

ဈေးကြီးတဲ့ ဗီဒီယို (50,000 ကျပ်ကနေ 500,000 ကျပ်အထိ) ကို တစ်ယောက်တည်း ဝယ်စရာမလိုတော့ပါဘူး — အတူတူစုပြီး ဝယ်လို့ရပါပြီ။

💰 ဘယ်လိုစုမလဲ
• တစ်ယောက်ကို အနည်းဆုံး 1,000 ကျပ်က စပြီး ကြိုက်သလောက် ထည့်လို့ရပါတယ်။
• စုစုပေါင်း ဈေးနှုန်းပြည့်သွားရင် pool ပိတ်ပါပြီ။
• ဗီဒီယိုကို ပေးဆောင်ထားသူတွေဆီကိုပဲ သီးသန့်ပို့ပေးပါတယ် — group ထဲမှာ ဘယ်တော့မှ မဖော်ပြပါဘူး။
• Pool ကတ်ပေါ်မှာ တိုးတက်မှု meter ကို အချိန်နဲ့တပြေးညီ ကြည့်လို့ရပါတယ်။
• ရောင်းသူက ဈေးနှုန်းအပြည့်အဝ ရပါတယ်။

📝 Pool တင်နည်း — /sell (သို့) /pool ကို နှိပ်ပြီး ပစ္စည်းရွေးပါ၊ "🤝 Pool" ကို ရွေးပါ၊ ဈေးနှုန်း (50,000–500,000 ကျပ်) သတ်မှတ်ပါ၊ ဗီဒီယို (1–5 မိနစ်) ပို့ပါ။

🤝 ပါဝင်နည်း — Pool ကတ်ပေါ်က "Join" ကို နှိပ်ပြီး ထည့်မယ့် ငွေပမာဏ ရိုက်ထည့်ပါ။ Balance ထဲက ဖြတ်ပါမယ်။

Pool မပြည့်သေးရင် ပယ်ဖျက်လိုက်ရင် ထည့်ထားတဲ့ ငွေအတိုင်း အကုန်ပြန်ရပါတယ်။

မေးစရာရှိရင် @HenryRealGood ကို ဆက်သွယ်ပါ။"""


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
            "cashout_mm_draft": {},
            "sellusdt": {},
            "sell_seq": 0,
            "sell_draft": {},
            "cards": {},
            "card_seq": 0,
            "card_draft": {},
            "auctions": {},
            "auction_seq": 0,
            "auction_draft": {},
            "pools": {},
            "pool_seq": 0,
            "pool_draft": {},
            "pool_join_draft": {},
            "bid_draft": {},
            "topup_mm_draft": {},
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


def mm_admin_numbers_text():
    """Arkar's admin payment numbers for Myanmar top-ups. The numbers
    are <code> so members can tap to copy them."""
    return (
        f"• KBZPay: <code>{KBZPAY}</code> (Arkar Myo Win)\n"
        f"• WavePay: <code>{WAVEPAY}</code> (Arkar Myo Win)\n"
        f"• AYAPay: <code>{AYAPAY}</code> (Arkar Myowin)"
    )


def mask_mm_number(number):
    """'09403720481' -> '0940…' — for buttons, so the full number is
    not shown on a button row."""
    number = str(number or "")
    return (number[:4] + "…") if len(number) > 4 else number


def parse_mm_account(text):
    """A typed Myanmar account: 'KBZPay 09403720481' -> ('KBZPay',
    '09403720481'). Accepts KBZ/Wave/AYA with or without 'Pay'.
    Returns None if the service is unknown or the number is not a
    Myanmar mobile number (09 + 7–9 digits)."""
    parts = (text or "").strip().split()
    if len(parts) < 2:
        return None
    service = MM_SERVICES.get(parts[0].lower())
    if not service:
        return None
    number = "".join(parts[1:]).replace("-", "").replace(" ", "")
    if not number.isdigit() or not number.startswith("09"):
        return None
    if not 9 <= len(number) <= 11:
        return None
    return service, number


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
                       product, ks, method, status, tx_hash=None, option=None):
    record_event(
        {
            "kind": "market",
            "buyer": str(buyer_id),
            "buyer_username": buyer_username or "",
            "seller": str(seller_id),
            "seller_name": seller_name or "",
            "product": product,
            "option": option or "",
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


def fmt_age_role(age, role):
    """'28 • Top', or '—' for anything missing."""
    a = str(age) if age else "—"
    r = str(role) if role else "—"
    return f"{a} • {r}"


# ------------------------------------------------------- seller titles ----

TITLE_TIERS = (
    (50, "💎 Legend"),
    (25, "👑 Star Seller"),
    (10, "🔥 Top Seller"),
    (5, "🌟 Rising Star"),
    (1, "🛍️ Seller"),
    (0, "🆕 New Seller"),
)


def count_sales(seller_id):
    """Completed marketplace sales by one seller: market sales +
    auction sales + completed pools, all status "paid". A completed
    pool counts as ONE sale. Class session packs do NOT count.
    Computed live from the sales records every time, so a title
    upgrades automatically as the seller sells more — no stored
    title to go stale."""
    sid = str(seller_id)
    total = 0
    for p in load_json_file(PURCHASES_PATH, []):
        if (
            p.get("kind") in ("market", "auction", "pool")
            and p.get("status") == "paid"
            and str(p.get("seller")) == sid
        ):
            total += 1
    return total


def seller_title(sales):
    for minimum, title in TITLE_TIERS:
        if sales >= minimum:
            return title
    return "🆕 New Seller"


def seller_title_line(seller_id):
    """'🔥 Top Seller • 12 sold' — shown on the seller's profile and
    on every post they make."""
    n = count_sales(seller_id)
    return f"{seller_title(n)} • {n} sold"


def profile_missing_fields(profile):
    """What a seller still has to fill in before they can /sell:
    age, role, and 3 photos."""
    missing = []
    if not profile.get("age"):
        missing.append("age")
    if not profile.get("role"):
        missing.append("role")
    if len(profile.get("photos") or []) < 3:
        missing.append("photos")
    return missing


def profile_summary_text(profile):
    lines = [f"👤 {profile.get('name', 'Seller')}"]
    if profile.get("username"):
        lines.append(
            f"@{profile['username']} | ID {profile.get('user_id', '?')}"
        )
    lines.append(
        f"Age: {profile.get('age') or '—'} • "
        f"Role: {profile.get('role') or '—'}"
    )
    lines.append(seller_title_line(profile.get("user_id")))
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
    lines.append(
        f"Age: {profile.get('age') or '—'} • "
        f"Role: {profile.get('role') or '—'}"
    )
    lines.append(seller_title_line(profile.get("user_id")))
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
        "Every seller below has a live profile. Tap a seller to see "
        "their products and pay them."
    )
    for profile in live_profiles:
        lines.append("")
        lines.append(
            f"👤 {profile.get('name', 'Seller')}, "
            f"{fmt_age_role(profile.get('age'), profile.get('role'))} • "
            f"{seller_title_line(profile.get('user_id'))}"
        )
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


def market_item_label(product, option=None):
    """Display name for a market item, e.g. "🥛 Milk (A — Small)" for
    a card option, or just "🥛 Milk" for a plain profile product."""
    label = PRODUCTS.get(product, product)
    if option:
        return f"{label} ({option})"
    return label


def sell_card_text(card):
    """The shopping card posted to the group for one seller product
    with its named options. Every card carries the seller's profile
    (name, age, role). With media it is a sneak peek only — the full
    version is revealed in the group when someone buys it."""
    lines = [
        f"🛍️ {card.get('seller_name', 'Seller')}, "
        f"{fmt_age_role(card.get('age'), card.get('role'))} • "
        f"{seller_title_line(card.get('seller'))} — "
        f"{PRODUCTS.get(card.get('product'), card.get('product', ''))}",
        "",
    ]
    for opt in card.get("options", []):
        lines.append(f"• {opt['name']} — {fmt_ks(opt['price'])}")
    if card.get("media_type"):
        lines.append("")
        lines.append(
            "👀 Sneak peek only — the full version is revealed in "
            "the group when someone buys it."
        )
    lines.append("")
    lines.append("Tap an option to buy it.")
    return "\n".join(lines)


def sell_card_keyboard(card):
    """One Buy button per option (deep link into the bot, which opens
    the buy flow for that option), a Seller profile button, and a
    Remove button for the seller / an admin. URL buttons are used for
    the group card so they work even for members who have never
    started the bot — the same pattern as the sellers board."""
    rows = []
    for idx, opt in enumerate(card.get("options", [])):
        rows.append(
            [
                {
                    "text": f"{opt['name']} — {fmt_ks(opt['price'])}",
                    "url": (
                        f"https://t.me/{bot_username()}"
                        f"?start=card_{card['id']}_{idx}"
                    ),
                }
            ]
        )
    rows.append(
        [
            {
                "text": "👤 Seller profile",
                "url": (
                    f"https://t.me/{bot_username()}"
                    f"?start=seller_{card['seller']}"
                ),
            }
        ]
    )
    rows.append(
        [{"text": "🗑️ Remove", "callback_data": f"carddel:{card['id']}"}]
    )
    return {"inline_keyboard": rows}


ROLE_OPTIONS = ("Top", "Bottom", "Verse")


def download_file_bytes(file_id):
    """Download a Telegram file (photo/video) as bytes, via getFile."""
    r = api("getFile", {"file_id": file_id})
    if not r.get("ok"):
        return None
    path = (r.get("result") or {}).get("file_path")
    if not path:
        return None
    try:
        resp = requests.get(
            f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}",
            timeout=60,
        )
    except Exception as e:
        print(f"file download error: {e}", flush=True)
        return None
    if resp.status_code != 200:
        return None
    return resp.content


def make_blurred_preview(image_bytes):
    """Blur a photo so no detail is visible: shrink it hard, blow it
    back up, then a strong Gaussian blur. Returns JPEG bytes or None."""
    try:
        from io import BytesIO

        from PIL import Image, ImageFilter

        im = Image.open(BytesIO(image_bytes)).convert("RGB")
        w, h = im.size
        scale = min(1.0, 1024 / max(w, h))
        if scale < 1.0:
            im = im.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.LANCZOS,
            )
            w, h = im.size
        small = im.resize(
            (max(1, w // 16), max(1, h // 16)), Image.LANCZOS
        )
        pix = small.resize((w, h), Image.LANCZOS)
        blurred = pix.filter(
            ImageFilter.GaussianBlur(radius=max(10, min(w, h) // 16))
        )
        out = BytesIO()
        blurred.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception as e:
        print(f"blur error: {e}", flush=True)
        return None


def blur_photo_file_id(file_id):
    """Download a photo and return blurred JPEG bytes, or None."""
    raw = download_file_bytes(file_id)
    if not raw:
        return None
    return make_blurred_preview(raw)


def send_photo_file(chat_id, filename, data, caption=None,
                    reply_markup=None):
    """Upload photo bytes via sendPhoto. Returns the api result."""
    payload = {"chat_id": str(chat_id)}
    if caption:
        payload["caption"] = caption
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    files = {"photo": (filename, data, "image/jpeg")}
    return api("sendPhoto", payload, files=files)


def send_photos_group(chat_id, file_ids):
    """Send up to 3 photos as a media group. Returns True if sent."""
    ids = [f for f in (file_ids or []) if f][:3]
    if not ids:
        return False
    media = [{"type": "photo", "media": fid} for fid in ids]
    r = api("sendMediaGroup", {"chat_id": chat_id, "media": media})
    return bool(r.get("ok"))


def send_seller_card(chat_id, profile):
    """A seller's profile card: their 3 photos as a media group
    first, then the text card with products and payment details."""
    send_photos_group(chat_id, profile.get("photos") or [])
    send_message(
        chat_id,
        seller_card_text(profile),
        parse_mode="HTML",
        reply_markup=seller_card_keyboard(profile),
    )


def post_card_to_group(state, card):
    """Post a /sell card to the group. With a blurred preview it goes
    as a photo (caption = card text); otherwise plain text. Returns
    (message_id, err) like post_to_group."""
    group = state.get("group") or GROUP_CHAT_ID
    if not group:
        return None, "no group set"
    text = sell_card_text(card)
    kb = sell_card_keyboard(card)
    if card.get("preview_file_id"):
        r = api(
            "sendPhoto",
            {
                "chat_id": group,
                "photo": card["preview_file_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        r = send_message(group, text, reply_markup=kb)
    if not r.get("ok"):
        return None, r.get("description", "unknown error")
    return r["result"]["message_id"], None


def reveal_card_purchase(state, card_id, option_name, buyer_name):
    """On the FIRST completed purchase of a card, post the full media
    to the group for everyone to see. Later purchases do nothing.
    Returns True if a reveal was posted."""
    card = (state.get("cards") or {}).get(card_id)
    if not card or card.get("revealed"):
        return False
    media = card.get("media_file_id")
    if not media:
        return False
    group = state.get("group") or GROUP_CHAT_ID
    if not group:
        return False
    product = PRODUCTS.get(card.get("product"), card.get("product", ""))
    opt = f" ({option_name})" if option_name else ""
    caption = (
        f"🔓 Revealed: {card.get('seller_name', 'Seller')}'s "
        f"{product}{opt} — bought by {buyer_name or 'Someone'}"
    )
    if card.get("media_type") == "video":
        r = api(
            "sendVideo",
            {"chat_id": group, "video": media, "caption": caption},
        )
    else:
        r = api(
            "sendPhoto",
            {"chat_id": group, "photo": media, "caption": caption},
        )
    if not r.get("ok"):
        return False
    card["revealed"] = True
    save_state(state)
    return True


# ------------------------------------------------------- auction house ----

# Every auction starts at 5,000 Ks; a new bid must beat the current
# bid by at least 1,000 Ks. An auction runs 15 minutes only. An
# unsold auction post stays up 24 hours after posting, then the
# sweep deletes it. Fixed-price cards are never auto-deleted.
# Auction videos must be 1 to 5 minutes long; the card shows the
# length in whole minutes (e.g. "⏱️ 3 min").
AUCTION_START_KS = 5000
AUCTION_MIN_INCREMENT_KS = 1000
AUCTION_DURATION_S = 15 * 60
AUCTION_POST_TTL_S = 24 * 3600
AUCTION_MIN_VIDEO_S = 60
AUCTION_MAX_VIDEO_S = 300

# Group-buy pool ("fundraiser pool"): an expensive video at a
# SELLER-SET price, 50,000–500,000 Ks. Each member contributes
# ONCE, any amount from a 1,000 Ks minimum — the pool fills when
# the total raised hits the set price, however many people that
# takes. The final contribution is capped at exactly what's left,
# so the pool always totals exactly the set price. When it fills,
# the video goes privately to every contributor — NEVER revealed
# in the group. No deadline; removing the pool refunds every
# contributor the exact amount they put in. Pool videos use the
# same 1–5 minute rule as auctions (AUCTION_MIN/MAX_VIDEO_S).
POOL_MIN_PRICE_KS = 50000
POOL_MAX_PRICE_KS = 500000
POOL_MIN_CONTRIB_KS = 1000


def fmt_countdown(seconds):
    """mm:ss left on an auction, e.g. 14:32."""
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def auction_card_text(auction, now=None):
    """The auction card posted to the group. The cover photo is the
    video's own thumbnail, UNBLURRED (unlike v5 fixed-price cards).
    The winner gets the video privately — never revealed in the group,
    unless an admin wins."""
    now = int(time.time()) if now is None else int(now)
    title = seller_title_line(auction.get("seller"))
    lines = [
        f"🔨 AUCTION — {auction.get('seller_name', 'Seller')}, "
        f"{fmt_age_role(auction.get('age'), auction.get('role'))} • "
        f"{title} — "
        f"{PRODUCTS.get(auction.get('product'), auction.get('product', ''))}",
        "",
        f"Starting bid: {fmt_ks(auction.get('start', AUCTION_START_KS))}",
    ]
    if auction.get("duration_min"):
        lines.insert(1, f"⏱️ {auction['duration_min']} min")
    if auction.get("current_bidder"):
        lines.append(
            f"Current bid: {fmt_ks(auction['current_bid'])} by "
            f"{auction.get('current_bidder_name', 'Someone')}"
        )
    else:
        lines.append("Current bid: No bids yet")
    if auction.get("status") == "live":
        lines.append(
            f"Ends in: {fmt_countdown(auction.get('ends_at', 0) - now)}"
        )
    elif auction.get("status") == "ended":
        lines.append("⏰ Auction ended — no bids.")
    lines.append("")
    lines.append(
        "Highest bidder wins the video privately — it is NOT revealed "
        "in the group. (If an admin wins, it is revealed in the group.)"
    )
    lines.append("")
    lines.append("Tap 💰 Bid to bid from your bot balance.")
    return "\n".join(lines)


def auction_card_keyboard(auction):
    """Bid (deep link into the bot DM — works for members who never
    started the bot), Seller profile, Remove. The Bid button is gone
    once the auction is no longer live."""
    rows = []
    if auction.get("status") == "live":
        rows.append(
            [
                {
                    "text": "💰 Bid",
                    "url": (
                        f"https://t.me/{bot_username()}"
                        f"?start=auction_{auction['id']}"
                    ),
                }
            ]
        )
    rows.append(
        [
            {
                "text": "👤 Seller profile",
                "url": (
                    f"https://t.me/{bot_username()}"
                    f"?start=seller_{auction['seller']}"
                ),
            }
        ]
    )
    rows.append(
        [{"text": "🗑️ Remove", "callback_data": f"aucdel:{auction['id']}"}]
    )
    return {"inline_keyboard": rows}


def post_auction_to_group(state, auction):
    """Post an auction card to the group: the cover photo (the video's
    own thumbnail, UNBLURRED) with the auction text as caption, or
    plain text if there is no cover. Returns (message_id, err)."""
    group = state.get("group") or GROUP_CHAT_ID
    if not group:
        return None, "no group set"
    text = auction_card_text(auction)
    kb = auction_card_keyboard(auction)
    if auction.get("cover_file_id"):
        r = api(
            "sendPhoto",
            {
                "chat_id": group,
                "photo": auction["cover_file_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        r = send_message(group, text, reply_markup=kb)
    if not r.get("ok"):
        return None, r.get("description", "unknown error")
    return r["result"]["message_id"], None


def edit_auction_card(state, auction):
    """Refresh the group card after a bid (or when it ends with no
    bids): new current bid + bidder + time left. Photo cards are
    edited by caption, text cards by text."""
    group = state.get("group") or GROUP_CHAT_ID
    if not group or not auction.get("message_id"):
        return
    text = auction_card_text(auction)
    kb = auction_card_keyboard(auction)
    if auction.get("cover_file_id"):
        api(
            "editMessageCaption",
            {
                "chat_id": group,
                "message_id": auction["message_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        api(
            "editMessageText",
            {
                "chat_id": group,
                "message_id": auction["message_id"],
                "text": text,
                "reply_markup": kb,
            },
        )


def _seller_ready(chat_id, user_id, state):
    """Shared gates for /sell and /auction: a live profile, complete
    (age, role, 3 photos), and the group linked. Sends the right
    message and returns the profile, or None when the seller can't
    post yet."""
    profile = get_profile(user_id)
    if not profile:
        send_message(
            chat_id,
            "You don't have a seller profile yet — make one with "
            "/profile first. It goes live straight away.",
        )
        return None
    if profile.get("status") != "live":
        if profile.get("status") == "removed":
            send_message(
                chat_id,
                "Your profile was removed by an admin — make a new "
                "one with /profile and you can post again.",
            )
        else:
            send_message(
                chat_id,
                "Your profile isn't live yet — make a new one with "
                "/profile and it goes live straight away.",
            )
        return None
    # Sellers with an older profile (no age / role / photos) finish
    # it first — age, role and 3 photos are required to post.
    if profile_missing_fields(profile):
        start_profile_completion(chat_id, user_id, state)
        return None
    group = state.get("group") or GROUP_CHAT_ID
    if not group:
        send_message(
            chat_id,
            "The group isn't linked yet — ask an admin to link it "
            "(/setgroup), then try again.",
        )
        return None
    return profile


def send_auction_preview(chat_id, user_id, draft):
    """Show the seller exactly what will post: the cover photo
    UNBLURRED, the auction text, Post / Cancel buttons."""
    profile = get_profile(user_id)
    preview = {
        "seller_name": draft.get("seller_name", "Seller"),
        "age": (profile or {}).get("age"),
        "role": (profile or {}).get("role"),
        "seller": str(user_id),
        "product": draft.get("product"),
        "start": AUCTION_START_KS,
        "duration_min": draft.get("duration_min"),
        "current_bidder": None,
        "ends_at": int(time.time()) + AUCTION_DURATION_S,
        "status": "live",
    }
    text = "This is what will post to the group:\n\n" + auction_card_text(
        preview
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": "✅ Post auction", "callback_data": "auctpost"},
                {"text": "❌ Cancel", "callback_data": "auctcancel"},
            ]
        ]
    }
    if draft.get("cover_file_id"):
        api(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": draft["cover_file_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        send_message(chat_id, text, reply_markup=kb)


def send_pool_info(chat_id, pool):
    """The FULL contributor list for one pool, in a DM: every
    member with their running total, highest first. The group card
    only shows the top 10 (caption limit), so this is where the
    whole list lives. Works for live and filled pools."""
    price = int(pool.get("price") or POOL_MIN_PRICE_KS)
    raised = pool_raised(pool)
    joined = len(pool.get("contributors") or [])
    product = PRODUCTS.get(pool.get("product"), pool.get("product", ""))
    status = pool.get("status", "live")
    lines = [
        f"🤝 Pool — {pool.get('seller_name', 'Seller')}'s {product}",
        "",
        f"Price: {fmt_ks(price)} — "
        f"{fmt_ks(POOL_MIN_CONTRIB_KS)} or more per person",
        f"{pool_meter(raised, price)}",
        f"👥 {joined} "
        f"{'person has' if joined == 1 else 'people have'} joined",
        f"Status: {status}",
        "",
        "Contributors:",
    ]
    contributors = sorted(
        (pool.get("contributors") or []),
        key=lambda c: int(c.get("ks") or 0),
        reverse=True,
    )
    if not contributors:
        lines.append("No one has joined yet.")
    for i, c in enumerate(contributors, 1):
        who = f"@{c['username']}" if c.get("username") else (
            c.get("name") or "Someone"
        )
        lines.append(f"{i}. {who} — {fmt_ks(int(c.get('ks') or 0))}")
    send_message(chat_id, "\n".join(lines))


def start_auction(chat_id, user_id, state, user=None):
    """Entry for /auction. Same gates as /sell (live profile, complete
    profile, group linked), then the seller picks a product and the
    auction flow starts."""
    profile = _seller_ready(chat_id, user_id, state)
    if profile is None:
        return
    products = profile.get("products", {})
    if not products:
        send_message(
            chat_id,
            "Your profile has no products — update it with /profile "
            "first.",
        )
        return
    state.get("card_draft", {}).pop(str(user_id), None)
    state.get("pool_draft", {}).pop(str(user_id), None)
    state.setdefault("auction_draft", {})[str(user_id)] = {
        "step": "product",
        "seller_name": profile.get("name", "Seller"),
    }
    save_state(state)
    rows = [
        [
            {
                "text": f"{PRODUCTS.get(k, k)} — {fmt_ks(v)}",
                "callback_data": f"aucprod:{k}",
            }
        ]
        for k, v in products.items()
    ]
    send_message(
        chat_id,
        "🔨 What are you auctioning? Pick a product from your profile.",
        reply_markup={"inline_keyboard": rows},
    )


def handle_auction_step(chat_id, user_id, text, state, user=None):
    """Text nudges during the /auction flow. Media is handled by
    handle_flow_media; this just answers stray text. Returns True if
    the message was consumed."""
    draft = (state.get("auction_draft") or {}).get(str(user_id))
    if not draft:
        return False
    step = draft.get("step")
    if step == "product":
        send_message(
            chat_id, "Tap a product above to pick it — or /cancel to stop."
        )
        return True
    if step == "video":
        send_message(
            chat_id,
            "Send the auction video now (1 to 5 minutes) — or /cancel "
            "to stop.",
        )
        return True
    if step == "cover":
        send_message(
            chat_id, "Send a cover photo for the video — or /cancel to stop."
        )
        return True
    return False


def parse_bid_amount(text):
    """A typed auction bid: a whole number of Ks, no range cap (the
    minimum-bid rule is checked in place_auction_bid)."""
    cleaned = (text or "").replace(",", "").replace(" ", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def send_bid_prompt(chat_id, auction):
    """The DM bid screen for one auction: current bid, minimum next
    bid, the bidder's balance, quick bids (+1,000 / +5,000 / +10,000
    over the current bid) and a typed-amount option. Bids come from
    the bot balance only."""
    current = (
        auction.get("current_bid")
        if auction.get("current_bidder")
        else auction.get("start", AUCTION_START_KS)
    )
    min_next = current + AUCTION_MIN_INCREMENT_KS
    balance = get_balance(chat_id)
    left = max(0, auction.get("ends_at", 0) - int(time.time()))
    seller_name = auction.get("seller_name", "Seller")
    product = PRODUCTS.get(auction.get("product"), auction.get("product", ""))
    if auction.get("current_bidder"):
        cur_line = (
            f"Current bid: {fmt_ks(current)} by "
            f"{auction.get('current_bidder_name', 'Someone')}"
        )
    else:
        cur_line = (
            "No bids yet — starting bid "
            f"{fmt_ks(auction.get('start', AUCTION_START_KS))}"
        )
    text = (
        f"🔨 Auction — {seller_name}'s {product}\n\n"
        f"{cur_line}\n"
        f"Minimum next bid: {fmt_ks(min_next)}\n"
        f"Ends in: {fmt_countdown(left)}\n"
        f"Your balance: {fmt_ks(balance)}\n\n"
        "Bids come from your bot balance only — top up with /topup "
        "first if you're short. If someone outbids you, your bid is "
        "refunded to your balance automatically.\n\n"
        "Win and the video is yours privately in this chat."
    )
    rows = []
    for amount in (min_next, current + 5000, current + 10000):
        rows.append(
            [
                {
                    "text": f"💰 Bid {fmt_ks(amount)}",
                    "callback_data": f"aucbidamt:{auction['id']}:{amount}",
                }
            ]
        )
    rows.append(
        [
            {
                "text": "✏️ Type an amount",
                "callback_data": f"aucbidtype:{auction['id']}",
            }
        ]
    )
    rows.append([{"text": "💰 Top up balance", "callback_data": "topup"}])
    send_message(chat_id, text, reply_markup={"inline_keyboard": rows})


def place_auction_bid(state, auction, bidder_id, amount, user=None):
    """Validate and apply one auction bid (balance only, escrowed).
    Returns (ok, message for the bidder). On a valid bid the previous
    leader is refunded immediately, the card is updated, and the
    seller is told."""
    now = int(time.time())
    if auction.get("status") != "live" or now >= auction.get("ends_at", 0):
        return False, "That auction has ended."
    if str(bidder_id) == str(auction.get("seller")):
        return False, "You can't bid on your own auction."
    if str(bidder_id) == str(auction.get("current_bidder")):
        return (
            False,
            "You're already the highest bidder — wait to be outbid first.",
        )
    current = (
        auction.get("current_bid")
        if auction.get("current_bidder")
        else auction.get("start", AUCTION_START_KS)
    )
    min_next = current + AUCTION_MIN_INCREMENT_KS
    if amount < min_next:
        return False, f"Minimum bid is {fmt_ks(min_next)}."
    balance = get_balance(bidder_id)
    if balance < amount:
        return (
            False,
            f"Your balance is {fmt_ks(balance)} — top up with /topup "
            "first, then bid again.",
        )
    prev_bidder = auction.get("current_bidder")
    prev_bid = int(auction.get("current_bid", 0))
    if change_balance(bidder_id, -amount) is None:
        return False, "Not enough balance — top up with /topup first."
    if prev_bidder:
        change_balance(prev_bidder, prev_bid)
        send_message(
            prev_bidder,
            f"😕 You've been outbid on "
            f"{auction.get('seller_name', 'Seller')}'s "
            f"{PRODUCTS.get(auction.get('product'), auction.get('product', ''))} "
            f"auction — your {fmt_ks(prev_bid)} was refunded to your "
            "balance.",
        )
    product = PRODUCTS.get(auction.get("product"), auction.get("product", ""))
    auction["current_bid"] = amount
    auction["current_bidder"] = str(bidder_id)
    auction["current_bidder_name"] = (
        (user or {}).get("first_name")
        or (user or {}).get("username")
        or "Someone"
    )
    auction["current_bidder_username"] = (user or {}).get("username", "")
    save_state(state)
    edit_auction_card(state, auction)
    send_message(
        auction["seller"],
        f"💰 New bid: {fmt_ks(amount)} on your {product} auction by "
        f"{auction['current_bidder_name']}.",
    )
    return (
        True,
        f"✅ You're the highest bidder at {fmt_ks(amount)} for "
        f"{product}! If someone outbids you, your bid is refunded "
        "automatically.",
    )


def _refund_auction_leader(state, auction):
    """Give the current highest bidder their escrowed bid back."""
    bidder = auction.get("current_bidder")
    bid = int(auction.get("current_bid", 0))
    if bidder and bid:
        change_balance(bidder, bid)
        send_message(
            bidder,
            f"↩️ Your bid of {fmt_ks(bid)} on "
            f"{auction.get('seller_name', 'Seller')}'s "
            f"{PRODUCTS.get(auction.get('product'), auction.get('product', ''))} "
            "auction was refunded — the auction was removed.",
        )
    auction["current_bidder"] = None
    auction["current_bid"] = auction.get("start", AUCTION_START_KS)


def _delete_auction_card(state, auction):
    """Delete the auction card message from the group, if it is still
    there."""
    group = state.get("group") or GROUP_CHAT_ID
    if group and auction.get("message_id"):
        api(
            "deleteMessage",
            {"chat_id": group, "message_id": auction["message_id"]},
        )


def _close_auction(state, auction, now):
    """The 15-minute deadline hit. With a winner: the escrowed bid
    goes to the seller and the video is delivered privately to the
    winner — unless an admin won, in which case it is revealed in
    the whole group. With no bids: close the auction, leave the post
    up (the 24-hour sweep deletes it later)."""
    group = state.get("group") or GROUP_CHAT_ID
    bidder = auction.get("current_bidder")
    bid = int(auction.get("current_bid", 0))
    seller = str(auction.get("seller"))
    product = PRODUCTS.get(auction.get("product"), auction.get("product", ""))
    winner_name = auction.get("current_bidder_name") or "Someone"
    if bidder:
        change_balance(seller, bid)
        record_event(
            {
                "kind": "auction",
                "buyer": str(bidder),
                "buyer_username": auction.get("current_bidder_username", ""),
                "seller": seller,
                "seller_name": auction.get("seller_name", "Seller"),
                "product": auction.get("product"),
                "ks": bid,
                "method": "Balance (auction)",
                "status": "paid",
                "ts": now,
            }
        )
        auction["status"] = "sold"
        if is_admin(bidder):
            if group:
                api(
                    "sendVideo",
                    {
                        "chat_id": group,
                        "video": auction["video_file_id"],
                        "caption": (
                            f"🔨 Auction won by {winner_name} — revealed "
                            f"in the group: {auction.get('seller_name', 'Seller')}'s "
                            f"{product} for {fmt_ks(bid)}"
                        ),
                        "protect_content": True,
                    },
                )
                send_message(
                    bidder,
                    f"🎉 You won the auction for {product} at "
                    f"{fmt_ks(bid)} — revealed in the group for everyone "
                    "to see.",
                )
            else:
                api(
                    "sendVideo",
                    {
                        "chat_id": bidder,
                        "video": auction["video_file_id"],
                        "caption": (
                            f"🎉 You won the auction! "
                            f"{auction.get('seller_name', 'Seller')}'s "
                            f"{product} — {fmt_ks(bid)}."
                        ),
                        "protect_content": True,
                    },
                )
                send_message(
                    bidder,
                    f"🎉 You won the auction for {product} at "
                    f"{fmt_ks(bid)}. The group isn't linked, so here it "
                    "is privately.",
                )
        else:
            api(
                "sendVideo",
                {
                    "chat_id": bidder,
                    "video": auction["video_file_id"],
                    "caption": (
                        f"🎉 You won the auction! "
                        f"{auction.get('seller_name', 'Seller')}'s "
                        f"{product} — {fmt_ks(bid)}. This video is yours "
                        "privately."
                    ),
                    "protect_content": True,
                },
            )
            send_message(
                bidder,
                f"🎉 You won the auction for {product} at "
                f"{fmt_ks(bid)}! The video is in your private chat — "
                "enjoy. 🙏",
            )
        send_message(
            seller,
            f"💰 Your {product} auction sold for {fmt_ks(bid)} to "
            f"{winner_name} — credited to your balance.",
        )
        _delete_auction_card(state, auction)
    else:
        auction["status"] = "ended"
        edit_auction_card(state, auction)
    save_state(state)


def sweep_auctions(state, now=None):
    """Deadline sweep for auctions — runs every polling iteration, so
    no external cron is needed. Closes 15-minute auctions at their
    deadline and deletes unsold auction posts 24 hours after posting.
    Fixed-price cards are never touched. `now` is injectable for
    tests. Returns True if anything changed."""
    now = int(time.time()) if now is None else int(now)
    changed = False
    for auction in list((state.get("auctions") or {}).values()):
        status = auction.get("status")
        if status == "live":
            profile = get_profile(auction.get("seller"))
            if not profile or profile.get("status") != "live":
                _refund_auction_leader(state, auction)
                _delete_auction_card(state, auction)
                auction["status"] = "removed"
                changed = True
                continue
            if now >= auction.get("ends_at", 0):
                _close_auction(state, auction, now)
                changed = True
        elif status == "ended":
            if now >= auction.get("posted_at", 0) + AUCTION_POST_TTL_S:
                _delete_auction_card(state, auction)
                auction["status"] = "expired"
                changed = True
    if changed:
        save_state(state)
    return changed


def send_sellers_list(chat_id):
    profiles = load_profiles()
    live = [p for p in profiles.values() if p.get("status") == "live"]
    if not live:
        send_message(
            chat_id,
            "No live sellers yet — make a profile with /profile and "
            "it goes live straight away.\n\n"
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
        lines.append(
            f"👤 {p.get('name', 'Seller')}, "
            f"{fmt_age_role(p.get('age'), p.get('role'))} • "
            f"{seller_title_line(p.get('user_id'))} — {products}"
        )
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
    rows.append(
        [
            {
                "text": "🇲🇲 KBZPay / WavePay / AYAPay",
                "callback_data": "topup_mm",
            }
        ]
    )
    send_message(
        user_id,
        "Top up your balance — pick an amount and a method.\n\n"
        "Stars: a native invoice from the bot.\n"
        "USDT: send it on BSC, paste the hash, I'll verify on-chain.\n"
        "🇲🇲 KBZPay / WavePay / AYAPay: pay the admin, send the receipt "
        f"— minimum {fmt_ks(TOPUP_MM_MIN_KS)}.",
        reply_markup={"inline_keyboard": rows},
    )


def send_buy_options(user_id, profile, product, price, option=None,
                     card_id=None, opt_idx=None):
    """Payment choices for one market item. `option`/`card_id` are set
    when the buyer came from a /sell card option — the buy callbacks
    then carry the card + option index so the option price (not the
    profile price) is charged. Plain profile buys leave them unset
    and the callbacks stay in the old 4-part form."""
    seller_name = profile.get("name", "Seller")
    balance = get_balance(user_id)
    stars = max(1, round(price / 50))
    usd = price / KS_PER_USD
    suffix = f":{card_id}:{opt_idx}" if card_id is not None else ""
    item = market_item_label(product, option)
    rows = []
    if balance >= price:
        rows.append(
            [
                {
                    "text": f"💰 Pay from balance ({fmt_ks(balance)})",
                    "callback_data": f"buypay:balance:{profile['user_id']}:{product}{suffix}",
                }
            ]
        )
    else:
        rows.append([{"text": "💰 Top up balance", "callback_data": "topup"}])
    rows.append(
        [
            {
                "text": f"⭐ Pay {stars} Stars now",
                "callback_data": f"buypay:stars:{profile['user_id']}:{product}{suffix}",
            }
        ]
    )
    rows.append(
        [
            {
                "text": f"💎 Pay {usd:g} USDT now",
                "callback_data": f"buypay:usdt:{profile['user_id']}:{product}{suffix}",
            }
        ]
    )
    rows.append(
        [
            {
                "text": "🇲🇲 Pay seller directly",
                "callback_data": f"buypay:direct:{profile['user_id']}:{product}{suffix}",
            }
        ]
    )
    text = (
        f"🛍 {item} from {seller_name} — "
        f"{fmt_ks(price)} (${usd:g})\n\n"
        "How do you want to pay?\n"
        f"💰 Balance: you have {fmt_ks(balance)}.\n"
        f"⭐ Stars: {stars} Stars go to the bot, the seller gets the balance.\n"
        f"💎 USDT: {usd:g} USDT to the bot, the seller gets the balance.\n"
        "🇲🇲 Direct: pay the seller's own KBZPay / WavePay / AYAPay / "
        "bank / USDT and send a receipt."
    )
    send_message(user_id, text, reply_markup={"inline_keyboard": rows})


# --------------------------------------------------- group-buy pool ----

def pool_raised(pool):
    """Total Ks raised so far: the stored total, or the sum of
    contributor amounts for pools saved before v7.2 (their entries
    carry no 'ks', and each put in the old fixed 1,000 Ks)."""
    if pool.get("raised") is not None:
        return int(pool["raised"])
    total = 0
    for c in pool.get("contributors") or []:
        total += int(c.get("ks") or POOL_MIN_CONTRIB_KS)
    return total


def parse_pool_price(text):
    """A seller-typed pool price: a whole number of Ks inside
    50,000–500,000. Returns the Ks int, or None."""
    cleaned = (text or "").replace(",", "").replace(" ", "").strip()
    if not cleaned.isdigit():
        return None
    price = int(cleaned)
    if price < POOL_MIN_PRICE_KS or price > POOL_MAX_PRICE_KS:
        return None
    return price


def pool_meter(raised, total, show_remaining=True):
    """10-segment money progress bar for a pool, e.g. on a 100,000
    Ks pool with 32,000 raised:
    '▓▓▓░░░░░░░ 32,000 / 100,000 Ks • 68,000 Ks to go'.
    Filled segments = round(raised / total × 10). One rendering,
    shared by the group card, the seller preview and the join
    prompt, so the meter is always the same everywhere."""
    total = int(total) if total else POOL_MIN_PRICE_KS
    raised = max(0, min(int(raised), total))
    filled = round(raised / total * 10) if total else 0
    bar = "▓" * filled + "░" * (10 - filled)
    text = f"{bar} {raised:,} / {total:,} Ks"
    if show_remaining:
        text += f" • {total - raised:,} Ks to go"
    return text


def pool_contributor_block(pool, max_count=10):
    """The contributor list shown on the pool card, under the meter
    ('the meter list'): one line per member with their RUNNING
    TOTAL, highest first, e.g. '@alice — 10,000 Ks'. A member who
    topped up again keeps a single line whose total grew. Capped
    at max_count lines; if more contributors exist, a final
    '…and N more people (see /poolinfo <id>)' line points at the
    full list."""
    contributors = sorted(
        (pool.get("contributors") or []),
        key=lambda c: int(c.get("ks") or 0),
        reverse=True,
    )
    if not contributors or max_count <= 0:
        return []
    lines = []
    for c in contributors[:max_count]:
        who = f"@{c['username']}" if c.get("username") else (
            c.get("name") or "Someone"
        )
        lines.append(f"{who} — {fmt_ks(int(c.get('ks') or 0))}")
    extra = len(contributors) - len(contributors[:max_count])
    if extra > 0:
        lines.append(
            f"…and {extra} more "
            f"{'person' if extra == 1 else 'people'} "
            f"(see /poolinfo {pool.get('id', '')})"
        )
    return lines


def pool_card_text(pool):
    """The pool card posted to the group. The cover photo is the
    video's own thumbnail, UNBLURRED (same as auctions). The video
    is NEVER revealed in the group — on completion it goes privately
    to every contributor's DM. The card carries a LIVE money meter,
    refreshed on every join, plus the contributor count and the
    contributor list under the meter (top 10 by total). The caption
    limit is 1,024 chars, so the list shrinks until the card fits."""
    title = seller_title_line(pool.get("seller"))
    price = int(pool.get("price") or POOL_MIN_PRICE_KS)
    raised = pool_raised(pool)
    joined = len(pool.get("contributors") or [])
    lines = [
        f"🤝 POOL — {pool.get('seller_name', 'Seller')}, "
        f"{fmt_age_role(pool.get('age'), pool.get('role'))} • "
        f"{title} — "
        f"{PRODUCTS.get(pool.get('product'), pool.get('product', ''))}",
        "",
        f"Price: {fmt_ks(price)} — "
        f"{fmt_ks(POOL_MIN_CONTRIB_KS)} or more per person",
    ]
    if pool.get("duration_min"):
        lines.insert(1, f"⏱️ {pool['duration_min']} min")
    tail = [
        "",
        "When the pool fills, the video goes privately to everyone "
        "who paid — it is NEVER revealed in the group.",
        "",
        f"Tap 🤝 Join to put in {fmt_ks(POOL_MIN_CONTRIB_KS)} or more "
        "from your bot balance.",
    ]
    if pool.get("status") == "live":
        lines.append(pool_meter(raised, price))
        lines.append(
            f"👥 {joined} "
            f"{'person has' if joined == 1 else 'people have'} joined"
        )
        shown = min(10, joined)
        while True:
            block = pool_contributor_block(pool, shown)
            text = "\n".join(
                lines + ([""] + block if block else []) + tail
            )
            if len(text) <= 1000 or shown == 0:
                return text
            shown -= 1
    elif pool.get("status") == "filled":
        lines.append(
            pool_meter(raised, price, show_remaining=False)
            + " — pool filled! 🎉"
        )
        lines.append(
            f"👥 {joined} "
            f"{'person' if joined == 1 else 'people'} joined"
        )
    return "\n".join(lines + tail)


def pool_card_keyboard(pool):
    """Join (deep link into the bot DM — works for members who never
    started the bot), Contributors (full list in DM), Seller
    profile, Remove. The Join button is gone once the pool is no
    longer live."""
    rows = []
    if pool.get("status") == "live":
        rows.append(
            [
                {
                    "text": f"🤝 Join — from {fmt_ks(POOL_MIN_CONTRIB_KS)}",
                    "url": (
                        f"https://t.me/{bot_username()}"
                        f"?start=pool_{pool['id']}"
                    ),
                }
            ]
        )
    rows.append(
        [
            {
                "text": "📋 Contributors",
                "url": (
                    f"https://t.me/{bot_username()}"
                    f"?start=poolinfo_{pool['id']}"
                ),
            }
        ]
    )
    rows.append(
        [
            {
                "text": "👤 Seller profile",
                "url": (
                    f"https://t.me/{bot_username()}"
                    f"?start=seller_{pool['seller']}"
                ),
            }
        ]
    )
    rows.append(
        [{"text": "🗑️ Remove", "callback_data": f"pooldel:{pool['id']}"}]
    )
    return {"inline_keyboard": rows}


def post_pool_to_group(state, pool):
    """Post a pool card to the group: the cover photo (the video's
    own thumbnail, UNBLURRED) with the pool text as caption, or
    plain text if there is no cover. Returns (message_id, err)."""
    group = state.get("group") or GROUP_CHAT_ID
    if not group:
        return None, "no group set"
    text = pool_card_text(pool)
    kb = pool_card_keyboard(pool)
    if pool.get("cover_file_id"):
        r = api(
            "sendPhoto",
            {
                "chat_id": group,
                "photo": pool["cover_file_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        r = send_message(group, text, reply_markup=kb)
    if not r.get("ok"):
        return None, r.get("description", "unknown error")
    return r["result"]["message_id"], None


def edit_pool_card(state, pool):
    """Refresh the group card after someone joins: new count +
    remaining. Photo cards are edited by caption, text cards by
    text."""
    group = state.get("group") or GROUP_CHAT_ID
    if not group or not pool.get("message_id"):
        return
    text = pool_card_text(pool)
    kb = pool_card_keyboard(pool)
    if pool.get("cover_file_id"):
        api(
            "editMessageCaption",
            {
                "chat_id": group,
                "message_id": pool["message_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        api(
            "editMessageText",
            {
                "chat_id": group,
                "message_id": pool["message_id"],
                "text": text,
                "reply_markup": kb,
            },
        )


def _delete_pool_card(state, pool):
    """Delete the pool card message from the group, if it is still
    there."""
    group = state.get("group") or GROUP_CHAT_ID
    if group and pool.get("message_id"):
        api(
            "deleteMessage",
            {"chat_id": group, "message_id": pool["message_id"]},
        )


def _refund_pool_contributors(state, pool):
    """Give every contributor back the exact amount they put in."""
    product = PRODUCTS.get(pool.get("product"), pool.get("product", ""))
    for c in pool.get("contributors") or []:
        amount = int(c.get("ks") or POOL_MIN_CONTRIB_KS)
        change_balance(c["id"], amount)
        send_message(
            c["id"],
            f"↩️ Your {fmt_ks(amount)} for "
            f"{pool.get('seller_name', 'Seller')}'s {product} pool was "
            "refunded — the pool was removed.",
        )
    pool["contributors"] = []
    pool["raised"] = 0


def _complete_pool(state, pool):
    """The pool filled: total raised hit the set price. The seller
    gets exactly the set price, the video goes PRIVATELY to every
    contributor's DM, and the pool card is deleted. Nothing is ever
    posted to the group."""
    now = int(time.time())
    seller = str(pool.get("seller"))
    price = int(pool.get("price") or POOL_MIN_PRICE_KS)
    product = PRODUCTS.get(pool.get("product"), pool.get("product", ""))
    contributors = list(pool.get("contributors") or [])
    change_balance(seller, price)
    record_event(
        {
            "kind": "pool",
            "buyer": "",
            "buyer_username": "",
            "seller": seller,
            "seller_name": pool.get("seller_name", "Seller"),
            "product": pool.get("product"),
            "ks": price,
            "contributors": len(contributors),
            "method": "Balance (pool)",
            "status": "paid",
            "ts": now,
        }
    )
    pool["status"] = "filled"
    for c in contributors:
        api(
            "sendVideo",
            {
                "chat_id": c["id"],
                "video": pool["video_file_id"],
                "caption": (
                    f"🤝 Pool filled! {pool.get('seller_name', 'Seller')}'s "
                    f"{product} — {fmt_ks(price)} shared by "
                    f"{len(contributors)} "
                    f"{'person' if len(contributors) == 1 else 'people'}. "
                    "This video is yours privately."
                ),
                "protect_content": True,
            },
        )
        send_message(
            c["id"],
            f"🎉 The pool for {product} is full — the video is in "
            "your private chat. Enjoy. 🙏",
        )
    send_message(
        seller,
        f"💰 Your {product} pool filled — {len(contributors)} "
        f"{'person' if len(contributors) == 1 else 'people'} put in "
        f"{fmt_ks(price)} in total — credited to your balance.",
    )
    _delete_pool_card(state, pool)
    save_state(state)


def join_pool(state, pool, user_id, amount, user=None):
    """One member joins a pool with an amount of their choice
    (minimum 1,000 Ks PER contribution). A member may contribute
    MORE than once: each top-up adds to their RUNNING TOTAL in the
    single contributor entry for them (one line on the card, one
    video on completion, one refund of their total on cancel).
    The amount is CAPPED at exactly what's left: if 1,000 Ks is
    all that's needed, only 1,000 Ks is taken even when the member
    offered more. Returns (ok, message for the member). When the
    total raised hits the set price the pool completes: seller
    credited the exact price, video sent privately to all
    contributors."""
    if pool.get("status") != "live":
        return False, "That pool is closed — check the group for the latest one."
    if str(user_id) == str(pool.get("seller")):
        return False, "You can't join your own pool."
    contributors = pool.setdefault("contributors", [])
    existing = next(
        (c for c in contributors if str(c.get("id")) == str(user_id)),
        None,
    )
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return False, "Send the amount as a whole number in Ks."
    if amount < POOL_MIN_CONTRIB_KS:
        return (
            False,
            f"Minimum is {fmt_ks(POOL_MIN_CONTRIB_KS)} — send an amount "
            "of 1,000 Ks or more.",
        )
    price = int(pool.get("price") or POOL_MIN_PRICE_KS)
    raised = pool_raised(pool)
    remaining = price - raised
    if remaining <= 0:
        return False, "That pool is already full."
    take = min(amount, remaining)
    capped_note = ""
    if take < amount:
        capped_note = (
            f"Only {fmt_ks(take)} was needed — taking {fmt_ks(take)}, "
            "the rest stays in your balance. "
        )
    balance = get_balance(user_id)
    if balance < take:
        return (
            False,
            f"Your balance is {fmt_ks(balance)} — top up with /topup "
            "first, then join again.",
        )
    if change_balance(user_id, -take) is None:
        return False, "Not enough balance — top up with /topup first."
    name = (user or {}).get("first_name") or (user or {}).get(
        "username"
    ) or "Someone"
    if existing is not None:
        # A top-up: grow their running total, keep one entry.
        existing["ks"] = int(existing.get("ks") or 0) + take
        existing["name"] = name
        existing["username"] = (user or {}).get("username", "")
        entry = existing
    else:
        entry = {
            "id": str(user_id),
            "name": name,
            "username": (user or {}).get("username", ""),
            "ks": take,
        }
        contributors.append(entry)
    pool["raised"] = raised + take
    save_state(state)
    if pool["raised"] >= price:
        _complete_pool(state, pool)
        return (
            True,
            f"{capped_note}🎉 You filled the pool! The video is on "
            "its way to your private chat. 🙏",
        )
    product = PRODUCTS.get(pool.get("product"), pool.get("product", ""))
    edit_pool_card(state, pool)
    total = int(entry.get("ks") or 0)
    if existing is not None:
        send_message(
            pool["seller"],
            f"🤝 {name} topped up their {product} pool — "
            f"put in {fmt_ks(take)} more (their total is now "
            f"{fmt_ks(total)}; {fmt_ks(pool['raised'])} / "
            f"{fmt_ks(price)} raised, {len(contributors)} "
            f"{'person' if len(contributors) == 1 else 'people'}).",
        )
        return (
            True,
            f"{capped_note}✅ Added {fmt_ks(take)} — your total in "
            f"this pool is now {fmt_ks(total)} "
            f"({fmt_ks(pool['raised'])} / {fmt_ks(price)} raised). "
            "The video comes to your private chat when the pool fills.",
        )
    send_message(
        pool["seller"],
        f"🤝 {name} joined your {product} pool — "
        f"put in {fmt_ks(take)} ({fmt_ks(pool['raised'])} / "
        f"{fmt_ks(price)} raised, {len(contributors)} "
        f"{'person' if len(contributors) == 1 else 'people'}).",
    )
    return (
        True,
        f"{capped_note}✅ You're in! {fmt_ks(take)} in — "
        f"your total is {fmt_ks(total)} "
        f"({fmt_ks(pool['raised'])} / {fmt_ks(price)} raised). "
        "The video comes to your private chat when the pool fills.",
    )


def send_join_prompt(chat_id, pool):
    """The DM join screen for one pool: price, money meter, the
    member's balance, Join and Top up. Joining asks for the amount
    first (minimum 1,000 Ks per contribution) — the typed amount is
    taken from the bot balance only, capped at what's left. A
    member who already put in money sees their running total, and
    can add more — contributions are not one-per-person."""
    price = int(pool.get("price") or POOL_MIN_PRICE_KS)
    raised = pool_raised(pool)
    joined = len(pool.get("contributors") or [])
    balance = get_balance(chat_id)
    product = PRODUCTS.get(pool.get("product"), pool.get("product", ""))
    mine = next(
        (
            int(c.get("ks") or 0)
            for c in pool.get("contributors") or []
            if str(c.get("id")) == str(chat_id)
        ),
        0,
    )
    text = (
        f"🤝 Pool — {pool.get('seller_name', 'Seller')}'s {product}\n\n"
        f"Price: {fmt_ks(price)} — "
        f"{fmt_ks(POOL_MIN_CONTRIB_KS)} or more per person\n"
        f"{pool_meter(raised, price)}\n"
        f"👥 {joined} "
        f"{'person has' if joined == 1 else 'people have'} joined\n"
        f"Your balance: {fmt_ks(balance)}\n"
    )
    if mine:
        text += (
            f"\nYou've put in {fmt_ks(mine)} so far — add more?\n"
        )
    text += (
        "\nHow much do you want to put in? Minimum "
        f"{fmt_ks(POOL_MIN_CONTRIB_KS)} — tap Join and send the "
        "amount in Ks. If less is left than you offer, only what's "
        "needed is taken. When the total raised hits "
        f"{fmt_ks(price)}, the video is sent privately to everyone "
        "who paid — it is NEVER revealed in the group."
    )
    kb = {
        "inline_keyboard": [
            [
                {
                    "text": "🤝 Join",
                    "callback_data": f"pooljoinask:{pool['id']}",
                }
            ],
            [{"text": "💰 Top up balance", "callback_data": "topup"}],
        ]
    }
    send_message(chat_id, text, reply_markup=kb)


def send_pool_preview(chat_id, user_id, draft):
    """Show the seller exactly what will post: the cover photo
    UNBLURRED, the pool text, Post / Cancel buttons."""
    profile = get_profile(user_id)
    preview = {
        "seller_name": draft.get("seller_name", "Seller"),
        "age": (profile or {}).get("age"),
        "role": (profile or {}).get("role"),
        "seller": str(user_id),
        "product": draft.get("product"),
        "duration_min": draft.get("duration_min"),
        "contributors": [],
        "status": "live",
    }
    text = "This is what will post to the group:\n\n" + pool_card_text(
        preview
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": "✅ Post pool", "callback_data": "poolpost"},
                {"text": "❌ Cancel", "callback_data": "poolcancel"},
            ]
        ]
    }
    if draft.get("cover_file_id"):
        api(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": draft["cover_file_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        send_message(chat_id, text, reply_markup=kb)


def start_pool(chat_id, user_id, state, user=None):
    """Entry for /pool. Same gates as /sell (live profile, complete
    profile, group linked), then the seller picks a product and the
    pool flow starts. The price is typed by the seller
    (50,000–500,000 Ks)."""
    profile = _seller_ready(chat_id, user_id, state)
    if profile is None:
        return
    products = profile.get("products", {})
    if not products:
        send_message(
            chat_id,
            "Your profile has no products — update it with /profile "
            "first.",
        )
        return
    state.get("card_draft", {}).pop(str(user_id), None)
    state.get("auction_draft", {}).pop(str(user_id), None)
    state.setdefault("pool_draft", {})[str(user_id)] = {
        "step": "product",
        "seller_name": profile.get("name", "Seller"),
    }
    save_state(state)
    rows = [
        [
            {
                "text": f"{PRODUCTS.get(k, k)} — {fmt_ks(v)}",
                "callback_data": f"poolprod:{k}",
            }
        ]
        for k, v in products.items()
    ]
    send_message(
        chat_id,
        "🤝 What are you pooling? Pick a product from your profile.",
        reply_markup={"inline_keyboard": rows},
    )


def handle_pool_step(chat_id, user_id, text, state, user=None):
    """Text steps during the /pool flow. The price is typed after the
    product is picked (50,000–500,000 Ks); media is handled by
    handle_flow_media; this just answers stray text. Returns True if
    the message was consumed."""
    draft = (state.get("pool_draft") or {}).get(str(user_id))
    if not draft:
        return False
    step = draft.get("step")
    if step == "product":
        send_message(
            chat_id, "Tap a product above to pick it — or /cancel to stop."
        )
        return True
    if step == "price":
        price = parse_pool_price(text)
        if price is None:
            send_message(
                chat_id,
                "Set the pool price as a whole number in Ks, between "
                f"{fmt_ks(POOL_MIN_PRICE_KS)} and "
                f"{fmt_ks(POOL_MAX_PRICE_KS)} — or /cancel to stop.",
            )
            return True
        draft["price"] = price
        draft["step"] = "video"
        save_state(state)
        send_message(
            chat_id,
            f"🤝 Pool for {PRODUCTS.get(draft.get('product'), draft.get('product', ''))} — "
            f"price {fmt_ks(price)} — send the video now (1 to 5 "
            "minutes).\n\n"
            "When the total raised hits "
            f"{fmt_ks(price)}, the video goes privately to everyone "
            "who paid — it is NEVER revealed in the group. The cover "
            "photo is the video's own thumbnail, unblurred.\n\n"
            "Or /cancel.",
        )
        return True
    if step == "video":
        send_message(
            chat_id,
            "Send the pool video now (1 to 5 minutes) — or /cancel "
            "to stop.",
        )
        return True
    if step == "cover":
        send_message(
            chat_id, "Send a cover photo for the video — or /cancel to stop."
        )
        return True
    return False


# ------------------------------------------------------ /sell cards ----

MAX_CARD_OPTIONS = 4


def start_sell(chat_id, user_id, state, user=None):
    """Entry for /sell (and the 'Post to group' button). Any member
    with a LIVE profile can post — no approval, no Zoom class needed.
    The group must be linked, or the seller is told plainly."""
    profile = _seller_ready(chat_id, user_id, state)
    if profile is None:
        return
    products = profile.get("products", {})
    if not products:
        send_message(
            chat_id,
            "Your profile has no products — update it with /profile "
            "first.",
        )
        return
    state.get("auction_draft", {}).pop(str(user_id), None)
    state.get("pool_draft", {}).pop(str(user_id), None)
    state.setdefault("card_draft", {})[str(user_id)] = {
        "step": "product",
        "seller_name": profile.get("name", "Seller"),
    }
    save_state(state)
    rows = [
        [
            {
                "text": f"{PRODUCTS.get(k, k)} — {fmt_ks(v)}",
                "callback_data": f"sellprod:{k}",
            }
        ]
        for k, v in products.items()
    ]
    send_message(
        chat_id,
        "What are you posting to the group? Pick a product from "
        "your profile.",
        reply_markup={"inline_keyboard": rows},
    )


def send_optname_prompt(chat_id, draft, profile):
    """Ask the seller to name the first option of a fixed-price card
    (or take the profile price with one tap)."""
    key = draft.get("product")
    price = (profile.get("products") or {}).get(key)
    send_message(
        chat_id,
        f"Name your first option for {PRODUCTS.get(key, key)} — e.g. "
        "A, B, C, D, or a size or flavour.\n\n"
        f"Or post it at your profile price ({fmt_ks(price)}) with "
        "one tap below.",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": f"Use profile price — {fmt_ks(price)}",
                        "callback_data": "sellprof",
                    }
                ]
            ]
        },
    )


def card_options_done(chat_id, user_id, draft, state):
    """Options are set — ask for the product photo/video (or skip)."""
    draft["step"] = "media"
    save_state(state)
    send_message(
        chat_id,
        "Last step: send the product photo or video (the full "
        "version — buyers only see a blurred sneak peek until "
        "someone buys it).\n\n"
        "Send a photo or a video now, or /skip for a text-only card.",
    )


def send_sell_preview(chat_id, user_id, draft):
    """Show the seller exactly what will post to the group, with
    Post / Cancel buttons. With media, the preview is the blurred
    sneak peek photo — blurred once here and stored on the draft so
    the group card can reuse it."""
    profile = get_profile(user_id)
    card = {
        "seller_name": draft.get("seller_name", "Seller"),
        "age": (profile or {}).get("age"),
        "role": (profile or {}).get("role"),
        "product": draft.get("product"),
        "options": draft.get("options", []),
        "media_type": draft.get("media_type"),
    }
    text = "This is what will post to the group:\n\n" + sell_card_text(card)
    kb = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Post to group",
                    "callback_data": "sellpost",
                },
                {
                    "text": "❌ Cancel",
                    "callback_data": "sellcancel",
                },
            ]
        ]
    }
    if draft.get("preview_source_file_id") and not draft.get(
        "preview_file_id"
    ):
        blurred = blur_photo_file_id(draft["preview_source_file_id"])
        if blurred:
            r = send_photo_file(
                chat_id, "preview.jpg", blurred, caption=text,
                reply_markup=kb,
            )
            if r.get("ok"):
                draft["preview_file_id"] = r["result"]["photo"][-1][
                    "file_id"
                ]
                return
    if draft.get("preview_file_id"):
        api(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": draft["preview_file_id"],
                "caption": text,
                "reply_markup": kb,
            },
        )
    else:
        send_message(chat_id, text, reply_markup=kb)


def handle_card_step(chat_id, user_id, text, state, user=None):
    """One step of the guided /sell flow. Returns True if the message
    was consumed by the flow."""
    draft = (state.get("card_draft") or {}).get(str(user_id))
    if not draft:
        return False
    step = draft.get("step")

    if step == "product":
        send_message(
            chat_id,
            "Tap a product above to pick it — or /cancel to stop.",
        )
        return True

    if step == "optname":
        if text == "/done":
            if draft.get("options"):
                card_options_done(chat_id, user_id, draft, state)
            else:
                send_message(
                    chat_id,
                    "Name at least one option first — e.g. A, B, C, D, "
                    "or a size or flavour.",
                )
            return True
        name = (text or "").strip()
        if len(name) < 1 or len(name) > 30:
            send_message(
                chat_id,
                "Option names are 1–30 characters — try again, or "
                "/cancel.",
            )
            return True
        draft["opt_name"] = name
        draft["step"] = "optprice"
        save_state(state)
        send_message(
            chat_id,
            f"Price for “{name}” in Ks "
            f"({PRICE_MIN_KS:,}–{PRICE_MAX_KS:,}):",
        )
        return True

    if step == "optprice":
        price = parse_price_ks(text)
        if price is None:
            send_message(
                chat_id,
                f"Price must be a whole number from "
                f"{PRICE_MIN_KS:,} to {PRICE_MAX_KS:,} Ks — try again for "
                f"“{draft.get('opt_name')}”.",
            )
            return True
        draft.setdefault("options", []).append(
            {"name": draft["opt_name"], "price": price}
        )
        draft.pop("opt_name", None)
        if len(draft["options"]) >= MAX_CARD_OPTIONS:
            card_options_done(chat_id, user_id, draft, state)
            return True
        draft["step"] = "optname"
        save_state(state)
        added = draft["options"][-1]
        send_message(
            chat_id,
            f"Added: {added['name']} — {fmt_ks(price)} "
            f"({len(draft['options'])}/{MAX_CARD_OPTIONS} options).\n\n"
            f"Name option {len(draft['options']) + 1}, or tap Done to "
            "preview the card.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Done — preview",
                            "callback_data": "selldone",
                        }
                    ]
                ]
            },
        )
        return True

    if step == "media":
        if text == "/skip":
            draft["step"] = "confirm"
            save_state(state)
            send_sell_preview(chat_id, user_id, draft)
            return True
        send_message(
            chat_id,
            "Send the product photo or video, or /skip for a "
            "text-only card.",
        )
        return True

    if step == "preview_photo":
        send_message(
            chat_id,
            "Send a preview photo for the video — this is the sneak "
            "peek everyone sees in the group.",
        )
        return True
    return False


# ------------------------------------------------- cash-out + sell USDT ----


def cashout_usdt_for_ks(ks):
    """Whole USDT a Ks amount cashes out to at the 4,500 rate, rounded
    down. Any leftover Ks stays in the balance. (The 5,000 pricing
    anchor is NOT used here.)"""
    return int(ks) // KS_PER_USDT_CASHOUT


def record_cashout(user_id, username, ks, usdt, address, status,
                   method=None):
    event = {
        "kind": "cashout",
        "user": str(user_id),
        "username": username or "",
        "ks": ks,
        "usdt": usdt,
        "address": address or "",
        "status": status,
        "ts": int(time.time()),
    }
    if method:
        event["method"] = method
    record_event(event)


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
    """Pick a cash-out method first — USDT or Myanmar payment."""
    balance = get_balance(user_id)
    if balance < CASHOUT_MIN_KS:
        send_message(
            chat_id,
            f"💸 Cash out your balance — 1 USDT = "
            f"{CASHOUT_MIN_KS:,} Ks.\n\n"
            f"Your balance is {fmt_ks(balance)} — you need at least "
            f"{fmt_ks(CASHOUT_MIN_KS)} (1 USDT) to cash out.\n\n"
            "Top up with /topup, or earn balance by selling in the market.",
        )
        return
    send_message(
        chat_id,
        f"💸 Cash out — your balance is {fmt_ks(balance)}.\n\n"
        "How do you want to be paid?\n"
        f"💵 USDT — 1 USDT = {CASHOUT_MIN_KS:,} Ks, minimum "
        f"{fmt_ks(CASHOUT_MIN_KS)} (whole USDT only).\n"
        "🇲🇲 KBZPay / WavePay / AYAPay — paid in Ks to your own "
        f"account, 1:1, minimum {fmt_ks(CASHOUT_MM_MIN_KS)}.\n\n"
        "Pick one below, or /cancel.",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "💵 USDT",
                        "callback_data": "cashout_usdt",
                    }
                ],
                [
                    {
                        "text": "🇲🇲 KBZPay / WavePay / AYAPay",
                        "callback_data": "cashout_mm",
                    }
                ],
            ]
        },
    )


def start_cashout_usdt(chat_id, user_id, state):
    """USDT leg of /cashout — unchanged from v3: whole USDT only at
    1 USDT = 4,500 Ks, leftovers stay in the balance."""
    balance = get_balance(user_id)
    if balance < CASHOUT_MIN_KS:
        send_message(
            chat_id,
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


def start_cashout_mm(chat_id, user_id, state):
    """Myanmar leg of /cashout — the admin sends the Ks to the
    member's own KBZPay / WavePay / AYAPay account, 1:1, minimum
    5,000 Ks. Saved profile accounts are offered as buttons; a
    member with none types the service and number instead."""
    balance = get_balance(user_id)
    if balance < CASHOUT_MM_MIN_KS:
        send_message(
            chat_id,
            f"🇲🇲 Cash out by KBZPay / WavePay / AYAPay needs at "
            f"least {fmt_ks(CASHOUT_MM_MIN_KS)} — your balance is "
            f"{fmt_ks(balance)}.\n\n"
            f"USDT cash-out needs only {fmt_ks(CASHOUT_MIN_KS)} — tap "
            "/cashout and pick USDT, or top up with /topup.",
        )
        return
    profile = get_profile(user_id)
    pay = (profile or {}).get("pay", {}) or {}
    saved = []
    for key, label in (
        ("kbz", "KBZPay"),
        ("wave", "WavePay"),
        ("aya", "AYAPay"),
    ):
        number = pay.get(key)
        if number:
            saved.append((key, label, number))
    state.setdefault("cashout_mm_draft", {})[str(user_id)] = {
        "step": "account",
    }
    save_state(state)
    if saved:
        rows = [
            [
                {
                    "text": f"{label} {mask_mm_number(number)}",
                    "callback_data": f"coacc:{key}",
                }
            ]
            for key, label, number in saved
        ]
        rows.append(
            [
                {
                    "text": "⌨️ Type a different number",
                    "callback_data": "coacc:other",
                }
            ]
        )
        send_message(
            chat_id,
            "🇲🇲 Cash out to your KBZPay / WavePay / AYAPay account — "
            f"1:1 in Ks, minimum {fmt_ks(CASHOUT_MM_MIN_KS)}.\n\n"
            "Which account should the admin pay to?",
            reply_markup={"inline_keyboard": rows},
        )
    else:
        send_message(
            chat_id,
            "🇲🇲 Cash out to your KBZPay / WavePay / AYAPay account — "
            f"1:1 in Ks, minimum {fmt_ks(CASHOUT_MM_MIN_KS)}.\n\n"
            "You have no Myanmar account on your profile. Type the "
            "service and number, e.g. \"KBZPay 09403720481\".\n\n"
            "Or /cancel.",
        )


def ask_cashout_mm_amount(chat_id, user_id, draft):
    """Prompt for the Myanmar cash-out amount once the account is
    known (saved button or typed)."""
    balance = get_balance(user_id)
    send_message(
        chat_id,
        f"Cashing out to your {draft['service']} "
        f"<code>{html.escape(draft['account'])}</code> — 1:1 in Ks, "
        "no conversion.\n\n"
        f"How many Ks? Your balance is {fmt_ks(balance)} "
        f"(minimum {fmt_ks(CASHOUT_MM_MIN_KS)}).\n\n"
        "Or /cancel.",
        parse_mode="HTML",
    )


def handle_cashout_mm_step(chat_id, user_id, text, state, user=None):
    """One step of the guided Myanmar cash-out flow. Returns True if
    the message was consumed by the flow."""
    draft = (state.get("cashout_mm_draft") or {}).get(str(user_id))
    if not draft:
        return False
    step = draft.get("step")

    if step == "account":
        parsed = parse_mm_account(text)
        if not parsed:
            send_message(
                chat_id,
                "Send the service and number, e.g. \"KBZPay "
                "09403720481\" or \"WavePay 09780695959\", or /cancel.",
            )
            return True
        service, account = parsed
        draft.update(
            {"step": "amount", "service": service, "account": account}
        )
        save_state(state)
        ask_cashout_mm_amount(chat_id, user_id, draft)
        return True

    if step == "amount":
        cleaned = (text or "").replace(",", "").replace(" ", "").strip()
        if not cleaned.isdigit():
            send_message(
                chat_id,
                "Send the amount in Ks as a number (e.g. 10000), "
                "or /cancel.",
            )
            return True
        amount = int(cleaned)
        balance = get_balance(user_id)
        if amount < CASHOUT_MM_MIN_KS:
            send_message(
                chat_id,
                f"Minimum Myanmar cash-out is "
                f"{fmt_ks(CASHOUT_MM_MIN_KS)} — send a bigger amount, "
                "or /cancel.",
            )
            return True
        if amount > balance:
            send_message(
                chat_id,
                f"That's more than your balance ({fmt_ks(balance)}) — "
                "send a smaller amount, or /cancel.",
            )
            return True
        service = draft["service"]
        account = draft["account"]
        state["cashout_seq"] = state.get("cashout_seq", 0) + 1
        cid = f"co{state['cashout_seq']}"
        state.setdefault("cashouts", {})[cid] = {
            "id": cid,
            "user": str(user_id),
            "username": (user or {}).get("username", ""),
            "method": "mm",
            "service": service,
            "account": account,
            "ks": amount,
            "usdt": 0,
            "address": "",
            "status": "pending",
            "ts": int(time.time()),
        }
        state.get("cashout_mm_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(
            chat_id,
            f"✅ Cash-out request sent — {fmt_ks(amount)} to your "
            f"{service} <code>{html.escape(account)}</code>.\n"
            "An admin will send the Ks and confirm it here. I'll tell "
            "you when it's paid.",
            parse_mode="HTML",
        )
        for admin_id in sorted(ADMIN_IDS):
            send_message(
                admin_id,
                f"💸 Myanmar cash-out request {cid} from "
                f"{user_tag(user)}:\n\n"
                f"• {fmt_ks(amount)} → {service} "
                f"<code>{html.escape(account)}</code>\n"
                f"• Balance now: {fmt_ks(get_balance(user_id))}\n\n"
                "Approve ONLY after you have sent the Ks to that "
                "account — approving debits the member's balance.",
                parse_mode="HTML",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Paid — Ks sent",
                                "callback_data": f"cmmok:{cid}",
                            },
                            {
                                "text": "❌ Decline",
                                "callback_data": f"cmmno:{cid}",
                            },
                        ]
                    ]
                },
            )
        return True
    return False


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


def send_role_prompt(chat_id, keep=False):
    text = "What's your role? Tap one, or type your own (1–30 characters)."
    if keep:
        text += " Or /skip to keep it."
    send_message(
        chat_id,
        text,
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": "Top", "callback_data": "role:Top"},
                    {"text": "Bottom", "callback_data": "role:Bottom"},
                    {"text": "Verse", "callback_data": "role:Verse"},
                ],
                [
                    {
                        "text": "Something else…",
                        "callback_data": "role:other",
                    }
                ],
            ]
        },
    )


def profile_after_role(chat_id, draft, data, state, username):
    """After the role is set: a short 'complete your profile' flow
    jumps straight to photos (or confirm); the full flow goes on to
    products."""
    if draft.get("complete"):
        if len(data.get("photos") or []) < 3:
            draft["step"] = "photos"
            save_state(state)
            send_message(
                chat_id,
                f"Send {3 - len(data.get('photos') or [])} photo(s) of "
                "you, one by one — 3 are required to sell.",
            )
        else:
            draft["step"] = "confirm"
            save_state(state)
            send_profile_confirm(chat_id, data, username)
    else:
        draft["step"] = "products"
        save_state(state)
        send_message(
            chat_id,
            "What do you sell? Tap each product you offer, then Done.",
            reply_markup=profile_draft_keyboard(draft),
        )


def start_profile_completion(chat_id, user_id, state):
    """Short flow for a live seller whose profile is missing age,
    role or photos (needed before /sell). Walks only the missing
    pieces, then confirms."""
    profile = get_profile(user_id)
    if not profile:
        return
    missing = profile_missing_fields(profile)
    data = {
        "name": profile.get("name", ""),
        "age": profile.get("age"),
        "role": profile.get("role"),
        "photos": list(profile.get("photos") or []),
        "products": dict(profile.get("products", {})),
        "pay": dict(profile.get("pay", {})),
    }
    step = (
        "age"
        if "age" in missing
        else "role" if "role" in missing else "photos"
    )
    state.setdefault("profile_draft", {})[str(chat_id)] = {
        "step": step,
        "data": data,
        "editing": True,
        "complete": True,
    }
    save_state(state)
    bits = []
    if "age" in missing:
        bits.append("your age")
    if "role" in missing:
        bits.append("your role")
    if "photos" in missing:
        bits.append(
            f"{3 - len(data['photos'])} photo(s) of you"
        )
    intro = (
        "Before you post, finish your profile — I still need "
        + " and ".join(bits)
        + ".\n\n"
    )
    if step == "age":
        send_message(
            chat_id, intro + "How old are you? Send your age as a number."
        )
    elif step == "role":
        send_message(chat_id, intro + "What's your role?")
        send_role_prompt(chat_id)
    else:
        send_message(
            chat_id,
            intro + "Send 3 photos of you, one by one — they're "
            "required to sell.",
        )


def start_profile(chat_id, user, state):
    existing = get_profile(chat_id)
    # A removed profile starts fresh — the seller makes a new one.
    if existing and existing.get("status") == "removed":
        existing = None
    data = {}
    if existing:
        data = {
            "name": existing.get("name", ""),
            "age": existing.get("age"),
            "role": existing.get("role"),
            "photos": list(existing.get("photos") or []),
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
    if data.get("photos"):
        send_photos_group(chat_id, data["photos"])
    text = "Check your profile:\n\n" + profile_summary_text(
        {
            "name": data.get("name", ""),
            "username": username,
            "age": data.get("age"),
            "role": data.get("role"),
            "products": data.get("products", {}),
            "pay": data.get("pay", {}),
        }
    )
    text += (
        "\n\nYour profile goes live straight away — other members can "
        "find you and buy your products."
    )
    send_message(
        chat_id,
        text,
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Make my profile live",
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
        draft["step"] = "age"
        save_state(state)
        send_message(
            chat_id,
            "How old are you? Send your age as a number.",
        )
        return True

    if step == "age":
        if text == "/skip":
            if not draft.get("editing") or not data.get("age"):
                send_message(chat_id, "Please send your age first (a number).")
                return True
        else:
            if not text.isdigit() or not (1 <= int(text) <= 120):
                send_message(
                    chat_id, "Your age as a number, please — e.g. 25."
                )
                return True
            data["age"] = int(text)
        draft["step"] = "role"
        save_state(state)
        send_role_prompt(chat_id, keep=bool(draft.get("editing")))
        return True

    if step == "role":
        if text == "/skip":
            if not draft.get("editing") or not data.get("role"):
                send_message(
                    chat_id, "Tap a role below, or type your own."
                )
                return True
        elif len(text) < 1 or len(text) > 30:
            send_message(
                chat_id,
                "Role is 1–30 characters — tap a button or type it.",
            )
            return True
        else:
            data["role"] = text.strip()
        profile_after_role(chat_id, draft, data, state, username)
        return True

    if step == "role_text":
        if len(text) < 1 or len(text) > 30:
            send_message(
                chat_id, "Role is 1–30 characters — try again, or /cancel."
            )
            return True
        data["role"] = text.strip()
        profile_after_role(chat_id, draft, data, state, username)
        return True

    if step == "photos":
        if text == "/skip":
            photos = data.get("photos", [])
            if len(photos) >= 3:
                draft["step"] = "confirm"
                save_state(state)
                send_profile_confirm(chat_id, data, username)
            else:
                send_message(
                    chat_id,
                    f"Photos are required to sell — send "
                    f"{3 - len(photos)} more photo(s) of you, or /cancel.",
                )
            return True
        send_message(
            chat_id,
            "Send a photo of you — I need 3 in total, one by one.",
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
                draft["step"] = "photos"
                save_state(state)
                photos = data.get("photos", [])
                if photos:
                    if len(photos) >= 3:
                        send_message(
                            chat_id,
                            "You already have 3 photos saved — /skip to "
                            "keep them, or send new ones to swap them.",
                        )
                    else:
                        send_message(
                            chat_id,
                            f"You have {len(photos)} photo(s) saved — "
                            f"send {3 - len(photos)} more photo(s) of "
                            "you, one by one. 3 are required to sell.",
                        )
                else:
                    send_message(
                        chat_id,
                        "Last step: send 3 photos of you, one by one — "
                        "they're required to sell.",
                    )
        return True

    if step == "confirm":
        send_message(
            chat_id,
            "Tap below to make your profile live, "
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


def handle_successful_payment(chat_id, user_id, sp, user=None,
                              state=None):
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
        # 5 parts: mkt:<seller>:<product>:<price>:<user> (profile buy)
        # 7 parts: + :<card_id>:<opt_idx> (card option buy)
        if len(parts) not in (5, 7) or parts[4] != str(user_id):
            return
        seller_id, product, price_s = parts[1], parts[2], parts[3]
        try:
            price = int(price_s)
        except ValueError:
            return
        option = None
        card_id = None
        if len(parts) == 7:
            card_id = parts[5]
            st = state if state is not None else load_state()
            card = st.get("cards", {}).get(card_id)
            if card and card.get("status") == "live":
                try:
                    option = card["options"][int(parts[6])]["name"]
                except (ValueError, IndexError, KeyError, TypeError):
                    option = None
        profile = get_profile(seller_id)
        if not profile or profile.get("status") != "live":
            send_message(
                user_id,
                "That seller is not live any more — the Stars were "
                "charged, so please message @SirArkar and we'll sort it out.",
            )
            return
        seller_name = profile.get("name", "Seller")
        item = market_item_label(product, option)
        change_balance(seller_id, price)
        record_market_sale(
            user_id, username, seller_id, seller_name, product, price,
            "Stars", "paid", option=option,
        )
        if card_id is not None:
            st = state if state is not None else load_state()
            reveal_card_purchase(
                st, card_id, option,
                (user or {}).get("first_name") or "Someone",
            )
        seller_total = get_balance(seller_id)
        send_message(
            user_id,
            f"✅ Paid {fmt_ks(price)} with Stars for "
            f"{item} from {seller_name}.",
        )
        send_message(
            seller_id,
            f"💰 {user_tag(user)} bought your "
            f"{item} for {fmt_ks(price)} (Stars).\n"
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
        option = pending.get("option")
        item = market_item_label(product, option)
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
                f"{item} for {fmt_ks(price)} (USDT).\n"
                "Credited to your bot balance — now "
                f"{fmt_ks(get_balance(seller_id))}.",
            )
        else:
            send_message(
                seller_id,
                f"💰 {user_tag(user)} paid you {fmt_ks(price)} in USDT for "
                f"{item} (direct, verified on-chain).",
            )
        record_market_sale(
            user_id, username, seller_id, seller_name, product, price,
            method, "paid", tx_hash, option=option,
        )
        if pending.get("card"):
            reveal_card_purchase(
                state, pending["card"], option,
                (user or {}).get("first_name") or "Someone",
            )
        send_message(
            user_id,
            f"✅ USDT confirmed on-chain — you bought "
            f"{item} for {fmt_ks(price)} from "
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


def forward_receipt_to_admins(user_id, user, key, message_id, state, market=None, topup=None):
    """Forward the receipt photo with Approve / Decline buttons. For a
    class pack it goes to every admin; for a marketplace sale it also
    goes to the seller, and the seller or an admin may confirm it.
    For a Myanmar balance top-up it goes to every admin only.
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
                "option": market.get("option", ""),
                "price_ks": market["price_ks"],
                "method": market.get("method", "Myanmar pay"),
                "card": market.get("card"),
                "buyer_name": (user or {}).get("first_name", ""),
            }
        )
        note = (
            f"📸 Receipt from {user_tag(user)} — buying your "
            f"{market_item_label(market['product'], market.get('option'))} for "
            f"{fmt_ks(market['price_ks'])} via "
            f"{market.get('method', 'Myanmar pay')}.\n"
            "Tap to confirm the payment, or decline."
        )
        button = "✅ Confirm payment"
        targets = [str(market["seller"])] + [
            a for a in sorted(ADMIN_IDS) if a != str(market["seller"])
        ]
    elif topup:
        entry.update(
            {
                "kind": "topup_mm",
                "ks": int(topup["ks"]),
            }
        )
        note = (
            f"💰 Balance top-up receipt from {user_tag(user)} — "
            f"{fmt_ks(int(topup['ks']))}.\n"
            "Tap to credit the member's balance, or decline."
        )
        button = "✅ Approve — credit balance"
        targets = sorted(ADMIN_IDS)
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


def handle_flow_media(msg, state):
    """Photos/videos that belong to a guided flow (profile photos,
    card media, card preview photo). Returns True if consumed — the
    message must NOT fall through to receipt handling."""
    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id")
    photo = msg.get("photo")
    video = msg.get("video")
    document = msg.get("document")
    if not photo and not video:
        # A video sent as a file during an auction or a pool: nudge
        # the seller to send it as a video instead — otherwise it
        # silently falls through and nothing happens.
        if document:
            adraft = (state.get("auction_draft") or {}).get(str(user_id))
            pdraft = (state.get("pool_draft") or {}).get(str(user_id))
            draft = adraft if adraft and adraft.get("step") == "video" else (
                pdraft if pdraft and pdraft.get("step") == "video" else None
            )
            if draft:
                send_message(
                    chat_id,
                    "That came through as a file — send it as a video "
                    "instead (tap the video, not 'Send as file').",
                )
                return True
        return False

    # ---- profile photos (3 required) ----
    pdraft = (state.get("profile_draft") or {}).get(str(user_id))
    if pdraft and pdraft.get("step") == "photos":
        if video:
            send_message(
                chat_id,
                "That was a video — I need a photo of you. Send a photo.",
            )
            return True
        fid = photo[-1]["file_id"]
        data = pdraft.setdefault("data", {})
        photos = data.setdefault("photos", [])
        if len(photos) >= 3:
            # Already has 3 — a new photo swaps the oldest one out.
            photos.pop(0)
            photos.append(fid)
            save_state(state)
            send_message(
                chat_id,
                "Photo updated — you still have 3. Send /skip to "
                "finish, or keep sending to swap more.",
            )
            return True
        photos.append(fid)
        save_state(state)
        if len(photos) < 3:
            send_message(
                chat_id,
                f"Photo {len(photos)}/3 saved — send {3 - len(photos)} "
                "more.",
            )
        else:
            pdraft["step"] = "confirm"
            save_state(state)
            send_profile_confirm(
                chat_id, data,
                (msg.get("from", {}) or {}).get("username", ""),
            )
        return True

    # ---- card media / preview photo ----
    cdraft = (state.get("card_draft") or {}).get(str(user_id))
    if cdraft and cdraft.get("step") == "media":
        if photo:
            cdraft["media_type"] = "photo"
            cdraft["media_file_id"] = photo[-1]["file_id"]
            cdraft["preview_source_file_id"] = photo[-1]["file_id"]
            cdraft["step"] = "confirm"
            save_state(state)
            send_sell_preview(chat_id, user_id, cdraft)
        elif video:
            cdraft["media_type"] = "video"
            cdraft["media_file_id"] = video["file_id"]
            cdraft["step"] = "preview_photo"
            save_state(state)
            send_message(
                chat_id,
                "Got the video. Now send a preview photo for it — "
                "this is the blurred sneak peek everyone sees in the "
                "group until someone buys it.",
            )
        return True
    if cdraft and cdraft.get("step") == "preview_photo":
        if video:
            send_message(
                chat_id,
                "That was a video — the preview needs to be a photo. "
                "Send a preview photo.",
            )
            return True
        if photo:
            cdraft["preview_source_file_id"] = photo[-1]["file_id"]
            cdraft["step"] = "confirm"
            save_state(state)
            send_sell_preview(chat_id, user_id, cdraft)
            return True

    # ---- auction video / cover photo ----
    adraft = (state.get("auction_draft") or {}).get(str(user_id))
    if adraft and adraft.get("step") == "video":
        if photo:
            send_message(
                chat_id,
                "Auctions are for videos — send a video for the auction.",
            )
            return True
        if video:
            dur = video.get("duration")
            if dur is not None and (
                dur < AUCTION_MIN_VIDEO_S or dur > AUCTION_MAX_VIDEO_S
            ):
                send_message(
                    chat_id,
                    f"That video is {dur // 60} min {dur % 60:02d} s — "
                    "auction videos must be 1 to 5 minutes. Send "
                    "another video.",
                )
                return True
            adraft["video_file_id"] = video["file_id"]
            if dur is not None:
                adraft["duration_s"] = dur
                adraft["duration_min"] = max(1, dur // 60)
            thumb = video.get("thumb") or {}
            if thumb.get("file_id"):
                adraft["cover_file_id"] = thumb["file_id"]
                adraft["step"] = "confirm"
                save_state(state)
                send_auction_preview(chat_id, user_id, adraft)
            else:
                adraft["step"] = "cover"
                save_state(state)
                send_message(
                    chat_id,
                    "Got the video — it has no cover photo, so send "
                    "one now (this is the unblurred cover everyone "
                    "sees on the auction card).",
                )
            return True
    if adraft and adraft.get("step") == "cover":
        if video:
            send_message(
                chat_id,
                "That was a video — the cover needs to be a photo. "
                "Send a cover photo.",
            )
            return True
        if photo:
            adraft["cover_file_id"] = photo[-1]["file_id"]
            adraft["step"] = "confirm"
            save_state(state)
            send_auction_preview(chat_id, user_id, adraft)
            return True

    # ---- pool video / cover photo (same 1–5 min rule as auctions) ----
    pdraft = (state.get("pool_draft") or {}).get(str(user_id))
    if pdraft and pdraft.get("step") == "video":
        if photo:
            send_message(
                chat_id,
                "Pools are for videos — send a video for the pool.",
            )
            return True
        if video:
            dur = video.get("duration")
            if dur is not None and (
                dur < AUCTION_MIN_VIDEO_S or dur > AUCTION_MAX_VIDEO_S
            ):
                send_message(
                    chat_id,
                    f"That video is {dur // 60} min {dur % 60:02d} s — "
                    "pool videos must be 1 to 5 minutes. Send "
                    "another video.",
                )
                return True
            pdraft["video_file_id"] = video["file_id"]
            if dur is not None:
                pdraft["duration_s"] = dur
                pdraft["duration_min"] = max(1, dur // 60)
            thumb = video.get("thumb") or {}
            if thumb.get("file_id"):
                pdraft["cover_file_id"] = thumb["file_id"]
                pdraft["step"] = "confirm"
                save_state(state)
                send_pool_preview(chat_id, user_id, pdraft)
            else:
                pdraft["step"] = "cover"
                save_state(state)
                send_message(
                    chat_id,
                    "Got the video — it has no cover photo, so send "
                    "one now (this is the unblurred cover everyone "
                    "sees on the pool card).",
                )
            return True
    if pdraft and pdraft.get("step") == "cover":
        if video:
            send_message(
                chat_id,
                "That was a video — the cover needs to be a photo. "
                "Send a cover photo.",
            )
            return True
        if photo:
            pdraft["cover_file_id"] = photo[-1]["file_id"]
            pdraft["step"] = "confirm"
            save_state(state)
            send_pool_preview(chat_id, user_id, pdraft)
            return True
    return False


def handle_topup_mm_step(chat_id, user_id, text, state, user=None):
    """Typed amount during a Myanmar top-up. A valid amount stores a
    `topup_mm` pending receipt (the member then pays and sends the
    receipt photo); anything below 5,000 Ks or not a number is
    rejected and the draft stays open. Returns True if consumed."""
    draft = (state.get("topup_mm_draft") or {}).get(str(user_id))
    if not draft:
        return False
    cleaned = (text or "").replace(",", "").replace(" ", "").strip()
    if not cleaned.isdigit():
        send_message(
            chat_id,
            "Send the amount as a whole number in Ks, or /cancel.",
        )
        return True
    amount = int(cleaned)
    if amount < TOPUP_MM_MIN_KS:
        send_message(
            chat_id,
            f"Minimum top-up is {fmt_ks(TOPUP_MM_MIN_KS)} — type a bigger "
            "amount, or /cancel.",
        )
        return True
    state.get("topup_mm_draft", {}).pop(str(user_id), None)
    state.setdefault("pending_mm", {})[str(user_id)] = {
        "kind": "topup_mm",
        "ks": amount,
    }
    save_state(state)
    send_message(
        chat_id,
        f"Pay {fmt_ks(amount)} to one of these, then send your receipt "
        "screenshot HERE:\n\n" + mm_admin_numbers_text(),
        parse_mode="HTML",
    )
    return True


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
    elif pending.get("kind") == "topup_mm":
        forward_receipt_to_admins(
            user_id, msg.get("from", {}), None, msg["message_id"], state,
            topup=pending,
        )
    else:
        forward_receipt_to_admins(
            user_id, msg.get("from", {}), pending["pack"], msg["message_id"],
            state,
        )
    if pending.get("kind") == "topup_mm":
        send_message(
            chat_id,
            "Receipt sent — an admin will check it and credit your "
            "balance. 🙏",
        )
    else:
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
        send_seller_card(chat_id, profile)
        return

    if arg.startswith("card_"):
        rest = arg[len("card_"):]
        if "_" not in rest:
            send_message(chat_id, "That card is gone — check the group for the latest one.")
            return
        card_id, idx_s = rest.rsplit("_", 1)
        card = (state.get("cards") or {}).get(card_id)
        if not card or card.get("status") != "live":
            send_message(
                chat_id,
                "That card is gone — check the group for the latest one.",
            )
            return
        try:
            idx = int(idx_s)
            opt = card["options"][idx]
        except (ValueError, IndexError, KeyError, TypeError):
            send_message(
                chat_id,
                "That option is gone — check the group for the latest card.",
            )
            return
        profile = get_profile(card["seller"])
        if not profile or profile.get("status") != "live":
            send_message(chat_id, "That seller is not live right now.")
            return
        if str(chat_id) == str(card["seller"]):
            send_message(chat_id, "That's your own product.")
            return
        send_buy_options(
            chat_id, profile, card["product"], int(opt["price"]),
            option=opt["name"], card_id=card["id"], opt_idx=idx,
        )
        return

    if arg.startswith("auction_"):
        aid = arg[len("auction_"):]
        auction = (state.get("auctions") or {}).get(aid)
        if not auction or auction.get("status") != "live":
            send_message(
                chat_id,
                "That auction has ended — check the group for the latest one.",
            )
            return
        if int(time.time()) >= auction.get("ends_at", 0):
            send_message(
                chat_id,
                "That auction has ended — check the group for the latest one.",
            )
            return
        if str(chat_id) == str(auction.get("seller")):
            send_message(chat_id, "That's your own auction.")
            return
        send_bid_prompt(chat_id, auction)
        return

    if arg.startswith("poolinfo_"):
        pid = arg[len("poolinfo_"):]
        pool = (state.get("pools") or {}).get(pid)
        if not pool:
            send_message(chat_id, "That pool is gone.")
            return
        send_pool_info(chat_id, pool)
        return

    if arg.startswith("pool_"):
        pid = arg[len("pool_"):]
        pool = (state.get("pools") or {}).get(pid)
        if not pool or pool.get("status") != "live":
            send_message(
                chat_id,
                "That pool is closed — check the group for the latest one.",
            )
            return
        if str(chat_id) == str(pool.get("seller")):
            send_message(chat_id, "That's your own pool.")
            return
        send_join_prompt(chat_id, pool)
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
        "peaches, donut, HD). Make your seller profile with /profile "
        "— age, role and 3 photos of you, then it goes live straight "
        "away. Post a card to the group with /sell — name your own "
        "options (A, B, C, D) with your own prices and a product "
        "photo or video. Cards show only a blurred sneak peek; the "
        "full version is revealed in the group when someone buys it. "
        "🔨 Or run an auction with /auction — starting bid 5,000 Ks, "
        "15 minutes, highest bidder wins the video privately. "
        "🤝 Or run a pool with /pool — a video at a price you set "
        "(50,000–500,000 Ks); everyone puts in 1,000 Ks or more, and "
        "when the total raised hits your price the video goes "
        "privately to everyone who paid. "
        "Browse with /sellers, check your balance with /balance. "
        "Top up with /topup — Stars, USDT, or KBZPay / WavePay / "
        "AYAPay (from 5,000 Ks).\n\n"
        "💸 Cash out your balance with /cashout — as USDT "
        "(1 USDT = 4,500 Ks) or straight to your KBZPay / WavePay / "
        "AYAPay in Ks (1:1, minimum 5,000 Ks). Or sell your "
        "USDT to Arkar with /sellusdt at 1 USDT = 4,500 Ks.",
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
        "/profile — age, role and 3 photos of you, then it goes live "
        "straight away, no approval needed. "
        "Post a product card to the group with /sell: name your own "
        "options (A, B, C, D) with your own prices, up to 4 per card, "
        "and add a product photo or video. The card shows only a "
        "blurred sneak peek; the full version is revealed in the "
        "group when someone buys it. "
        "Or run a video auction with /auction: starting bid 5,000 Ks, "
        "15 minutes, bids from your bot balance — highest bidder wins "
        "the video privately (an admin win is revealed in the group "
        "instead). Auction videos must be 1 to 5 minutes, and the card "
        "shows the length in minutes. The cover is the video's own "
        "thumbnail, unblurred. "
        "Unsold auction posts are deleted after 24 hours. "
        "Or run a group-buy pool with /pool: an expensive video at "
        "a price you set, 50,000–500,000 Ks — each person puts in "
        "1,000 Ks or more from their bot balance, as often as they "
        "like (every top-up adds to their running total, and the "
        "card shows each member's total under the meter). When the "
        "total raised hits your price the "
        "video goes privately to everyone who paid — it is NEVER "
        "revealed in the group. The last contribution is capped at "
        "exactly what's left, so the pool always totals exactly "
        "your price. The card shows a live money meter (Ks raised / "
        "your price) and how many people have joined. /poolinfo "
        "<pool id> shows the full contributor list. Pool videos "
        "must be 1 to 5 minutes, and the card shows the length in "
        "minutes. The cover is the video's own thumbnail, unblurred. "
        "No deadline — a pool stays open until it fills, or the "
        "seller removes it (everyone is refunded what they put in). "
        "Sellers earn a title from their sales — New Seller, Seller, "
        "Rising Star, Top Seller, Star Seller, Legend — shown with "
        "their sales count on their profile and every post. "
        "Buyers tap an option on the card and pay. Buyers pay from "
        "their bot balance, with Stars, with USDT, or directly to "
        "the seller (receipt photo or USDT hash). Top up with /topup "
        "— Stars, USDT, or KBZPay / WavePay / AYAPay (minimum 5,000 Ks "
        "for Myanmar pay).\n\n"
        "Admin:\n"
        "/newsession <topic> | <date/time> — post a session card\n"
        "/post <text> — announcement with pack buttons\n"
        "/announce — post an announcement to the group (tap to "
        "choose: main intro, fundraiser pool, or both)\n"
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
        "/sell — post a product card to the group\n"
        "/auction — post a video auction (start 5,000 Ks, 15 minutes)\n"
        "/pool — post a group-buy pool (price 50,000–500,000 Ks, "
        "1,000 Ks or more per person)\n"
        "/poolinfo <pool id> — full contributor list for a pool\n"
        "/sellers — live sellers\n"
        "/balance — your bot balance\n"
        "/topup — top up by Stars, USDT or KBZPay/WavePay/AYAPay (min 5,000 Ks)\n"
        "/cashout — cash out your balance: USDT (1 USDT = 4,500 Ks) "
        "or KBZPay / WavePay / AYAPay in Ks, 1:1 (min 5,000 Ks)\n"
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
        handle_successful_payment(
            chat_id, user_id, sp, user=msg.get("from", {}), state=state
        )
        return

    # Photos/videos for a guided flow (profile photos, card media)
    # are consumed by that flow — never treat them as receipts.
    # Documents are routed too, so a video sent as a file during an
    # auction gets the "send it as a video" nudge instead of silence.
    if msg.get("photo") or msg.get("video") or msg.get("document"):
        if handle_flow_media(msg, state):
            return

    if msg.get("photo") and not is_admin(chat_id):
        handle_receipt_photo(msg, state)
        return

    # ---- shared commands: everyone, admins included ----
    if text == "/cancel":
        state.get("profile_draft", {}).pop(str(user_id), None)
        state.get("cashout_draft", {}).pop(str(user_id), None)
        state.get("cashout_mm_draft", {}).pop(str(user_id), None)
        state.get("sell_draft", {}).pop(str(user_id), None)
        state.get("card_draft", {}).pop(str(user_id), None)
        state.get("auction_draft", {}).pop(str(user_id), None)
        state.get("pool_draft", {}).pop(str(user_id), None)
        state.get("pool_join_draft", {}).pop(str(user_id), None)
        state.get("bid_draft", {}).pop(str(user_id), None)
        state.get("topup_mm_draft", {}).pop(str(user_id), None)
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
            "removed": "❌ Removed by an admin",
        }.get(profile.get("status"), profile.get("status", "?"))
        kb = None
        if profile.get("status") == "live":
            kb = {
                "inline_keyboard": [
                    [
                        {
                            "text": "📣 Post to group",
                            "callback_data": "sellstart",
                        }
                    ]
                ]
            }
        send_photos_group(user_id, profile.get("photos") or [])
        send_message(
            chat_id,
            f"Your profile — {status}:\n\n" + profile_summary_text(profile),
            reply_markup=kb,
        )
        return

    if text == "/sell":
        start_sell(chat_id, user_id, state, user=msg.get("from", {}))
        return

    if text == "/auction":
        start_auction(chat_id, user_id, state, user=msg.get("from", {}))
        return

    if text == "/pool":
        start_pool(chat_id, user_id, state, user=msg.get("from", {}))
        return

    if text.startswith("/poolinfo"):
        parts = text.split()
        if len(parts) < 2:
            send_message(
                chat_id,
                "Usage: /poolinfo <pool id> — e.g. /poolinfo p12. "
                "The pool id is on the pool card, or tap "
                "📋 Contributors on the card.",
            )
            return
        pool = (state.get("pools") or {}).get(parts[1].strip())
        if not pool:
            send_message(chat_id, "No pool with that id.")
            return
        send_pool_info(chat_id, pool)
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

    b_draft = (state.get("bid_draft") or {}).get(str(user_id))
    if b_draft and not text.startswith("/"):
        amount = parse_bid_amount(text)
        if amount is None:
            send_message(
                chat_id,
                "Send your bid as a whole number in Ks, or /cancel.",
            )
            return
        auction = (state.get("auctions") or {}).get(b_draft.get("auction"))
        if not auction:
            state.get("bid_draft", {}).pop(str(user_id), None)
            save_state(state)
            send_message(chat_id, "That auction is gone.")
            return
        ok, msg = place_auction_bid(
            state, auction, user_id, amount, user=msg.get("from", {})
        )
        state.get("bid_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(chat_id, msg)
        return

    pj_draft = (state.get("pool_join_draft") or {}).get(str(user_id))
    if pj_draft and not text.startswith("/"):
        amount = parse_bid_amount(text)
        if amount is None:
            send_message(
                chat_id,
                "Send the amount as a whole number in Ks, or /cancel.",
            )
            return
        if amount < POOL_MIN_CONTRIB_KS:
            # Below the minimum: plain message, draft stays open so
            # the member can type a valid amount.
            send_message(
                chat_id,
                f"Minimum is {fmt_ks(POOL_MIN_CONTRIB_KS)} — send an "
                "amount of 1,000 Ks or more, or /cancel.",
            )
            return
        pool = (state.get("pools") or {}).get(pj_draft.get("pool"))
        if not pool:
            state.get("pool_join_draft", {}).pop(str(user_id), None)
            save_state(state)
            send_message(chat_id, "That pool is gone.")
            return
        ok, msg = join_pool(
            state, pool, user_id, amount, user=msg.get("from", {})
        )
        state.get("pool_join_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(chat_id, msg)
        return

    mm_draft = (state.get("topup_mm_draft") or {}).get(str(user_id))
    if mm_draft and not text.startswith("/"):
        handle_topup_mm_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    co_draft = (state.get("cashout_draft") or {}).get(str(user_id))
    if co_draft and (not text.startswith("/") or text == "/keep"):
        handle_cashout_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    cmm_draft = (state.get("cashout_mm_draft") or {}).get(str(user_id))
    if cmm_draft and not text.startswith("/"):
        handle_cashout_mm_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    su_draft = (state.get("sell_draft") or {}).get(str(user_id))
    if su_draft and not text.startswith("/"):
        handle_sell_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    card_draft = (state.get("card_draft") or {}).get(str(user_id))
    if card_draft and (
        not text.startswith("/") or text in ("/done", "/skip")
    ):
        handle_card_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    a_draft = (state.get("auction_draft") or {}).get(str(user_id))
    if a_draft and not text.startswith("/"):
        handle_auction_step(chat_id, user_id, text, state, user=msg.get("from", {}))
        return

    p_draft = (state.get("pool_draft") or {}).get(str(user_id))
    if p_draft and not text.startswith("/"):
        handle_pool_step(chat_id, user_id, text, state, user=msg.get("from", {}))
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

    if text == "/announce":
        # Admin-only announcement list: tap one option and the
        # matching announcement goes to the group. The list itself
        # stays in this DM — only the chosen announcement(s) post.
        send_message(
            chat_id,
            "📢 Announcements — tap to post to the group:",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "📢 Main intro",
                            "callback_data": "announce:main",
                        }
                    ],
                    [
                        {
                            "text": "🤝 Fundraiser pool",
                            "callback_data": "announce:pool",
                        }
                    ],
                    [
                        {
                            "text": "📢🤝 Both",
                            "callback_data": "announce:both",
                        }
                    ],
                ]
            },
        )
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
                chat_id, "No live sellers yet — members make a profile with /profile."
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
                item = PRODUCTS.get(p['product'], p['product'])
                if p.get("option"):
                    item += f" ({p['option']})"
                lines.append(
                    f"{fmt_time(p['ts'])} — {buyer} → "
                    f"{p.get('seller_name', p['seller'])} — "
                    f"{item} — "
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
                if p.get("method", "").startswith("Myanmar"):
                    lines.append(
                        f"{fmt_time(p['ts'])} — {name} — cash-out "
                        f"{fmt_ks(p.get('ks', 0))} → "
                        f"{p.get('address', '')} — {p['status']}"
                    )
                else:
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
            elif kind == "auction":
                buyer = (
                    f"@{p['buyer_username']}"
                    if p.get("buyer_username")
                    else p["buyer"]
                )
                item = PRODUCTS.get(p["product"], p["product"])
                lines.append(
                    f"{fmt_time(p['ts'])} — {buyer} → "
                    f"{p.get('seller_name', p['seller'])} — "
                    f"🔨 Auction {item} — "
                    f"{fmt_ks(p['ks'])} — {p['method']} — {p['status']}"
                )
            elif kind == "pool":
                item = PRODUCTS.get(p["product"], p["product"])
                lines.append(
                    f"{fmt_time(p['ts'])} — "
                    f"{p.get('seller_name', p['seller'])} — "
                    f"🤝 Pool {item} — "
                    f"{fmt_ks(p['ks'])} — "
                    f"{p.get('contributors', 0)} contributors — "
                    f"{p['method']} — {p['status']}"
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
        if receipt.get("kind") == "topup_mm":
            ks = int(receipt["ks"])
            if data.startswith("mmok:"):
                receipt["status"] = "approved"
                save_state(state)
                new_total = change_balance(cust_id, ks)
                record_topup(
                    cust_id, receipt.get("username", ""),
                    ks // KS_PER_USD, ks, TOPUP_MM_METHOD,
                )
                send_message(
                    cust_id,
                    f"✅ Top-up approved — {fmt_ks(ks)} added to your "
                    f"balance.\nYour balance is now {fmt_ks(new_total)}.",
                )
                answer_callback(qid, "Approved — balance credited.")
            else:
                receipt["status"] = "declined"
                save_state(state)
                send_message(
                    cust_id,
                    "❌ Your receipt was declined. Check the amount and "
                    "the payment and try again with /topup, or message "
                    "@SirArkar.",
                )
                answer_callback(qid, "Declined.")
            return
        if receipt.get("kind") == "market":
            seller_id = receipt["seller"]
            product = receipt["product"]
            price = int(receipt["price_ks"])
            method = receipt.get("method", "Myanmar pay")
            option = receipt.get("option")
            item = market_item_label(product, option)
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
                    option=option,
                )
                if receipt.get("card"):
                    reveal_card_purchase(
                        state, receipt["card"], option,
                        receipt.get("buyer_name")
                        or receipt.get("username")
                        or "Someone",
                    )
                send_message(
                    cust_id,
                    f"✅ Payment confirmed — you bought "
                    f"{item} for {fmt_ks(price)} "
                    f"from {seller_name}.",
                )
                send_message(
                    seller_id,
                    f"💰 Payment confirmed: {user_tag(query.get('from', {}))} "
                    f"bought your {item} for "
                    f"{fmt_ks(price)} via {method}.",
                )
                answer_callback(qid, "Confirmed.")
            else:
                receipt["status"] = "declined"
                save_state(state)
                record_market_sale(
                    cust_id, receipt.get("username", ""), seller_id,
                    seller_name, product, price, method, "declined",
                    option=option,
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
        if req.get("method") == "mm":
            # A Myanmar request is decided with its own buttons
            # (cmmok:/cmmno:) — the USDT buttons never apply to it.
            answer_callback(
                qid, "Use the Myanmar buttons for this one.",
                show_alert=True,
            )
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

    # ---- cash-out method choice + Myanmar account choice ----
    if data == "cashout_usdt":
        start_cashout_usdt(user_id, user_id, state)
        answer_callback(qid, "USDT cash-out — send the amount.")
        return

    if data == "cashout_mm":
        start_cashout_mm(user_id, user_id, state)
        answer_callback(qid, "Myanmar cash-out — pick an account.")
        return

    if data.startswith("coacc:"):
        key = data.split(":", 1)[1]
        draft = (state.get("cashout_mm_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "account":
            answer_callback(
                qid, "Start again with /cashout.", show_alert=True,
            )
            return
        if key == "other":
            send_message(
                user_id,
                "Type the service and number, e.g. \"KBZPay "
                "09403720481\" or \"WavePay 09780695959\", or /cancel.",
            )
            answer_callback(qid, "Type the account.")
            return
        profile = get_profile(user_id)
        number = ((profile or {}).get("pay", {}) or {}).get(key)
        label = {"kbz": "KBZPay", "wave": "WavePay", "aya": "AYAPay"}.get(key)
        if not number or not label:
            send_message(
                user_id,
                "That account is no longer on your profile — type the "
                "service and number, e.g. \"KBZPay 09403720481\".",
            )
            answer_callback(qid, "Account not on profile.")
            return
        draft.update(
            {"step": "amount", "service": label, "account": number}
        )
        save_state(state)
        ask_cashout_mm_amount(user_id, user_id, draft)
        answer_callback(qid, f"{label} selected.")
        return

    # ---- Myanmar cash-out: admin confirms the Ks is paid ----
    if data.startswith("cmmok:") or data.startswith("cmmno:"):
        if not is_admin(user_id):
            answer_callback(qid, "Admin only.", show_alert=True)
            return
        cid = data.split(":", 1)[1]
        req = (state.get("cashouts") or {}).get(cid)
        if not req or req.get("method") != "mm":
            answer_callback(qid, "Unknown cash-out request.", show_alert=True)
            return
        if req.get("status") != "pending":
            answer_callback(qid, "Already handled.", show_alert=True)
            return
        member_id = req["user"]
        amount = int(req["ks"])
        dest = f"{req['service']} {req['account']}"
        if data.startswith("cmmok:"):
            if get_balance(member_id) < amount:
                req["status"] = "failed"
                save_state(state)
                send_message(
                    member_id,
                    "Your cash-out request was cancelled — your balance "
                    "no longer covers it. Please try again with /cashout.",
                )
                answer_callback(
                    qid, "Balance no longer covers it — request cancelled.",
                    show_alert=True,
                )
                return
            # Mark handled + save BEFORE debiting, so a second
            # Approve finds it already handled and debits nothing
            # (same guard as the Myanmar top-up approve).
            req["status"] = "paid"
            req["decided_ts"] = int(time.time())
            save_state(state)
            change_balance(member_id, -amount)
            record_cashout(
                member_id, req.get("username", ""), amount, 0, dest,
                "paid", method=CASHOUT_MM_METHOD,
            )
            send_message(
                member_id,
                f"✅ Cash-out sent — {fmt_ks(amount)} to your "
                f"{req['service']} "
                f"<code>{html.escape(req['account'])}</code>.\n"
                f"Your balance is now {fmt_ks(get_balance(member_id))}.",
                parse_mode="HTML",
            )
            answer_callback(qid, "Paid — member notified, balance debited.")
        else:
            req["status"] = "declined"
            req["decided_ts"] = int(time.time())
            save_state(state)
            record_cashout(
                member_id, req.get("username", ""), amount, 0, dest,
                "declined", method=CASHOUT_MM_METHOD,
            )
            send_message(
                member_id,
                "❌ Your cash-out request was declined — your balance "
                "is untouched. If you think this is a mistake, message "
                "@HenryRealGood.",
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

    # ---- seller profile approval (LEGACY — profiles go live on
    # creation since v4, so no new profile is ever "pending". Kept
    # only so an old pending profile can still be approved/declined.) ----
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
                "find you with /sellers and buy your products.\n\n"
                "Post your first card to the group with /sell.",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "📣 Post to group",
                                "callback_data": "sellstart",
                            }
                        ]
                    ]
                },
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

    # ---- remove seller (admin moderation, not a gate) ----
    if data.startswith("profremove:"):
        if not is_admin(user_id):
            answer_callback(qid, "Admin only.", show_alert=True)
            return
        target = data.split(":", 1)[1]
        profiles = load_profiles()
        profile = profiles.get(str(target))
        if not profile:
            answer_callback(qid, "Unknown profile.", show_alert=True)
            return
        if profile.get("status") == "removed":
            answer_callback(qid, "Already removed.", show_alert=True)
            return
        profile["status"] = "removed"
        save_profiles(profiles)
        # Take their live cards down too, so nothing of theirs stays
        # buyable in the group.
        group = state.get("group") or GROUP_CHAT_ID
        for card in (state.get("cards") or {}).values():
            if str(card.get("seller")) == str(target) and card.get(
                "status"
            ) == "live":
                card["status"] = "removed"
                if group and card.get("message_id"):
                    api(
                        "deleteMessage",
                        {
                            "chat_id": group,
                            "message_id": card["message_id"],
                        },
                    )
        # And their live auctions — refund the highest bidder first.
        for auction in (state.get("auctions") or {}).values():
            if str(auction.get("seller")) == str(target) and auction.get(
                "status"
            ) == "live":
                _refund_auction_leader(state, auction)
                _delete_auction_card(state, auction)
                auction["status"] = "removed"
        # And their live pools — refund every contributor first.
        for pool in (state.get("pools") or {}).values():
            if str(pool.get("seller")) == str(target) and pool.get(
                "status"
            ) == "live":
                _refund_pool_contributors(state, pool)
                _delete_pool_card(state, pool)
                pool["status"] = "removed"
        save_state(state)
        send_message(
            target,
            "❌ Your seller profile was removed by an admin — your "
            "cards, auctions and pools are off the group and you can't "
            "post new ones until you make a new profile with /profile.",
        )
        answer_callback(qid, "Seller removed — cards taken down.")
        return

    # ---- profile setup: role picker ----
    if data.startswith("role:"):
        value = data.split(":", 1)[1]
        draft = (state.get("profile_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "role":
            answer_callback(qid, "No role picker open — /profile to start.")
            return
        if value == "other":
            draft["step"] = "role_text"
            save_state(state)
            send_message(
                user_id,
                "Type your role (1–30 characters) — e.g. top, bottom, "
                "verse, or anything else.",
            )
            answer_callback(qid, "Type your role.")
            return
        if value not in ROLE_OPTIONS:
            answer_callback(qid, "Unknown role.")
            return
        draft.setdefault("data", {})["role"] = value
        profile_after_role(
            user_id, draft, draft["data"], state, username
        )
        answer_callback(qid, f"Role: {value}.")
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
            "age": pdata.get("age"),
            "role": pdata.get("role"),
            "photos": list(pdata.get("photos") or []),
            "products": pdata.get("products", {}),
            "pay": pdata.get("pay", {}),
            "status": "live",
            "ts": int(time.time()),
        }
        save_profiles(profiles)
        state.get("profile_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(
            user_id,
            "✅ Your seller profile is LIVE! Other members can now "
            "find you with /sellers and buy your products.\n\n"
            "Post your first card to the group with /sell.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "📣 Post to group",
                            "callback_data": "sellstart",
                        }
                    ]
                ]
            },
        )
        profile = profiles[str(user_id)]
        for admin_id in sorted(ADMIN_IDS):
            send_message(
                admin_id,
                "🆕 New seller profile (live now):\n\n"
                + profile_summary_text(profile)
                + f"\n\nSeller: {user_tag(query.get('from', {}))}\n"
                "No approval needed — it is live now. Remove them "
                "below if needed.",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "🗑️ Remove seller",
                                "callback_data": f"profremove:{user_id}",
                            }
                        ]
                    ]
                },
            )
        answer_callback(qid, "Your profile is live.")
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

    # ---- /sell: member self-service product cards ----
    if data == "sellstart":
        start_sell(user_id, user_id, state, user=query.get("from", {}))
        answer_callback(qid, "Pick a product to post.")
        return

    if data.startswith("sellprod:"):
        key = data.split(":", 1)[1]
        draft = (state.get("card_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "product":
            answer_callback(qid, "No card in progress — /sell to start.")
            return
        profile = get_profile(user_id)
        if not profile or profile.get("status") != "live":
            answer_callback(
                qid, "Your profile is not live any more.", show_alert=True
            )
            return
        if key not in (profile.get("products") or {}):
            answer_callback(
                qid, "That product is not on your profile.", show_alert=True
            )
            return
        draft["product"] = key
        draft["options"] = []
        draft["step"] = "type"
        save_state(state)
        send_message(
            user_id,
            f"Posting {PRODUCTS.get(key, key)} — fixed price card or "
            "auction or pool?\n\n"
            "🛍️ Fixed price card: name your options (A, B, C, D) with "
            "your own prices — buyers tap an option to buy it.\n"
            "🔨 Auction: starting bid 5,000 Ks, 15 minutes, highest "
            "bidder wins the video privately.\n"
            "🤝 Pool: an expensive video at a price you set "
            "(50,000–500,000 Ks) — everyone puts in 1,000 Ks or "
            "more, and everyone who paid gets the video privately "
            "when the pool fills.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "🛍️ Fixed price card",
                            "callback_data": "selltype:fixed",
                        }
                    ],
                    [
                        {
                            "text": "🔨 Auction",
                            "callback_data": "selltype:auction",
                        }
                    ],
                    [
                        {
                            "text": "🤝 Pool",
                            "callback_data": "selltype:pool",
                        }
                    ],
                ]
            },
        )
        answer_callback(qid, "Fixed price, auction or pool?")
        return

    # ---- /sell: fixed price card or auction? ----
    if data.startswith("selltype:"):
        kind = data.split(":", 1)[1]
        draft = (state.get("card_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "type":
            answer_callback(qid, "No card in progress — /sell to start.")
            return
        if kind == "fixed":
            draft["step"] = "optname"
            save_state(state)
            profile = get_profile(user_id)
            send_optname_prompt(user_id, draft, profile)
            answer_callback(qid, "Name your first option.")
            return
        if kind == "auction":
            product = draft.get("product")
            state.get("card_draft", {}).pop(str(user_id), None)
            state.setdefault("auction_draft", {})[str(user_id)] = {
                "step": "video",
                "seller_name": draft.get("seller_name", "Seller"),
                "product": product,
            }
            save_state(state)
            send_message(
                user_id,
                f"🔨 Auction for {PRODUCTS.get(product, product)} — send "
                "the video now.\n\n"
                "Starting bid is fixed at 5,000 Ks. The auction runs 15 "
                "minutes once posted. The highest bidder wins the video "
                "privately — it is NOT revealed in the group (unless an "
                "admin wins). The cover photo is the video's own "
                "thumbnail, unblurred.\n\n"
                "Or /cancel.",
            )
            answer_callback(qid, "Send the video.")
            return
        if kind == "pool":
            product = draft.get("product")
            state.get("card_draft", {}).pop(str(user_id), None)
            state.setdefault("pool_draft", {})[str(user_id)] = {
                "step": "price",
                "seller_name": draft.get("seller_name", "Seller"),
                "product": product,
            }
            save_state(state)
            send_message(
                user_id,
                f"🤝 Pool for {PRODUCTS.get(product, product)} — set the "
                f"pool price (whole Ks, {fmt_ks(POOL_MIN_PRICE_KS)}–"
                f"{fmt_ks(POOL_MAX_PRICE_KS)}).\n\n"
                "Each person puts in 1,000 Ks or more, and when the "
                "total raised hits your price, the video goes "
                "privately to everyone who paid — it is NEVER "
                "revealed in the group. The cover photo is the "
                "video's own thumbnail, unblurred.\n\n"
                "Or /cancel.",
            )
            answer_callback(qid, "Set the price.")
            return
        answer_callback(qid, "Unknown choice.")
        return

    if data == "sellprof":
        draft = (state.get("card_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "optname" or draft.get("options"):
            answer_callback(qid, "No card in progress — /sell to start.")
            return
        profile = get_profile(user_id)
        if not profile or profile.get("status") != "live":
            answer_callback(
                qid, "Your profile is not live any more.", show_alert=True
            )
            return
        key = draft.get("product")
        price = (profile.get("products") or {}).get(key)
        if price is None:
            answer_callback(
                qid,
                "That product is not on your profile any more.",
                show_alert=True,
            )
            return
        draft["options"] = [{"name": PRODUCTS.get(key, key), "price": price}]
        card_options_done(user_id, user_id, draft, state)
        answer_callback(qid, "Now send the product photo or video.")
        return

    if data == "selldone":
        draft = (state.get("card_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "optname":
            answer_callback(qid, "No card in progress — /sell to start.")
            return
        if not draft.get("options"):
            answer_callback(
                qid, "Add at least one option first.", show_alert=True
            )
            return
        card_options_done(user_id, user_id, draft, state)
        answer_callback(qid, "Now send the product photo or video.")
        return

    if data == "sellpost":
        draft = (state.get("card_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "confirm" or not draft.get(
            "options"
        ):
            answer_callback(qid, "No card to post — /sell to start.")
            return
        profile = get_profile(user_id)
        if not profile or profile.get("status") != "live":
            state.get("card_draft", {}).pop(str(user_id), None)
            save_state(state)
            answer_callback(
                qid, "Your profile is not live any more.", show_alert=True
            )
            return
        group = state.get("group") or GROUP_CHAT_ID
        if not group:
            answer_callback(
                qid,
                "The group isn't linked yet — ask an admin.",
                show_alert=True,
            )
            return
        state["card_seq"] = state.get("card_seq", 0) + 1
        cid = f"c{state['card_seq']}"
        card = {
            "id": cid,
            "seller": str(user_id),
            "seller_name": profile.get("name", "Seller"),
            "age": profile.get("age"),
            "role": profile.get("role"),
            "product": draft["product"],
            "options": draft["options"],
            "media_type": draft.get("media_type"),
            "media_file_id": draft.get("media_file_id"),
            "preview_file_id": draft.get("preview_file_id"),
            "revealed": False,
            "message_id": None,
            "ts": int(time.time()),
            "status": "live",
        }
        state.setdefault("cards", {})[cid] = card
        save_state(state)
        mid, err = post_card_to_group(state, card)
        if err:
            card["status"] = "failed"
            save_state(state)
            send_message(
                user_id,
                "Posting failed — is the bot an admin in the group? "
                f"Telegram said: {err}",
            )
            answer_callback(qid, "Posting failed.")
            return
        card["message_id"] = mid
        state.get("card_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(
            user_id,
            "✅ Posted to the group! Members can tap an option to buy it.",
        )
        answer_callback(qid, "Posted.")
        return

    if data == "sellcancel":
        state.get("card_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(user_id, "Cancelled — nothing was posted.")
        answer_callback(qid, "Cancelled.")
        return

    if data.startswith("carddel:"):
        card_id = data.split(":", 1)[1]
        card = (state.get("cards") or {}).get(card_id)
        if not card:
            answer_callback(qid, "That card is gone.", show_alert=True)
            return
        if str(user_id) != str(card.get("seller")) and not is_admin(user_id):
            answer_callback(
                qid,
                "Only the seller or an admin can remove this.",
                show_alert=True,
            )
            return
        if card.get("status") != "live":
            answer_callback(qid, "Already removed.", show_alert=True)
            return
        card["status"] = "removed"
        save_state(state)
        chat = (
            (query.get("message") or {}).get("chat", {}).get("id")
            or state.get("group")
            or GROUP_CHAT_ID
        )
        if chat and card.get("message_id"):
            api(
                "deleteMessage",
                {"chat_id": chat, "message_id": card["message_id"]},
            )
        answer_callback(qid, "Card removed.")
        return

    # ---- auctions: post, bid, remove ----
    if data.startswith("aucprod:"):
        key = data.split(":", 1)[1]
        draft = (state.get("auction_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "product":
            answer_callback(qid, "No auction in progress — /auction to start.")
            return
        profile = get_profile(user_id)
        if not profile or profile.get("status") != "live":
            answer_callback(
                qid, "Your profile is not live any more.", show_alert=True
            )
            return
        if key not in (profile.get("products") or {}):
            answer_callback(
                qid, "That product is not on your profile.", show_alert=True
            )
            return
        draft["product"] = key
        draft["step"] = "video"
        save_state(state)
        send_message(
            user_id,
            f"🔨 Auction for {PRODUCTS.get(key, key)} — send the video now "
            "(1 to 5 minutes).\n\n"
            "Starting bid is fixed at 5,000 Ks. The auction runs 15 "
            "minutes once posted. The highest bidder wins the video "
            "privately — it is NOT revealed in the group (unless an "
            "admin wins). The cover photo is the video's own thumbnail, "
            "unblurred.\n\n"
            "Or /cancel.",
        )
        answer_callback(qid, "Send the video.")
        return

    if data.startswith("poolprod:"):
        key = data.split(":", 1)[1]
        draft = (state.get("pool_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "product":
            answer_callback(qid, "No pool in progress — /pool to start.")
            return
        profile = get_profile(user_id)
        if not profile or profile.get("status") != "live":
            answer_callback(
                qid, "Your profile is not live any more.", show_alert=True
            )
            return
        if key not in (profile.get("products") or {}):
            answer_callback(
                qid, "That product is not on your profile.", show_alert=True
            )
            return
        draft["product"] = key
        draft["step"] = "price"
        save_state(state)
        send_message(
            user_id,
            f"🤝 Pool for {PRODUCTS.get(key, key)} — set the pool price "
            f"(whole Ks, {fmt_ks(POOL_MIN_PRICE_KS)}–"
            f"{fmt_ks(POOL_MAX_PRICE_KS)}).\n\n"
            "Each person puts in 1,000 Ks or more, and when the total "
            "raised hits your price, the video goes privately to "
            "everyone who paid — it is NEVER revealed in the group. "
            "The cover photo is the video's own thumbnail, "
            "unblurred.\n\n"
            "Or /cancel.",
        )
        answer_callback(qid, "Set the price.")
        return

    if data == "auctpost":
        draft = (state.get("auction_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "confirm" or not draft.get(
            "video_file_id"
        ):
            answer_callback(qid, "No auction to post — /auction to start.")
            return
        profile = get_profile(user_id)
        if not profile or profile.get("status") != "live":
            state.get("auction_draft", {}).pop(str(user_id), None)
            save_state(state)
            answer_callback(
                qid, "Your profile is not live any more.", show_alert=True
            )
            return
        group = state.get("group") or GROUP_CHAT_ID
        if not group:
            answer_callback(
                qid,
                "The group isn't linked yet — ask an admin.",
                show_alert=True,
            )
            return
        state["auction_seq"] = state.get("auction_seq", 0) + 1
        aid = f"a{state['auction_seq']}"
        now = int(time.time())
        auction = {
            "id": aid,
            "seller": str(user_id),
            "seller_name": profile.get("name", "Seller"),
            "age": profile.get("age"),
            "role": profile.get("role"),
            "product": draft["product"],
            "video_file_id": draft["video_file_id"],
            "cover_file_id": draft.get("cover_file_id"),
            "duration_s": draft.get("duration_s"),
            "duration_min": draft.get("duration_min"),
            "start": AUCTION_START_KS,
            "current_bid": AUCTION_START_KS,
            "current_bidder": None,
            "current_bidder_name": "",
            "current_bidder_username": "",
            "ends_at": now + AUCTION_DURATION_S,
            "posted_at": now,
            "message_id": None,
            "status": "live",
        }
        state.setdefault("auctions", {})[aid] = auction
        save_state(state)
        mid, err = post_auction_to_group(state, auction)
        if err:
            auction["status"] = "failed"
            save_state(state)
            send_message(
                user_id,
                "Posting failed — is the bot an admin in the group? "
                f"Telegram said: {err}",
            )
            answer_callback(qid, "Posting failed.")
            return
        auction["message_id"] = mid
        state.get("auction_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(
            user_id,
            "✅ Auction posted to the group! 15 minutes — highest "
            "bidder wins the video privately.",
        )
        answer_callback(qid, "Posted.")
        return

    if data == "auctcancel":
        state.get("auction_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(user_id, "Cancelled — nothing was posted.")
        answer_callback(qid, "Cancelled.")
        return

    if data == "poolpost":
        draft = (state.get("pool_draft") or {}).get(str(user_id))
        if not draft or draft.get("step") != "confirm" or not draft.get(
            "video_file_id"
        ):
            answer_callback(qid, "No pool to post — /pool to start.")
            return
        profile = get_profile(user_id)
        if not profile or profile.get("status") != "live":
            state.get("pool_draft", {}).pop(str(user_id), None)
            save_state(state)
            answer_callback(
                qid, "Your profile is not live any more.", show_alert=True
            )
            return
        group = state.get("group") or GROUP_CHAT_ID
        if not group:
            answer_callback(
                qid,
                "The group isn't linked yet — ask an admin.",
                show_alert=True,
            )
            return
        state["pool_seq"] = state.get("pool_seq", 0) + 1
        pid = f"p{state['pool_seq']}"
        now = int(time.time())
        pool = {
            "id": pid,
            "seller": str(user_id),
            "seller_name": profile.get("name", "Seller"),
            "age": profile.get("age"),
            "role": profile.get("role"),
            "product": draft["product"],
            "video_file_id": draft["video_file_id"],
            "cover_file_id": draft.get("cover_file_id"),
            "duration_s": draft.get("duration_s"),
            "duration_min": draft.get("duration_min"),
            "price": int(draft.get("price") or POOL_MIN_PRICE_KS),
            "per_person": POOL_MIN_CONTRIB_KS,
            "raised": 0,
            "contributors": [],
            "posted_at": now,
            "message_id": None,
            "status": "live",
        }
        state.setdefault("pools", {})[pid] = pool
        save_state(state)
        mid, err = post_pool_to_group(state, pool)
        if err:
            pool["status"] = "failed"
            save_state(state)
            send_message(
                user_id,
                "Posting failed — is the bot an admin in the group? "
                f"Telegram said: {err}",
            )
            answer_callback(qid, "Posting failed.")
            return
        pool["message_id"] = mid
        state.get("pool_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(
            user_id,
            f"✅ Pool posted to the group! Price {fmt_ks(pool['price'])} — "
            "each person puts in 1,000 Ks or more. When the total "
            "raised hits the price, the video goes privately to "
            "everyone who paid.",
        )
        answer_callback(qid, "Posted.")
        return

    if data == "poolcancel":
        state.get("pool_draft", {}).pop(str(user_id), None)
        save_state(state)
        send_message(user_id, "Cancelled — nothing was posted.")
        answer_callback(qid, "Cancelled.")
        return

    if data.startswith("aucbidamt:"):
        parts = data.split(":")
        if len(parts) != 3:
            answer_callback(qid, "Unknown button.")
            return
        _, aid, amount_s = parts
        auction = (state.get("auctions") or {}).get(aid)
        if not auction:
            answer_callback(qid, "That auction is gone.", show_alert=True)
            return
        try:
            amount = int(amount_s)
        except ValueError:
            answer_callback(qid, "Unknown amount.")
            return
        ok, msg = place_auction_bid(
            state, auction, user_id, amount, user=query.get("from", {})
        )
        if ok:
            answer_callback(qid, "Bid placed.")
            send_message(user_id, msg)
        else:
            answer_callback(qid, msg, show_alert=True)
        return

    if data.startswith("aucbidtype:"):
        aid = data.split(":", 1)[1]
        auction = (state.get("auctions") or {}).get(aid)
        if not auction or auction.get("status") != "live":
            answer_callback(qid, "That auction has ended.", show_alert=True)
            return
        if str(user_id) == str(auction.get("seller")):
            answer_callback(qid, "That's your own auction.", show_alert=True)
            return
        current = (
            auction.get("current_bid")
            if auction.get("current_bidder")
            else auction.get("start", AUCTION_START_KS)
        )
        state.setdefault("bid_draft", {})[str(user_id)] = {"auction": aid}
        save_state(state)
        send_message(
            user_id,
            "How much do you bid? Minimum is "
            f"{fmt_ks(current + AUCTION_MIN_INCREMENT_KS)} — send the "
            "amount in Ks, or /cancel.",
        )
        answer_callback(qid, "Send your bid.")
        return

    if data.startswith("pooljoinask:"):
        pid = data.split(":", 1)[1]
        pool = (state.get("pools") or {}).get(pid)
        if not pool:
            answer_callback(qid, "That pool is gone.", show_alert=True)
            return
        if pool.get("status") != "live":
            answer_callback(
                qid, "That pool is closed.", show_alert=True
            )
            return
        if str(user_id) == str(pool.get("seller")):
            answer_callback(
                qid, "You can't join your own pool.", show_alert=True
            )
            return
        # Repeat contributions are allowed (v7.3): a member who
        # already put in money can top up again — join_pool adds
        # to their running total.
        state.setdefault("pool_join_draft", {})[str(user_id)] = {
            "pool": pid
        }
        save_state(state)
        send_message(
            user_id,
            "How much do you want to put in? Minimum "
            f"{fmt_ks(POOL_MIN_CONTRIB_KS)} — send the amount in Ks, "
            "or /cancel.",
        )
        answer_callback(qid, "Send your amount.")
        return

    if data.startswith("aucdel:"):
        aid = data.split(":", 1)[1]
        auction = (state.get("auctions") or {}).get(aid)
        if not auction:
            answer_callback(qid, "That auction is gone.", show_alert=True)
            return
        if str(user_id) != str(auction.get("seller")) and not is_admin(
            user_id
        ):
            answer_callback(
                qid,
                "Only the seller or an admin can remove this.",
                show_alert=True,
            )
            return
        if auction.get("status") != "live":
            answer_callback(qid, "Already removed.", show_alert=True)
            return
        _refund_auction_leader(state, auction)
        _delete_auction_card(state, auction)
        auction["status"] = "removed"
        save_state(state)
        if str(user_id) != str(auction.get("seller")):
            send_message(
                auction["seller"],
                "❌ Your auction was removed by an admin — the highest "
                "bidder was refunded.",
            )
        answer_callback(qid, "Auction removed.")
        return

    if data.startswith("pooldel:"):
        pid = data.split(":", 1)[1]
        pool = (state.get("pools") or {}).get(pid)
        if not pool:
            answer_callback(qid, "That pool is gone.", show_alert=True)
            return
        if str(user_id) != str(pool.get("seller")) and not is_admin(
            user_id
        ):
            answer_callback(
                qid,
                "Only the seller or an admin can remove this.",
                show_alert=True,
            )
            return
        if pool.get("status") != "live":
            answer_callback(qid, "Already removed.", show_alert=True)
            return
        _refund_pool_contributors(state, pool)
        _delete_pool_card(state, pool)
        pool["status"] = "cancelled"
        save_state(state)
        if str(user_id) != str(pool.get("seller")):
            send_message(
                pool["seller"],
                "❌ Your pool was removed by an admin — every "
                "contributor was refunded what they put in.",
            )
        answer_callback(qid, "Pool removed — everyone refunded.")
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
        send_seller_card(user_id, profile)
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
        # 4 parts: buypay:<method>:<seller>:<product> (profile price)
        # 6 parts: + :<card_id>:<opt_idx> (card option price — the card
        # is the source of truth for seller, product and price)
        option = None
        card_id = None
        opt_idx = None
        if len(parts) == 6:
            method = parts[1]
            card = (state.get("cards") or {}).get(parts[4])
            if not card or card.get("status") != "live":
                answer_callback(qid, "That card is gone.", show_alert=True)
                return
            try:
                opt_idx = int(parts[5])
                opt = card["options"][opt_idx]
            except (ValueError, IndexError, KeyError, TypeError):
                answer_callback(qid, "That option is gone.", show_alert=True)
                return
            seller_id = str(card["seller"])
            product = card["product"]
            price = int(opt["price"])
            option = opt["name"]
            card_id = card["id"]
            profile = get_profile(seller_id)
            if not profile or profile.get("status") != "live":
                answer_callback(
                    qid, "That seller is not live right now.", show_alert=True
                )
                return
        elif len(parts) == 4:
            _, method, seller_id, product = parts
            profile = get_profile(seller_id)
            if not profile or profile.get("status") != "live":
                answer_callback(
                    qid, "That seller is not live right now.", show_alert=True
                )
                return
            price = (profile.get("products") or {}).get(product)
            if price is None:
                answer_callback(
                    qid, "That product is no longer listed.", show_alert=True
                )
                return
        else:
            answer_callback(qid, "Unknown button.")
            return
        if str(user_id) == str(seller_id):
            answer_callback(qid, "That's your own product.", show_alert=True)
            return
        seller_name = profile.get("name", "Seller")
        item = market_item_label(product, option)
        suffix = f":{card_id}:{opt_idx}" if card_id is not None else ""
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
                "Balance", "paid", option=option,
            )
            if card_id is not None:
                reveal_card_purchase(
                    state, card_id, option,
                    (query.get("from") or {}).get("first_name")
                    or "Someone",
                )
            send_message(
                user_id,
                f"✅ Paid {fmt_ks(price)} from your balance for "
                f"{item} from {seller_name}.\n"
                f"Your balance is now {fmt_ks(new_buyer)}.",
            )
            send_message(
                seller_id,
                f"💰 {user_tag(query.get('from', {}))} bought your "
                f"{item} for {fmt_ks(price)} — "
                "paid from their bot balance.\n"
                f"Your balance is now {fmt_ks(new_seller)}. You can spend "
                "it on other sellers' products.",
            )
            answer_callback(qid, "Paid from balance.")
            return
        if method == "stars":
            stars = max(1, round(price / 50))
            payload = f"mkt:{seller_id}:{product}:{price}:{user_id}"
            if card_id is not None:
                payload += f":{card_id}:{opt_idx}"
            r = api(
                "sendInvoice",
                {
                    "chat_id": user_id,
                    "title": f"DaddyTeacher Market: {item}",
                    "description": (
                        f"{item} from "
                        f"{seller_name} — {fmt_ks(price)}."
                    ),
                    "payload": payload,
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [
                        {
                            "label": f"{item} — {fmt_ks(price)}",
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
                "option": option,
                "card": card_id,
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
                            "callback_data": f"dirpay:kbz:{seller_id}:{product}{suffix}",
                        }
                    ]
                )
            if pay.get("wave"):
                rows.append(
                    [
                        {
                            "text": "🇲🇲 WavePay",
                            "callback_data": f"dirpay:wave:{seller_id}:{product}{suffix}",
                        }
                    ]
                )
            if pay.get("aya"):
                rows.append(
                    [
                        {
                            "text": "🇲🇲 AYAPay",
                            "callback_data": f"dirpay:aya:{seller_id}:{product}{suffix}",
                        }
                    ]
                )
            if pay.get("bank_acct"):
                rows.append(
                    [
                        {
                            "text": "🏦 Bank transfer",
                            "callback_data": f"dirpay:bank:{seller_id}:{product}{suffix}",
                        }
                    ]
                )
            if pay.get("usdt"):
                rows.append(
                    [
                        {
                            "text": "💎 USDT (direct to seller)",
                            "callback_data": f"dirpay:usdt:{seller_id}:{product}{suffix}",
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
                f"{item} ({fmt_ks(price)}).\n"
                "Choose how:",
                reply_markup={"inline_keyboard": rows},
            )
            answer_callback(qid, "Choose how to pay the seller.")
            return
        answer_callback(qid, "Unknown button.")
        return

    if data.startswith("dirpay:"):
        parts = data.split(":")
        # 4 parts: dirpay:<method>:<seller>:<product> (profile price)
        # 6 parts: + :<card_id>:<opt_idx> (card option price)
        option = None
        card_id = None
        if len(parts) == 6:
            method = parts[1]
            card = (state.get("cards") or {}).get(parts[4])
            if not card or card.get("status") != "live":
                answer_callback(qid, "That card is gone.", show_alert=True)
                return
            try:
                opt_idx = int(parts[5])
                opt = card["options"][opt_idx]
            except (ValueError, IndexError, KeyError, TypeError):
                answer_callback(qid, "That option is gone.", show_alert=True)
                return
            seller_id = str(card["seller"])
            product = card["product"]
            price = int(opt["price"])
            option = opt["name"]
            card_id = card["id"]
            profile = get_profile(seller_id)
            if not profile or profile.get("status") != "live":
                answer_callback(
                    qid, "That seller is not live right now.", show_alert=True
                )
                return
        elif len(parts) == 4:
            _, method, seller_id, product = parts
            profile = get_profile(seller_id)
            if not profile or profile.get("status") != "live":
                answer_callback(
                    qid, "That seller is not live right now.", show_alert=True
                )
                return
            price = (profile.get("products") or {}).get(product)
            if price is None:
                answer_callback(
                    qid, "That product is no longer listed.", show_alert=True
                )
                return
        else:
            answer_callback(qid, "Unknown button.")
            return
        pay = profile.get("pay", {})
        seller_name = profile.get("name", "Seller")
        item = market_item_label(product, option)
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
                "option": option,
                "card": card_id,
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
            "option": option,
            "card": card_id,
        }
        save_state(state)
        send_message(
            user_id,
            f"Pay {fmt_ks(price)} for {item} to "
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

    if data == "topup_mm":
        state.setdefault("topup_mm_draft", {})[str(user_id)] = {
            "step": "amount",
        }
        save_state(state)
        send_message(
            user_id,
            "🇲🇲 Top up by KBZPay / WavePay / AYAPay.\n\n"
            "Pay to any of these:\n\n"
            + mm_admin_numbers_text()
            + "\n\nType the amount in Ks you are paying "
            f"(minimum {fmt_ks(TOPUP_MM_MIN_KS)}), or /cancel.",
            parse_mode="HTML",
        )
        answer_callback(qid, "Myanmar payment details sent.")
        return

    if data.startswith("announce:"):
        # Admin-only announcement list (/announce): post the main
        # intro, the pool announcement, or both, to the group.
        # This MUST sit before the pack section below: its generic
        # "key not in PACKS" check would swallow "announce:main"
        # ("main" is not a pack key).
        if not is_admin(user_id):
            answer_callback(qid, "Admin only.", show_alert=True)
            return
        choice = data.split(":", 1)[1]
        if choice not in ("main", "pool", "both"):
            answer_callback(qid, "Unknown button.")
            return
        group = state.get("group") or GROUP_CHAT_ID
        if not group:
            answer_callback(qid, "No group linked yet.")
            send_message(
                user_id,
                "No group linked yet — nothing was posted.\n"
                "Set it with /setgroup <@group>, or forward any "
                "message from the group to me, then tap again.",
            )
            return
        texts = []
        if choice in ("main", "both"):
            texts.append(("Main intro", MAIN_ANNOUNCEMENT))
        if choice in ("pool", "both"):
            texts.append(("Fundraiser pool", POOL_ANNOUNCEMENT))
        posted = []
        for name, text in texts:
            mid, err = post_to_group(state, text)
            if err:
                answer_callback(
                    qid, f"Posting failed — {err}", show_alert=True
                )
                send_message(
                    user_id,
                    "Posting failed — is the bot an admin in the "
                    f"group? Telegram said: {err}"
                    + (
                        f"\nAlready posted: {', '.join(posted)}."
                        if posted
                        else ""
                    ),
                )
                return
            posted.append(name)
        answer_callback(qid, "Posted to the group.")
        send_message(
            user_id,
            "✅ Posted to the group: " + " + ".join(posted) + ".",
        )
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
        # Auction deadlines + 24-hour post expiry run here, every
        # polling iteration — no external cron is needed.
        before_sweep = json.dumps(state, sort_keys=True)
        try:
            sweep_auctions(state)
        except Exception as e:
            print(f"auction sweep error: {e}", flush=True)
        if json.dumps(state, sort_keys=True) != before_sweep:
            dirty = True
        if dirty:
            save_state(state)


if __name__ == "__main__":
    main()
