#!/usr/bin/env python3
"""Copy data files from the Telegram bots into messenger-bots/data/.

Run this after any price/FAQ update so the Messenger bots stay in sync.
"""
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
COPIES = [
    ("/home/hatch/workspace/telegram-bot/faq.json", "faq.json"),
    ("/home/hatch/workspace/telegram-bot/thai-qr.jpg", "thai-qr.jpg"),
    ("/home/hatch/workspace/subscription-bot/catalog.json", "catalog.json"),
]

os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
for src, dst in COPIES:
    shutil.copy(src, os.path.join(BASE, "data", dst))
    print("synced", dst)
