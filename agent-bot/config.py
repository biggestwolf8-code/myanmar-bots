"""Shared configuration for the personal agent bot."""
import os
import secrets

DATA_DIR = os.environ.get("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "7061620871")

# Vultr VM access (SSH from the agent)
VULTR_HOST = os.environ.get("VULTR_HOST", "149.28.150.78")
VULTR_USER = os.environ.get("VULTR_USER", "root")
VULTR_PASSWORD = os.environ.get("VULTR_PASSWORD", "")

# VPN fleet: nickname -> {host, country, wireguard subnet}. Singapore is the
# original server; japan/uk/usa added 2026-10-17 for multi-country VPN sales.
VPN_SERVERS = {
    "singapore": {"host": "149.28.150.78", "country": "Singapore", "subnet": "10.8.0.0/24"},
    "japan":     {"host": "45.32.62.209",  "country": "Japan",     "subnet": "10.9.0.0/24"},
    "uk":        {"host": "136.244.65.38", "country": "UK",        "subnet": "10.10.0.0/24"},
    "usa":       {"host": "149.248.11.196", "country": "USA",       "subnet": "10.11.0.0/24"},
}

# Secret shared with the laptop companion worker. Generated once and
# persisted so it survives restarts; shown to the owner for worker setup.
def _worker_secret():
    path = os.path.join(DATA_DIR, "worker_secret.txt")
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read().strip()
    s = secrets.token_hex(16)
    with open(path, "w") as fh:
        fh.write(s)
    return s

WORKER_SECRET = os.environ.get("WORKER_SECRET", "") or _worker_secret()

# Secret for the private inbox that Muse (the main assistant) uses to send
# tasks to this agent. Set via env var; the endpoint stays disabled if empty.
# Arkar can read everything sent here with the /inbox command.
INBOX_SECRET = os.environ.get("INBOX_SECRET", "")

DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "500"))
MAX_AGENT_STEPS = int(os.environ.get("MAX_AGENT_STEPS", "12"))
HTTP_PORT = int(os.environ.get("PORT", "8080"))

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

MODEL_RATES = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (5.0, 25.0),
    "claude-fable-5-1": (10.0, 50.0),
}
