#!/usr/bin/env python3
"""
Messenger webhook server for both businesses.

- /webhook/english      -> MasterClass English FAQ bot
- /webhook/subscription -> Biggest Seller Myanmar catalog bot

Each bot reuses the same answers/catalog as its Telegram twin (see
sync_data.py). Unknown questions and receipt photos are forwarded to the
admin; the admin replies (using Messenger's reply/quote) to send the
answer back to the customer.

Env vars:
    VERIFY_TOKEN_ENGLISH / VERIFY_TOKEN_SUBSCRIPTION  - any random string you
        invent; paste the same into the Meta webhook setup
    PAGE_TOKEN_ENGLISH / PAGE_TOKEN_SUBSCRIPTION      - Page access token from
        the Meta developer dashboard (per bot's Facebook Page)
    ADMIN_PSID_ENGLISH / ADMIN_PSID_SUBSCRIPTION      - the admin's page-scoped
        user id (they must message the Page once first)
    CONTACT_USERNAME - order contact for the catalog bot (default @biggestseller1)
    PORT - listen port (default 5000)
"""

import json
import os

import requests
from flask import Flask, request

import brains

GRAPH = "https://graph.facebook.com/v21.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "relay_map.json")


def cfg(prefix):
    return {
        "verify": os.environ.get(f"VERIFY_TOKEN_{prefix}", ""),
        "page_token": os.environ.get(f"PAGE_TOKEN_{prefix}", ""),
        "admin_psid": os.environ.get(f"ADMIN_PSID_{prefix}", ""),
    }


BOTS = {"english": cfg("ENGLISH"), "subscription": cfg("SUBSCRIPTION")}
CONTACT = os.environ.get("CONTACT_USERNAME", "@biggestseller1").strip() or "@biggestseller1"

EN_FAQ = brains.load_json("faq.json")["entries"]
CATALOG = brains.load_json("catalog.json")
CATS = sorted({it["category"] for it in CATALOG})
PRODUCTS = {c: sorted({it["product"] for it in CATALOG if it["category"] == c})
            for c in CATS}

EN_WELCOME = (
    "Hello! Welcome to MasterClass English by Sayar Arkar. 🙏\n"
    "Tap a topic or just type your question.\n\n"
    "မင်္ဂလာပါ! MasterClass English by Sayar Arkar မှ ကြိုဆိုပါတယ်။ 🙏\n"
    "ခေါင်းစဉ်တစ်ခုရွေးပါ သို့မဟုတ် မေးခွန်းရိုက်ထည့်ပါ။"
)
EN_FALLBACK = (
    "Thanks! I've passed your message to Sayar Arkar — he'll reply here soon. 🙏\n"
    "ကျေးဇူးပါ! မေးခွန်းကို ဆရာ့ထံပို့ပေးလိုက်ပါပြီ — မကြာခင် ဒီမှာပဲ ပြန်ဖြေပေးပါမယ်။ 🙏"
)
SUB_WELCOME = (
    "👋 Biggest Seller Myanmar မှ ကြိုဆိုပါတယ်!\n"
    "Category ရွေးပါ သို့မဟုတ် နာမည်ရိုက်ရှာပါ (ဥပမာ 'spotify').\n\n"
    "👋 Welcome to Biggest Seller Myanmar!\n"
    "Pick a category or type a product name (e.g. 'spotify')."
)
SUB_FALLBACK = (
    "Thanks! I've passed your question to the admin — they'll reply here soon. 🙏\n"
    "ကျေးဇူးပါ! မေးခွန်းကို admin ထံပို့ပေးလိုက်ပါပြီ — မကြာခင် ဒီမှာပဲ ပြန်ဖြေပေးပါမယ်။ 🙏"
)
RECEIPT_MSG = (
    "📸 Receipt received! The admin will check it and confirm here soon. 🙏\n"
    "📸 ပြေစာရရှိပါပြီ! Admin စစ်ဆေးပြီး ဒီမှာပဲ အတည်ပြုပေးပါမယ်။ 🙏"
)
GREETINGS = {"hi", "hello", "hey", "start", "/start", "မင်္ဂလာပါ"}

