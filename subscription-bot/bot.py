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

import vpn as vpn_mod

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

# ---------- VPN purchase flow ----------
# Pending VPN orders: customer chat_id -> plan label. Set when they tap Buy,
# cleared when the receipt arrives (forwarded to admin for approval).
VPN_ORDERS_FILE = os.path.join(BASE_DIR, "vpn_pending.json")

# Pending app orders: customer chat_id -> {product, plan}. For Chat GPT Plus / Claude AI Pro.
APP_ORDERS_FILE = os.path.join(BASE_DIR, "app_pending.json")

# Web app URLs for instant code generation
APP_URLS = {
    "Chat GPT Plus": "https://gpt-web-production-ba94.up.railway.app",
    "Claude AI Pro": "https://claude-web-production-6603.up.railway.app",
}
APP_PRODUCTS = ["Chat GPT Plus", "Claude AI Pro"]

# Plan label -> days for code expiry
APP_PLAN_DAYS = {
    "1 Month": 30, "3 Months": 90, "6 Months": 180, "1 Year": 365,
}

VPN_PAYMENT_MSG = (
    "💳 To order Biggest VPN ({plan} — {price:,} Ks):\n\n"
    "1️⃣ Pay to any of these:\n"
    "• KBZPay: 09403720481 (Arkar Myo Win)\n"
    "• WavePay: 09780695959 (Arkar Myo Win)\n"
    "• AYAPay: 09754926216 (Arkar Myowin)\n\n"
    "2️⃣ Send your payment receipt screenshot HERE.\n\n"
    "⚡ Your VPN configs (4 countries) arrive right after admin confirms. 🙏\n\n"
    "💳 Biggest VPN ({plan} — {price:,} ကျပ်) မှာယူရန်:\n\n"
    "1️⃣ ငွေလွှဲရန်:\n"
    "• KBZPay: 09403720481 (Arkar Myo Win)\n"
    "• WavePay: 09780695959 (Arkar Myo Win)\n"
    "• AYAPay: 09754926216 (Arkar Myowin)\n\n"
    "2️⃣ ပြေစာ screenshot ကို ဒီမှာပို့ပေးပါ။\n\n"
    "⚡ Admin အတည်ပြုပြီးတာနဲ့ VPN config (၄ နိုင်ငံ) ချက်ချင်းရပါမယ်။ 🙏"
)

# NOTE: Burmese wording below is a DRAFT — owner must verify before final.
VPN_WELCOME_MSG = (
    "🎉 Your Biggest VPN is ready! ({plan})\n"
    "Code: {code}\n"
    "Expires: {expires}\n\n"
    "📲 SETUP — do this once (takes 2 minutes):\n\n"
    "1️⃣ Install the free \"WireGuard\" app from Play Store (Android) "
    "or App Store (iPhone).\n\n"
    "2️⃣ You'll see 4 files above — one per country "
    "(Singapore, Japan, UK, USA). Save all 4 to your phone.\n\n"
    "3️⃣ Open the WireGuard app → tap the + button → "
    "\"Import from file\" → choose the first .conf file. "
    "Repeat for the other 3. You'll now see 4 tunnels listed.\n\n"
    "4️⃣ To connect: tap the toggle switch next to the country you want. "
    "That's it — you're on VPN! ✅\n\n"
    "🔄 TO SWITCH COUNTRIES: turn OFF the current tunnel first, "
    "then turn ON the one you want. (Only one can be active at a time.)\n\n"
    "💡 TIP: start with Singapore — it's closest and usually fastest.\n\n"
    "❓ Problems? Message @biggestseller1.\n"
    "━━━━━━━━━━━━━━━\n"
    "🎉 Biggest VPN ရပါပြီ! ({plan})\n"
    "ကုဒ်: {code}\n"
    "သက်တမ်း: {expires} ထိ\n\n"
    "📲 တပ်ဆင်နည်း — တစ်ခါပဲလုပ်ရန် (၂ မိနစ်ခန့်):\n\n"
    "1️⃣ \"WireGuard\" app အခမဲ့ကို Play Store (Android) သို့မဟုတ် "
    "App Store (iPhone) မှ install လုပ်ပါ။\n\n"
    "2️⃣ အပေါ်မှာ file ၄ ခု တွေ့ပါမယ် — တစ်နိုင်ငံတစ်ခု "
    "(Singapore, Japan, UK, USA)။ ၄ ခုလုံး ဖုန်းထဲသိမ်းပါ။\n\n"
    "3️⃣ WireGuard app ဖွင့် → + ခလုတ်နှိပ် → \"Import from file\" → "
    "ပထမ .conf file ရွေး။ ကျန် ၃ ခုလည်း ဒီလိုပဲလုပ်။ "
    "Tunnel ၄ ခု စာရင်းပေါ်လာပါမယ်။\n\n"
    "4️⃣ ချိတ်ဆက်ရန်: လိုချင်တဲ့နိုင်ငံ ဘေးက ခလုတ်ကိုနှိပ်။ "
    "ရပါပြီ! ✅\n\n"
    "🔄 နိုင်ငံပြောင်းရန်: လက်ရှိဟာကို အရင် ပိတ် (OFF), "
    "ပြီးမှ နောက်တစ်ခုကို ဖွင့် (ON)။ "
    "(တစ်ချိန်မှာ တစ်ခုပဲသုံးလို့ရပါတယ်။)\n\n"
    "💡 အကြံ: Singapore က အနီးဆုံးမို့ အမြန်ဆုံးဖြစ်တတ်ပါတယ်။\n\n"
    "❓ အခက်အခဲရှိရင် @biggestseller1 ကို ဆက်သွယ်ပါ။"
)


