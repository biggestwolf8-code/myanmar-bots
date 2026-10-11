"""Pure matching/formatting logic for the Messenger webhooks.

No network calls here — app.py handles all Messenger API I/O.
Data files (faq.json, catalog.json) are synced from the Telegram bots
via sync_data.py. The small SUB_FAQ list is duplicated from
~/workspace/subscription-bot/bot.py (kept in sync manually).
"""
import json
import os
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")


def norm(s):
    return unicodedata.normalize("NFC", s or "").lower().strip()


def load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def best_entry(entries, text):
    """Best keyword entry by hits, ties broken by keyword coverage."""
    t = norm(text)
    best, key = None, (0, 0)
    for e in entries:
        kws = e["keywords"]
        hits = sum(1 for k in kws if norm(k) and norm(k) in t)
        if not hits:
            continue
        k = (hits, hits / len(kws))
        if k > key:
            best, key = e, k
    return best


def search_products(catalog, query):
    # A match needs substance: the full query, a long word (>=4 chars),
    # or at least two short words — so "do you sell steam wallets?"
    # doesn't match Adobe/Windows/YouTube on "do"/"you".
    qt = norm(query)
    words = [w for w in qt.split() if len(w) > 1]
    if not words:
        return []
    names = sorted({it["product"] for it in catalog})
    scored = []
    for p in names:
        pn = norm(p)
        if len(qt) >= 3 and qt in pn:
            scored.append((p, 100))
            continue
        strong = sum(1 for w in words if len(w) >= 4 and w in pn)
        total = sum(1 for w in words if w in pn)
        if strong or total >= 2:
            scored.append((p, 100 if strong else total))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [p for p, _ in scored]


def product_text(catalog, product, contact):
    items = [it for it in catalog if it["product"] == product]
    lines = [f"📦 {product}"]
    for it in items:
        line = f"• {it['plan']} — {it['price_ks']:,} Ks"
        if it.get("notes"):
            line += f"\n  ({it['notes']})"
        lines.append(line)
    lines.append(f"\n📩 Order: {contact}")
    return "\n".join(lines)


def chunk(text, limit=1900):
    """Split a long message into Messenger-safe parts (2000 char limit)."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n"):
        if cur and len(cur) + len(para) + 1 > limit:
            parts.append(cur)
            cur = para
        else:
            cur = cur + "\n" + para if cur else para
    if cur:
        parts.append(cur)
    return parts


# Duplicated from ~/workspace/subscription-bot/bot.py
SUB_FAQ = [
    {"keywords": ["how can i pay", "how do i pay", "pay", "payment", "kbzpay",
                  "wavepay", "aya pay", "ayapay", "bank transfer", "qr",
                  "promptpay", "prompt pay", "ငွေပေး", "ငွေချေ"],
     "photo": None,
     "answer": (
         "💳 Payment methods:\n"
         "• KBZPay: 09403720481 (Arkar Myo Win)\n"
         "• WavePay: 09780695959 (Arkar Myo Win)\n"
         "• AYAPay: 09754926216 (Arkar Myowin)\n"
         "• Thailand: bank QR code\n\n"
         "⚠️ Please confirm the price with @biggestseller1 before paying, "
         "then send your receipt here. 🙏\n\n"
         "💳 ပေးချေနည်းများ:\n"
         "• KBZPay: 09403720481 (Arkar Myo Win)\n"
         "• WavePay: 09780695959 (Arkar Myo Win)\n"
         "• AYAPay: 09754926216 (Arkar Myowin)\n"
         "• ထိုင်း: ဘဏ် QR code\n\n"
         "⚠️ ငွေမလွှဲခင် @biggestseller1 နဲ့ ဈေးနှုန်းအတည်ပြုပါ၊ "
         "ပြီးရင် ပြေစာကို ဒီမှာပို့ပေးပါ။ 🙏")},
    {"keywords": ["warranty", "guarantee", "refund", "replacement", "အာမခံ"],
     "photo": None,
     "answer": (
         "✅ 100% warranty for the full subscription period — if your account "
         "has any problem, contact @biggestseller1 for a fix or replacement.\n\n"
         "✅ Subscription ကာလအပြည့်အဝ 100% warranty ပေးပါတယ် — "
         "ပြဿနာရှိရင် @biggestseller1 ကို ဆက်သွယ်ပါ။")},
    {"keywords": ["reseller", "resell", "20%"],
     "photo": None,
     "answer": (
         "🤝 Resellers get 20% off! Message @biggestseller1 for reseller details.\n\n"
         "🤝 Reseller များအတွက် 20% off ပေးပါတယ်! "
         "အသေးစိတ်ကို @biggestseller1 ကို ဆက်သွယ်ပါ။")},
]
