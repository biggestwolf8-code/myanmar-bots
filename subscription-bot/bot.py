#!/usr/bin/env python3
"""
Biggest Seller Myanmar - Telegram catalog bot.

Browse 80+ digital subscriptions by category (tap buttons) or search by
typing a product name. Unknown questions are forwarded to the admin, and
the admin's reply to a forwarded message is relayed back to the customer.

Env vars:
    BOT_TOKEN        - from @BotFather (create a NEW bot for this business)
    ADMIN_CHAT_ID    - your Telegram user id (from @userinfobot)
    CONTACT_USERNAME - order contact shown to customers (default @biggestseller1)
"""

import json
import os
import time
import unicodedata

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()
CONTACT = os.environ.get("CONTACT_USERNAME", "@biggestseller1").strip() or "@biggestseller1"

if not BOT_TOKEN:
    raise SystemExit("Set the BOT_TOKEN env var (get it from @BotFather).")
if not ADMIN_CHAT_ID:
    print("WARNING: ADMIN_CHAT_ID not set - questions can't be forwarded.")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
STATE_FILE = os.path.join(BASE_DIR, "forward_map.json")

with open(os.path.join(BASE_DIR, "catalog.json"), encoding="utf-8") as f:
    CATALOG = json.load(f)

CATS = sorted({it["category"] for it in CATALOG})
PRODUCTS = {c: sorted({it["product"] for it in CATALOG if it["category"] == c})
            for c in CATS}

WELCOME = (
    "👋 Biggest Seller Myanmar မှ ကြိုဆိုပါတယ်!\n"
    "Subscription 80+ ကို category ရွေးပြီး ကြည့်နိုင်ပါတယ်၊ "
    "သို့မဟုတ် နာမည်ရိုက်ရှာပါ (ဥပမာ 'spotify', 'netflix', 'canva').\n\n"
    "👋 Welcome to Biggest Seller Myanmar!\n"
    "Browse 80+ subscriptions by category, or just type a name "
    "(e.g. 'spotify', 'netflix', 'canva')."
)

FALLBACK = (
    "Thanks! I've passed your question to the admin — they'll reply here soon. 🙏\n"
    "ကျေးဇူးပါ! မေးခွန်းကို admin ထံပို့ပေးလိုက်ပါပြီ — "
    "မကြာခင် ဒီမှာပဲ ပြန်ဖြေပေးပါမယ်။ 🙏"
)

ADMIN_NOTE = (
    "(Admin note: no product matched this, so nothing was forwarded — "
    "you're the admin. A customer asking this would be forwarded to you.)"
)

RECEIPT_MSG = (
    "📸 Receipt received! The admin will check it and confirm here soon. 🙏\n"
    "📸 ပြေစာရရှိပါပြီ! Admin စစ်ဆေးပြီး ဒီမှာပဲ အတည်ပြုပေးပါမယ်။ 🙏"
)

# Fixed answers, checked before product search. [PAYMENT] is a placeholder
# until the owner provides the real payment methods.
FAQ = [
    {"keywords": ["how can i pay", "how do i pay", "pay", "payment", "kbzpay",
                  "wavepay", "aya pay", "ayapay", "bank transfer", "qr",
                  "promptpay", "prompt pay", "ငွေပေး", "ငွေချေ"],
     "photo": "thai-qr.jpg",
     "answer": (
         "💳 Payment methods:\n"
         "• KBZPay: 09403720481 (Arkar Myo Win)\n"
         "• WavePay: 09780695959 (Arkar Myo Win)\n"
         "• AYAPay: 09754926216 (Arkar Myowin)\n"
         "• Thailand: bank QR code (see QR below)\n\n"
         "⚠️ Please confirm the price with @biggestseller1 before paying, "
         "then send your receipt here. 🙏\n\n"
         "💳 ပေးချေနည်းများ:\n"
         "• KBZPay: 09403720481 (Arkar Myo Win)\n"
         "• WavePay: 09780695959 (Arkar Myo Win)\n"
         "• AYAPay: 09754926216 (Arkar Myowin)\n"
         "• ထိုင်း: ဘဏ် QR code (အောက် QR ကို scan ဖတ်ပါ)\n\n"
         "⚠️ ငွေမလွှဲခင် @biggestseller1 နဲ့ ဈေးနှုန်းအတည်ပြုပါ၊ "
         "ပြီးရင် ပြေစာကို ဒီမှာပို့ပေးပါ။ 🙏")},
    {"keywords": ["warranty", "guarantee", "refund", "replacement", "အာမခံ"],
     "answer": (
         "✅ 100% warranty for the full subscription period — if your account "
         "has any problem, contact @biggestseller1 for a fix or replacement.\n\n"
         "✅ Subscription ကာလအပြည့်အဝ 100% warranty ပေးပါတယ် — "
         "ပြဿနာရှိရင် @biggestseller1 ကို ဆက်သွယ်ပါ။")},
    {"keywords": ["reseller", "resell", "20%"],
     "answer": (
         "🤝 Resellers get 20% off! Message @biggestseller1 for reseller details.\n\n"
         "🤝 Reseller များအတွက် 20% off ပေးပါတယ်! "
         "အသေးစိတ်ကို @biggestseller1 ကို ဆက်သွယ်ပါ။")},
]


def find_faq(text):
    """Best FAQ entry by keyword hits, ties broken by keyword coverage."""
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
    if reply_markup is not None:
        params["reply_markup"] = reply_markup
    return api("sendMessage", **params)


def load_map():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_map(mapping):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f)


