"""Persistent memory + conversation history for the personal agent.

memory/MEMORY.md  - long-term facts, seeded with what we know about Arkar
history/<chat_id>.json - recent conversation per chat (trimmed)
"""
import json
import os
import time

import config

MEM_DIR = os.path.join(config.DATA_DIR, "memory")
HIST_DIR = os.path.join(config.DATA_DIR, "history")
os.makedirs(MEM_DIR, exist_ok=True)
os.makedirs(HIST_DIR, exist_ok=True)

MEMORY_FILE = os.path.join(MEM_DIR, "MEMORY.md")

SEED_MEMORY = """# Agent memory — Arkar Myowin

- Owner: Arkar Myowin. Telegram user id 8028025915. Timezone Asia/Bangkok.
- Speaks English and Burmese (Myanmar). Learning Thai.
- Runs "MasterClass English By Sayar Arkar" — online English courses for Myanmar learners.
- Runs "Biggest Seller Myanmar" — digital subscription reselling (Telegram channel, ~3.5K subscribers).
- Infra: Vultr VM in Singapore (Ubuntu 22.04, IP 149.28.150.78) for VPN and services; many Telegram bots and web apps on Railway.
- Windows laptop user, beginner with terminals — explain things simply, avoid jargon.
- Prefers done-for-you handling: do the work, report concisely what was done.
- Cost-sensitive about API usage; report roughly what things cost when relevant.
- For customer-facing Burmese wording, always have Arkar verify before finalizing.
- Honest positioning only: never imply his API apps are official Anthropic/OpenAI products.
- This agent can run commands on the Vultr server (vultr tool) and on Arkar's Windows laptop
  (laptop tool, only while his companion program is running). Confirm before destructive
  actions (deleting data, changing system config, rebooting).
"""


def ensure_seed():
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w", encoding="utf-8") as fh:
            fh.write(SEED_MEMORY)


def read_memory():
    ensure_seed()
    with open(MEMORY_FILE, encoding="utf-8") as fh:
        return fh.read()


def append_memory(entry):
    """Append a timestamped fact to long-term memory."""
    ensure_seed()
    ts = time.strftime("%Y-%m-%d")
    with open(MEMORY_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"\n- {ts}: {entry.strip()}\n")
    return True


def _hist_path(chat_id):
    return os.path.join(HIST_DIR, f"{chat_id}.json")


def load_history(chat_id, limit=30):
    try:
        with open(_hist_path(chat_id), encoding="utf-8") as fh:
            data = json.load(fh)
        return data[-limit:]
    except (OSError, ValueError):
        return []


def save_history(chat_id, history):
    try:
        with open(_hist_path(chat_id), "w", encoding="utf-8") as fh:
            json.dump(history[-60:], fh)
    except OSError:
        pass


def clear_history(chat_id):
    try:
        os.remove(_hist_path(chat_id))
    except OSError:
        pass
