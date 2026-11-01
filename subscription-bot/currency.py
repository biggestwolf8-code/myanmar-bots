#!/usr/bin/env python3
"""Currency converter for Biggest Seller Myanmar.

Anchor rate (set by the owner, 2026-11-02): 1 USD = 50,000 MMK.
That rate lives in code (DEFAULT_RATES) so it survives redeploys.

Every other currency is stored as "MMK per 1 unit of that currency"
and converts through MMK as the hub, so adding a currency once makes
it convertible to/from every other currency — e.g. once THB is set
with /setrate, /convert can do THB <-> USD <-> MMK with no extra code.

Extra rates added by the admin (/setrate) are kept in rates.json next
to this file and loaded on top of the defaults at startup.
"""

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RATES_FILE = os.path.join(BASE_DIR, "rates.json")

# MMK per 1 unit. USD is the owner's fixed anchor rate.
DEFAULT_RATES = {
    "USD": 50000.0,
    "MMK": 1.0,
}

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
    extra = {k: v for k, v in rates.items() if k not in DEFAULT_RATES}
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
    lines.append("\nRate used: 1 USD = 50,000 Ks.")
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