def load_vpn_orders():
    try:
        with open(VPN_ORDERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_vpn_orders(d):
    tmp = VPN_ORDERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, VPN_ORDERS_FILE)


def load_app_orders():
    try:
        with open(APP_ORDERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_app_orders(d):
    tmp = APP_ORDERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, APP_ORDERS_FILE)


def kb_app_buy(product):
    """Buy buttons for each app plan (Chat GPT Plus / Claude AI Pro)."""
    items = [it for it in CATALOG if it["product"] == product]
    rows = [[{"text": f"🛒 Buy {it['plan']} — {it['price_ks']:,} Ks",
              "callback_data": f"appbuy:{product}:{it['plan']}"}] for it in items]
    rows.append([{"text": "⬅️ Back", "callback_data": prod_callback(product)}])
    return {"inline_keyboard": rows}


def create_app_code(product, plan_label, customer_id):
    """Call the web app's subscription API to generate an invite code.
    Returns (ok, code, link) or (False, error_message, None)."""
    import urllib.request
    base_url = APP_URLS.get(product)
    if not base_url:
        return False, f"Unknown app: {product}", None
    secret = os.environ.get("SUBSCRIPTION_SECRET", "").strip()
    if not secret:
        return False, "SUBSCRIPTION_SECRET not configured", None
    # Extract days from plan label (e.g. "Private Access / Unlimited Devices / 1 Month")
    days = 30
    for label, d in APP_PLAN_DAYS.items():
        if label in plan_label:
            days = d
            break
    payload = json.dumps({
        "secret": secret,
        "days": days,
        "label": f"subscription-bot/{customer_id}",
    }).encode()
    try:
        req = urllib.request.Request(
            f"{base_url}/api/subscription/create_code",
            data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read().decode())
        if resp.get("ok"):
            return True, resp["code"], resp["link"]
        return False, resp.get("error", "unknown error"), None
    except Exception as e:
        return False, str(e), None


def kb_vpn_buy(product):
    """Buy buttons for each VPN plan."""
    items = [it for it in CATALOG if it["product"] == product]
    rows = [[{"text": f"🛒 Buy {it['plan']} — {it['price_ks']:,} Ks",
              "callback_data": f"vpnbuy:{it['plan']}"}] for it in items]
    rows.append([{"text": "⬅️ Back", "callback_data": prod_callback(product)}])
    return {"inline_keyboard": rows}