app = Flask(__name__)


# ---------- state ----------

def load_map():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_map(m):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(m, f)


# ---------- send ----------

def send(bot, psid, message):
    """Send a message dict via the Send API. Returns the API response."""
    tok = BOTS[bot]["page_token"]
    if not tok:
        print(f"[{bot}] no PAGE_TOKEN — would send to {psid}: {str(message)[:100]}")
        return {}
    try:
        r = requests.post(
            f"{GRAPH}/me/messages",
            params={"access_token": tok},
            json={"recipient": {"id": psid}, "message": message},
            timeout=30,
        )
        data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[{bot}] send failed:", e)
        return {}
    if not data.get("message_id"):
        print(f"[{bot}] send error:", str(data)[:200])
    return data


def send_text(bot, psid, text, quick_replies=None):
    first = True
    for part in brains.chunk(text):
        msg = {"text": part}
        if quick_replies and first:
            msg["quick_replies"] = quick_replies
        send(bot, psid, msg)
        first = False


def qr(title, payload):
    return {"content_type": "text", "title": title, "payload": payload}


def cats_qr():
    return [qr(c, f"CAT:{i}") for i, c in enumerate(CATS)]


def prods_qr(ci):
    return [qr(p, f"PROD:{ci}:{j}") for j, p in enumerate(PRODUCTS[CATS[ci]])]


def topics_qr():
    return [qr("📚 Courses", "FAQ:courses"), qr("💰 Fees", "FAQ:fees"),
            qr("📝 Enroll", "FAQ:enroll"), qr("🕐 Schedule", "FAQ:schedule"),
            qr("💳 Pay", "FAQ:howpay")]


# ---------- admin relay ----------

def forward_to_admin(bot, customer_psid, text=None, image_url=None):
    """Forward a customer message to the admin; remember the mapping."""
    admin = BOTS[bot]["admin_psid"]
    if not admin:
        print(f"[{bot}] no ADMIN_PSID — cannot forward")
        return
    fwd = load_map()
    mids = []
    if image_url:
        r = send(bot, admin, {"attachment": {"type": "image",
              "payload": {"url": image_url, "is_reusable": True}}})
        if r.get("message_id"):
            mids.append(r["message_id"])
    note = "📩 New customer message:\n\n" + (text or "(photo)")
    r = send(bot, admin, {"text": note})
    if r.get("message_id"):
        mids.append(r["message_id"])
    for mid in mids:
        fwd[mid] = customer_psid
    save_map(fwd)


def relay_admin_reply(bot, msg):
    """If the admin quoted a forwarded message, relay their reply to the customer."""
    reply_mid = (msg.get("reply_to") or {}).get("mid")
    if not reply_mid:
        return False
    customer = load_map().get(reply_mid)
    if not customer:
        return False
    text = msg.get("text", "")
    if text:
        send_text(bot, customer, text)
    for a in msg.get("attachments", []) or []:
        if a.get("type") == "image" and (a.get("payload") or {}).get("url"):
            send(bot, customer, {"attachment": {"type": "image", "payload": {
                "url": a["payload"]["url"], "is_reusable": True}}})
    return True


# ---------- english bot ----------

def handle_english(psid, msg, is_admin):
    text = msg.get("text", "") or ""
    payload = (msg.get("quick_reply") or {}).get("payload", "")

    if payload.startswith("FAQ:"):
        eid = payload[4:]
        entry = next((e for e in EN_FAQ if e.get("id") == eid), None)
        if entry and not entry.get("forward"):
            send_text("english", psid, entry["answer"])
            return

    if is_admin and relay_admin_reply("english", msg):
        return

    images = [a for a in (msg.get("attachments") or [])
              if a.get("type") == "image"]
    if images:
        if not is_admin:
            for im in images:
                url = (im.get("payload") or {}).get("url")
                if url:
                    forward_to_admin("english", psid, image_url=url)
            send_text("english", psid, RECEIPT_MSG)
        return

    if brains.norm(text) in GREETINGS:
        send_text("english", psid, EN_WELCOME, topics_qr())
        return

    entry = brains.best_entry(EN_FAQ, text)
    if entry and not entry.get("forward"):
        send_text("english", psid, entry["answer"])
    elif is_admin:
        send_text("english", psid, "(Admin note: no FAQ answer matched — "
                  "a customer asking this would be forwarded to you.)")
    else:
        forward_to_admin("english", psid, text=text)
        send_text("english", psid, EN_FALLBACK)


