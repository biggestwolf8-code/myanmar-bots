#!/usr/bin/env python3
"""Currency converter for the Masterclass Practice Bot.

Same rate structure as the Biggest Seller converter, anchored to
THIS bot's own prices (2 months = 50,000 Ks / 350 baht, about $10),
so 1 USD = 5,000 Ks — the same anchor the catalogue uses since the
owner corrected its 50,000 typo on 2026-11-03. Rates are stored as
"MMK per 1 unit" and converted through MMK as the hub. The Practice
Bot has no /updaterates command, so these rates only change by
editing this file.
"""

import json
import os
import re
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RATES_FILE = os.path.join(BASE_DIR, "rates.json")

# MMK per 1 unit. Anchor 1 USD = 5,000 Ks (this bot's own prices);
# every other rate is the Biggest Seller rate divided by 10.
DEFAULT_RATES = {
    "USD": 5000.0,
    "MMK": 1.0,
    "THB": 148.19,
    "SGD": 3906.25,
    "EUR": 5580.36,
    "GBP": 6693.44,
    "JPY": 31.75,
    "CNY": 749.63,
    "INR": 52.60,
    "AUD": 3521.13,
    "KRW": 3.75,
    "VND": 0.19,
    "MYR": 1231.53,
    "PHP": 78.48,
    "AED": 1362.40,
    "CAD": 3571.43,
    "NZD": 2808.99,
    "HKD": 636.94,
    "LAK": 0.22,
    "KHR": 1.23,
}

# Currencies to pull from the online USD feed when refreshing.
ONLINE_CURRENCIES = [c for c in DEFAULT_RATES if c not in ("USD", "MMK")]


def fetch_online_rates():
    """Fetch live USD rates online and derive MMK per unit from the
    this bot's 5,000 Ks anchor. Returns (rates_dict, source_date)."""
    with urllib.request.urlopen(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=15) as r:
        data = json.loads(r.read().decode())
    usd_rates = data["rates"]
    derived = {}
    for code in ONLINE_CURRENCIES:
        per_usd = usd_rates.get(code)
        if per_usd:
            derived[code] = round(5000.0 / per_usd, 2)
    if not derived:
        raise ValueError("Online feed returned no usable rates")
    return derived, data.get("date", "unknown")

ALIASES = {
    "$": "USD", "US$": "USD", "DOLLAR": "USD", "DOLLARS": "USD",
    "K": "MMK", "KS": "MMK", "KYAT": "MMK", "KYATS": "MMK",
    "MMK": "MMK", "MMM": "MMK", "MYANMAR": "MMK",
    "THB": "THB", "BAHT": "THB", "฿": "THB",
}


def norm_code(code):
    code = (code or "").strip().upper()
    return ALIASES.get(code, code)


def load_rates():
    rates = dict(DEFAULT_RATES)
    try:
        with open(RATES_FILE, encoding="utf-8") as f:
            extra = json.load(f)
        for k, v in extra.items():
            if isinstance(v, (int, float)) and v > 0:
                rates[norm_code(k)] = float(v)
    except (OSError, ValueError):
        pass
    return rates


def save_rates(rates):
    # Save every non-anchor currency, including refreshed values that
    # override a default — otherwise /updaterates would not stick.
    extra = {k: v for k, v in rates.items() if k not in ("USD", "MMK")}
    tmp = RATES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(extra, f, indent=2)
    os.replace(tmp, RATES_FILE)


def convert(amount, from_code, to_code, rates=None):
    """Convert amount from one currency to another via the MMK hub.
    Returns (value, from_code, to_code) or raises ValueError for an
    unknown currency."""
    rates = rates or load_rates()
    src, dst = norm_code(from_code), norm_code(to_code)
    if src not in rates:
        raise ValueError(f"Unknown currency: {from_code}")
    if dst not in rates:
        raise ValueError(f"Unknown currency: {to_code}")
    mmk = amount * rates[src]
    return mmk / rates[dst], src, dst


def fmt(amount, code):
    if code == "MMK":
        return f"{amount:,.0f} Ks"
    return f"{amount:,.2f} {code}"


def convert_all_text(amount, from_code, rates=None):
    """One amount converted into every known currency."""
    rates = rates or load_rates()
    src = norm_code(from_code)
    if src not in rates:
        known = ", ".join(sorted(rates))
        return (f"❌ Unknown currency '{from_code}'.\n"
                f"Known currencies: {known}\n"
                f"Admin can add one with: /setrate CODE mmk_per_unit\n"
                f"(e.g. /setrate THB 1500)")
    lines = [f"💱 {fmt(amount, src)} equals:"]
    for code in sorted(rates):
        if code == src:
            continue
        value, _, _ = convert(amount, src, code, rates)
        lines.append(f"• {fmt(value, code)}")
    lines.append("\nRate used: 1 USD = 5,000 Ks.")
    return "\n".join(lines)


def parse_convert(text):
    """Parse '/convert 10 USD', '/convert 500000 Ks to USD', etc.
    Returns (amount, from_code, to_code_or_None) or None if unparseable."""
    m = re.match(
        r"^/convert\s+([\d,]+(?:\.\d+)?)\s*([A-Za-z$฿]+)"
        r"(?:\s+to\s+([A-Za-z$฿]+))?\s*$",
        text.strip(), re.IGNORECASE)
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    return amount, m.group(2), m.group(3)