def send_vpn_configs(chat_id, result):
    """Deliver the 4 .conf files + setup instructions to the customer."""
    for srv in ("singapore", "japan", "uk", "usa"):
        country = vpn_mod.SERVERS[srv]["country"]
        filename = f"BiggestVPN-{country}.conf"
        content = result["configs"][srv]
        r = requests.post(
            f"{API}/sendDocument", data={"chat_id": chat_id,
                                         "caption": f"🌍 {country}"},
            files={"document": (filename, content.encode())}, timeout=60)
        if not r.json().get("ok"):
            print("Failed to send conf:", r.text)
    exp = result["expires_at"][:10]
    api("sendMessage", chat_id=chat_id,
        text=VPN_WELCOME_MSG.format(plan=result.get("plan", ""),
                                   code=result["code"], expires=exp))

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
            # If this customer tapped a VPN Buy button, give admin one-tap approve.
            orders = load_vpn_orders()
            order = orders.get(chat_id)
            if order and ADMIN_CHAT_ID:
                plan = order["plan"]
                price = next((it["price_ks"] for it in CATALOG
                              if it["product"] == "Biggest VPN"
                              and it["plan"] == plan), 0)
                api("sendMessage", chat_id=ADMIN_CHAT_ID,
                    text=(f"🛡️ VPN order: {plan} — {price:,} Ks\n"
                          f"Customer: {chat_id}\n"
                          "Tap to approve & auto-deliver configs, or decline."),
                    reply_markup={"inline_keyboard": [[
                        {"text": "✅ Approve & Deliver",
                         "callback_data": f"vpnok:{chat_id}:{plan}"},
                        {"text": "❌ Decline",
                         "callback_data": f"vpnno:{chat_id}"}]]})
                return
            # If this customer tapped an app Buy button, give admin one-tap approve.
            app_orders = load_app_orders()
            app_order = app_orders.get(chat_id)
            if app_order and ADMIN_CHAT_ID:
                product, plan = app_order["product"], app_order["plan"]
                price = next((it["price_ks"] for it in CATALOG
                              if it["product"] == product
                              and it["plan"] == plan), 0)
                api("sendMessage", chat_id=ADMIN_CHAT_ID,
                    text=(f"🤖 {product} order: {plan} — {price:,} Ks\n"
                          f"Customer: {chat_id}\n"
                          "Tap to approve & auto-deliver invite code, or decline."),
                    reply_markup={"inline_keyboard": [[
                        {"text": "✅ Approve & Deliver",
                         "callback_data": f"appok:{chat_id}"},
                        {"text": "❌ Decline",
                         "callback_data": f"appno:{chat_id}"}]]})
                return
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

    # ---- VPN admin commands ----
    if is_admin and text.startswith("/vpnlist"):
        custs = vpn_mod.list_active()
        if not custs:
            send_threaded(chat_id, "No active VPN customers.", msg)
        else:
            lines = ["🛡️ VPN customers:"]
            for code, c in custs.items():
                exp = c.get("expires_at", "?")[:10]
                lines.append(f"• {code} — {c.get('name')} "
                             f"({c.get('plan')}) — until {exp}")
            send_threaded(chat_id, "\n".join(lines), msg)
        return

    if is_admin and text.startswith("/vpnrenew"):
        parts = text.split()
        if len(parts) != 3:
            send_threaded(chat_id,
                          "Usage: /vpnrenew CODE days  (e.g. /vpnrenew VPN-123456 30)",
                          msg)
            return
        _, code, days = parts
        try:
            days = int(days)
        except ValueError:
            send_threaded(chat_id, "Days must be a number.", msg)
            return
        ok, res = vpn_mod.renew(code, days)
        if not ok:
            send_threaded(chat_id, f"❌ {res}", msg)
            return
        exp = res[:10]
        send_threaded(chat_id,
                      f"✅ {code} extended — now expires {exp}. "
                      "Customer keeps using their existing configs.", msg)
        # notify the customer
        cust = vpn_mod.get(code)
        if cust and cust.get("telegram_id"):
            api("sendMessage", chat_id=cust["telegram_id"],
                text=f"🎉 Your Biggest VPN has been extended until {exp}! "
                     "No need to change anything — your existing setup keeps working. ✅")
        return

    if is_admin and text.startswith("/vpnrevoke"):
        parts = text.split()
        if len(parts) != 2:
            send_threaded(chat_id, "Usage: /vpnrevoke CODE", msg)
            return
        ok, res = vpn_mod.revoke(parts[1])
        if not ok:
            send_threaded(chat_id, f"❌ {res}", msg)
        else:
            send_threaded(chat_id,
                          f"✅ {parts[1]} revoked and removed from all servers."
                          + (f" (notes: {res})" if res else ""), msg)
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
            if product == "Biggest VPN":
                edit(f"🛡️ {product} — choose a plan:\n"
                     "4 countries included: Singapore, Japan, UK, USA.",
                     kb_vpn_buy(product))
            elif product in APP_PRODUCTS:
                edit(f"🤖 {product} — choose a plan:\n"
                     "Private Access / Unlimited Devices.\n"
                     "Instant invite code on approval.",
                     kb_app_buy(product))
            else:
                edit(product_text(product), kb_back(int(ci)))
        except (ValueError, IndexError, KeyError):
            pass
    elif data.startswith("vpnbuy:"):
        plan = data[len("vpnbuy:"):]
        price = next((it["price_ks"] for it in CATALOG
                      if it["product"] == "Biggest VPN"
                      and it["plan"] == plan), 0)
        orders = load_vpn_orders()
        orders[chat_id] = {"plan": plan, "at": time.time()}
        save_vpn_orders(orders)
        edit(VPN_PAYMENT_MSG.format(plan=plan, price=price),
             {"inline_keyboard": [[{"text": "⬅️ Plans",
                                    "callback_data": prod_callback("Biggest VPN")}]]})
    elif data.startswith("appbuy:"):
        # Customer tapped Buy for Chat GPT Plus / Claude AI Pro
        try:
            _, product, plan = data.split(":", 2)
        except ValueError:
            return
        if product not in APP_PRODUCTS:
            return
        price = next((it["price_ks"] for it in CATALOG
                      if it["product"] == product
                      and it["plan"] == plan), 0)
        orders = load_app_orders()
        orders[chat_id] = {"product": product, "plan": plan, "at": time.time()}
        save_app_orders(orders)
        edit(f"💳 To order {product} ({plan} — {price:,} Ks):\n\n"
             f"KBZPay: 09403720481\nWavePay: 09780695959\nAYAPay: 09754926216\n"
             f"(Account: Arkar Myo Win)\n\n"
             f"📸 Send your payment receipt screenshot here.",
             {"inline_keyboard": [[{"text": "⬅️ Plans",
                                    "callback_data": prod_callback(product)}]]})
    elif data.startswith("vpnok:"):
        # Admin approved a VPN order: vpnok:<customer_chat_id>:<plan>
        try:
            _, cust_id, plan = data.split(":", 2)
        except ValueError:
            return
        if chat_id != ADMIN_CHAT_ID:
            return
        api("sendMessage", chat_id=cust_id,
            text="✅ Payment confirmed! Setting up your VPN… ⚡")
        ok, result = vpn_mod.provision(cust_id, cust_id, plan)
        if ok:
            result["plan"] = plan
            send_vpn_configs(cust_id, result)
            api("sendMessage", chat_id=chat_id,
                text=f"✅ VPN delivered to {cust_id} ({plan}, code {result['code']}).")
            orders = load_vpn_orders()
            orders.pop(cust_id, None)
            save_vpn_orders(orders)
        else:
            api("sendMessage", chat_id=chat_id,
                text=f"❌ VPN provisioning failed for {cust_id}: {result}")
    elif data.startswith("vpnno:"):
        try:
            _, cust_id = data.split(":", 1)
        except ValueError:
            return
        if chat_id != ADMIN_CHAT_ID:
            return
        api("sendMessage", chat_id=cust_id,
            text="❌ We couldn't confirm your payment. Please contact @biggestseller1.")
        orders = load_vpn_orders()
        orders.pop(cust_id, None)
        save_vpn_orders(orders)
    elif data.startswith("appok:"):
        # Admin approved an app order: appok:<customer_chat_id>
        try:
            _, cust_id = data.split(":", 1)
        except ValueError:
            return
        if chat_id != ADMIN_CHAT_ID:
            return
        orders = load_app_orders()
        order = orders.get(cust_id)
        if not order:
            api("sendMessage", chat_id=chat_id,
                text=f"❌ No pending app order for {cust_id}.")
            return
        product, plan = order["product"], order["plan"]
        api("sendMessage", chat_id=cust_id,
            text=f"✅ Payment confirmed! Generating your {product} invite code… ⚡")
        ok, code, link = create_app_code(product, plan, cust_id)
        if ok:
            api("sendMessage", chat_id=cust_id,
                text=f"🎉 Your {product} is ready!\n\n"
                     f"📋 Plan: {plan}\n"
                     f"🔑 Invite code: `{code}`\n"
                     f"🔗 Or tap to redeem: {link}\n\n"
                     f"Enter the code in the app to activate.",
                parse_mode="Markdown")
            api("sendMessage", chat_id=chat_id,
                text=f"✅ {product} delivered to {cust_id} ({plan}, code {code}).")
        else:
            api("sendMessage", chat_id=chat_id,
                text=f"❌ Code generation failed for {cust_id} ({product}): {code}")
            api("sendMessage", chat_id=cust_id,
                text="⚠️ There was an issue generating your code. "
                     "Please contact @biggestseller1.")
        orders.pop(cust_id, None)
        save_app_orders(orders)
    elif data.startswith("appno:"):
        try:
            _, cust_id = data.split(":", 1)
        except ValueError:
            return
        if chat_id != ADMIN_CHAT_ID:
            return
        api("sendMessage", chat_id=cust_id,
            text="❌ We couldn't confirm your payment. Please contact @biggestseller1.")
        orders = load_app_orders()
        orders.pop(cust_id, None)
        save_app_orders(orders)


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