def norm(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


# ---------- catalog helpers ----------

def kb_cats():
    rows = [[{"text": c, "callback_data": f"c:{i}"}] for i, c in enumerate(CATS)]
    return {"inline_keyboard": rows}


def kb_products(ci):
    rows = [[{"text": p, "callback_data": f"p:{ci}:{j}"}]
            for j, p in enumerate(PRODUCTS[CATS[ci]])]
    rows.append([{"text": "⬅️ Categories", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def kb_back(ci):
    return {"inline_keyboard": [[{"text": "⬅️ Back", "callback_data": f"c:{ci}"}]]}


def prod_callback(product):
    for ci, c in enumerate(CATS):
        if product in PRODUCTS[c]:
            return f"p:{ci}:{PRODUCTS[c].index(product)}"
    return "home"


def product_text(product):
    items = [it for it in CATALOG if it["product"] == product]
    lines = [f"📦 {product}"]
    for it in items:
        line = f"• {it['plan']} — {it['price_ks']:,} Ks"
        if it.get("notes"):
            line += f"\n  ({it['notes']})"
        lines.append(line)
    lines.append(f"\n📩 Order: {CONTACT}")
    return "\n".join(lines)


def search_products(query):
    # A match needs substance: the full query, a long word (>=4 chars),
    # or at least two short words — so "do you sell steam wallets?"
    # doesn't match Adobe/Windows/YouTube on "do"/"you".
    qt = norm(query)
    words = [w for w in qt.split() if len(w) > 1]
    if not words:
        return []
    names = sorted({it["product"] for it in CATALOG})
    scored = []
    for p in names:
        pn = norm(p)
        if qt in pn and len(qt) >= 3:
            scored.append((p, 100))
            continue
        strong = sum(1 for w in words if len(w) >= 4 and w in pn)
        total = sum(1 for w in words if w in pn)
        if strong or total >= 2:
            scored.append((p, 100 if strong else total))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [p for p, _ in scored]


# ---------- update handling ----------

def forward_to_admin(chat_id, message_id, fwd_map):
    if not ADMIN_CHAT_ID:
        return
    res = api("forwardMessage", chat_id=ADMIN_CHAT_ID,
              from_chat_id=chat_id, message_id=message_id)
    if res.get("ok"):
        fwd_map[str(res["result"]["message_id"])] = str(chat_id)
        save_map(fwd_map)


def handle_message(msg, fwd_map):
    chat_id = str(msg["chat"]["id"])
    is_admin = bool(ADMIN_CHAT_ID) and chat_id == ADMIN_CHAT_ID

    # Photo (e.g. payment receipt screenshot): forward to admin, acknowledge.
    if "photo" in msg:
        if not is_admin:
            forward_to_admin(chat_id, msg["message_id"], fwd_map)
            send_threaded(chat_id, RECEIPT_MSG, msg)
        return

    if "text" not in msg:
        return
    text = msg["text"]

    # Admin replying to a forwarded customer message -> relay it back.
    if is_admin and msg.get("reply_to_message"):
        student_id = fwd_map.get(str(msg["reply_to_message"]["message_id"]))
        if student_id:
            api("sendMessage", chat_id=student_id, text=text)
            return

    if text.startswith("/start"):
        send_threaded(chat_id, WELCOME, msg, reply_markup=kb_cats())
        return

    faq = find_faq(text)
    if faq:
        if faq.get("photo"):
            send_photo(chat_id, faq["photo"], faq["answer"], msg)
        else:
            send_threaded(chat_id, faq["answer"], msg)
        return

    matches = search_products(text)
    if len(matches) == 1:
        send_threaded(chat_id, product_text(matches[0]), msg)
    elif matches:
        rows = [[{"text": p, "callback_data": prod_callback(p)}]
                for p in matches[:8]]
        send_threaded(chat_id, "Found these — tap one:", msg,
            reply_markup={"inline_keyboard": rows})
    elif is_admin:
        send_threaded(chat_id, ADMIN_NOTE, msg)
    else:
        forward_to_admin(chat_id, msg["message_id"], fwd_map)
        send_threaded(chat_id, FALLBACK, msg)


def handle_callback(cb):
    data = cb.get("data", "")
    msg = cb.get("message") or {}
    chat_id = str(msg.get("chat", {}).get("id", ""))
    msg_id = msg.get("message_id")
    api("answerCallbackQuery", callback_query_id=cb["id"])
    if not chat_id or not msg_id:
        return

    def edit(text, markup):
        api("editMessageText", chat_id=chat_id, message_id=msg_id,
            text=text, reply_markup=markup)

    if data == "home":
        edit(WELCOME, kb_cats())
    elif data.startswith("c:"):
        try:
            ci = int(data[2:])
            edit(f"📂 {CATS[ci]} — choose a product:", kb_products(ci))
        except (ValueError, IndexError):
            pass
    elif data.startswith("p:"):
        try:
            _, ci, j = data.split(":")
            product = PRODUCTS[CATS[int(ci)]][int(j)]
            edit(product_text(product), kb_back(int(ci)))
        except (ValueError, IndexError, KeyError):
            pass


def main():
    print(f"Catalog bot started: {len(CATALOG)} plans, {len(CATS)} categories. Polling…")
    fwd_map = load_map()
    offset = 0
    while True:
        try:
            data = api("getUpdates", offset=offset, timeout=50,
                       allowed_updates=["message", "callback_query"])
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                if "callback_query" in upd:
                    handle_callback(upd["callback_query"])
                elif "message" in upd:
                    handle_message(upd["message"], fwd_map)
        except Exception as e:  # keep polling through network blips
            print("Polling error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
