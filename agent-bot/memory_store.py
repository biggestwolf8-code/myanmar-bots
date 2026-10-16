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
VERSION_FILE = os.path.join(MEM_DIR, "memory_version.txt")
MEMORY_VERSION = 6

SEED_ADDITIONS = {
    2: """
## Resurrection kit (added 2026-10-16)
- Arkar's full context backup lives in the private GitHub repo biggestwolf8-code/arkar-context.
  RESURRECT.md there explains how to restore Muse in a new chat. The kit refreshes automatically.
- If Arkar says he lost Muse / wants to resurrect it, point him to that repo and to RESURRECT.md.
- You are his always-on fallback: you know the essentials and can keep working while he sets up a new Muse.
""",
    3: """
## WireGuard VPN on Vultr — in progress (added 2026-10-16)
- Goal: Arkar's own VPN on the Vultr VM (149.28.150.78, Ubuntu 22.04, Singapore) so his phone/laptop/tablet share a private Singapore IP. No third-party VPN subscription.
- Current state: wg-quick@wg0 is ACTIVE on the server, IPv4 forwarding is 1, NAT rules present, WireGuard listening. A client/server key mismatch was found and fixed (fresh phone keypair, server peer key updated). Listen port moved from UDP 51820 to UDP 443; UFW allows 443/udp. Vultr shows NO cloud firewall attached.
- Problem: the phone still cannot connect on Wi-Fi or mobile data. No successful handshake ever observed.
- Setup script: setup-vm.sh in biggestwolf8-code/myanmar-bots (run in Vultr console via curl). Client config at /root/wg-client.conf on the server.
- Next diagnostic step: packet capture on the server (tcpdump on UDP 443) to see whether the phone's packets even arrive.
- When Arkar says "continue the vpn thing", use the vultr tool to diagnose and fix. Check: `wg show`, `systemctl status wg-quick@wg0`, `ss -ulpn | grep 443`, iptables NAT/forward rules, then tcpdump while he retries from the phone. Iterate until handshake succeeds.
""",
    4: """
## Inbox from Muse (added 2026-10-16)
- Muse is Arkar's main assistant in the Muse app. It can send you tasks through a private inbox (POST /inbox).
- Inbox messages arrive prefixed "[Inbox from Muse]". Treat them exactly like Arkar's own requests — he set this up so he doesn't have to relay between you two.
- Arkar can read everything in the inbox with /inbox, and he sees each message echoed to him when it arrives. Stay transparent; nothing in the inbox is hidden from him.
- When you transcribe long keys or tokens from a message into a command or config, double-check every character — a single wrong character breaks keys silently.
""",
    6: """
## VPN customers — manual subscriptions (added 2026-10-16)
- Arkar sells VPN access as a subscription and provisions each customer manually with your help.
- Customer file: /data/vpn_customers.json — a JSON list of {name, public_key, vpn_ip, since, until, status}.
  Arkar's own phone is 10.8.0.2 (never touch it). Server is 10.8.0.1. Customers get 10.8.0.3 and up.
- ADD ("new VPN customer <name>, <N> days"):
  1. Read the customer file, pick the next free 10.8.0.x IP.
  2. On the server generate a keypair: `wg genkey | tee /tmp/vpn_<name>.key | wg pubkey`. Move keys only via shell variables and command substitution — never retype them.
  3. Append a [Peer] block (PublicKey=<pub>, AllowedIPs=<ip>/32) to /etc/wireguard/wg0.conf, then `systemctl restart wg-quick@wg0` and verify with `wg show`.
  4. Build the client config text: [Interface] PrivateKey=<new key>, Address=<ip>/32, DNS=1.1.1.1; [Peer] PublicKey=<server pubkey from `wg show wg0 public-key`>, Endpoint=149.28.150.78:443, AllowedIPs=0.0.0.0/0.
  5. Save it as vpn-<name>.conf in the workspace and send_file it to Arkar with short customer setup instructions (in the WireGuard app: + → Create from file or archive → pick the file → toggle on). Conf file only — no QR codes (Arkar's decision 2026-10-16).
  6. Record the customer in the JSON file with until=<N> days from today. Delete the /tmp key files afterwards.
  7. Schedule reminders: 2 days before expiry and on the expiry day itself.
- RENEW ("renew VPN customer <name> <N> days"): extend `until`, confirm, schedule fresh reminders.
- REMOVE ("remove VPN customer <name>"): confirm with Arkar first, then delete the [Peer] block containing their PublicKey from /etc/wireguard/wg0.conf, restart WireGuard, mark status revoked in the file.
- LIST ("list VPN customers"): show name, IP, expiry date, status.
- Pricing is Arkar's call — never quote prices yourself. If a customer doesn't pay, Arkar tells you to remove them.
""",
}


def ensure_seed():
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w", encoding="utf-8") as fh:
            fh.write(SEED_MEMORY)
            for v in range(1, MEMORY_VERSION + 1):
                if v in SEED_ADDITIONS:
                    fh.write(SEED_ADDITIONS[v])
        with open(VERSION_FILE, "w") as fh:
            fh.write(str(MEMORY_VERSION))
        return
    try:
        with open(VERSION_FILE) as fh:
            ver = int(fh.read().strip())
    except (OSError, ValueError):
        ver = 1
    if ver < MEMORY_VERSION:
        with open(MEMORY_FILE, "a", encoding="utf-8") as fh:
            for v in range(ver + 1, MEMORY_VERSION + 1):
                if v in SEED_ADDITIONS:
                    fh.write(SEED_ADDITIONS[v])
        with open(VERSION_FILE, "w") as fh:
            fh.write(str(MEMORY_VERSION))

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