# ---------- subscription bot ----------

def prod_payload(product):
    for ci, c in enumerate(CATS):
        if product in PRODUCTS[c]:
            return f"PROD:{ci}:{PRODUCTS[c].index(product)}"
    return "HOME"


def handle_subscription(psid, msg, is_admin):
    text = msg.get("text", "") or ""
    payload = (msg.get("quick_reply") or {}).get("payload", "")

    if payload == "HOME":
        send_text("subscription", psid, SUB_WELCOME, cats_qr())
        return
    if payload.startswith("CAT:"):
        try:
            ci = int(payload[4:])
            send_text("subscription", psid,
                      f"📂 {CATS[ci]} — choose a product:", prods_qr(ci))
        except (ValueError, IndexError):
            pass
        return
    if payload.startswith("PROD:"):
        try:
            _, ci, j = payload.split(":")
            product = PRODUCTS[CATS[int(ci)]][int(j)]
            send_text("subscription", psid,
                      brains.product_text(CATALOG, product, CONTACT))
        except (ValueError, IndexError, KeyError):
            pass
        return

    if is_admin and relay_admin_reply("subscription", msg):
        return

    images = [a for a in (msg.get("attachments") or [])
              if a.get("type") == "image"]
    if images:
        if not is_admin:
            for im in images:
                url = (im.get("payload") or {}).get("url")
                if url:
                    forward_to_admin("subscription", psid, image_url=url)
            send_text("subscription", psid, RECEIPT_MSG)
        return

    if brains.norm(text) in GREETINGS:
        send_text("subscription", psid, SUB_WELCOME, cats_qr())
        return

    faq = brains.best_entry(brains.SUB_FAQ, text)
    if faq:
        # NOTE: Thai QR photo is Telegram-only for now; text answer here.
        send_text("subscription", psid, faq["answer"])
        return

    matches = brains.search_products(CATALOG, text)
    if len(matches) == 1:
        send_text("subscription", psid,
                  brains.product_text(CATALOG, matches[0], CONTACT))
    elif matches:
        rows = [qr(p, prod_payload(p)) for p in matches[:8]]
        send_text("subscription", psid, "Found these — tap one:", rows)
    elif is_admin:
        send_text("subscription", psid, "(Admin note: no product matched — "
                  "a customer asking this would be forwarded to you.)")
    else:
        forward_to_admin("subscription", psid, text=text)
        send_text("subscription", psid, SUB_FALLBACK)


# ---------- webhook ----------

@app.get("/webhook/<bot>")
def verify(bot):
    if bot not in BOTS:
        return "unknown bot", 404
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == BOTS[bot]["verify"]):
        return request.args.get("hub.challenge", ""), 200
    return "forbidden", 403


@app.post("/webhook/<bot>")
def incoming(bot):
    if bot not in BOTS:
        return "unknown bot", 404
    data = request.get_json(force=True, silent=True) or {}
    if data.get("object") != "page":
        return "ok", 200
    for entry in data.get("entry", []):
        for m in entry.get("messaging", []):
            msg = m.get("message") or {}
            if msg.get("is_echo"):
                continue
            psid = str((m.get("sender") or {}).get("id", ""))
            if not psid:
                continue
            is_admin = bool(BOTS[bot]["admin_psid"]) and psid == BOTS[bot]["admin_psid"]
            if bot == "english":
                handle_english(psid, msg, is_admin)
            else:
                handle_subscription(psid, msg, is_admin)
    return "ok", 200


@app.get("/")
def index():
    return "Messenger bots running. Webhooks at /webhook/english and /webhook/subscription.", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
