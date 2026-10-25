"""Biggest VPN - WireGuard provisioning for the subscription bot.

Provisions a customer across all 4 VPN servers via SSH:
  - generates one client keypair (reused on all servers)
  - adds the peer to each server's wg0 (persistent via wg-quick save)
  - returns 4 .conf file contents keyed by country

Customer records live in vpn_customers.json next to this file.
"""
import base64
import json
import os
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOMERS_FILE = os.path.join(BASE_DIR, "vpn_customers.json")
SSH_KEY = os.path.join(BASE_DIR, "vpn_ssh_key")


def _ensure_ssh_key():
    """Write the SSH private key from the VPN_SSH_KEY env var if not on disk.
    Railway doesn't get the key from git (it's gitignored), so it must be
    set as an env var on the service."""
    if os.path.exists(SSH_KEY):
        return True
    key_data = os.environ.get("VPN_SSH_KEY", "").strip()
    if not key_data:
        return False
    # env var may have literal \n if pasted awkwardly
    key_data = key_data.replace("\\n", "\n")
    if not key_data.endswith("\n"):
        key_data += "\n"
    with open(SSH_KEY, "w", encoding="utf-8") as fh:
        fh.write(key_data)
    os.chmod(SSH_KEY, 0o600)
    return True

SERVERS = {
    "singapore": {"host": "149.28.150.78", "country": "Singapore",
                  "subnet": "10.8.0", "server_ip": "10.8.0.1"},
    "japan":     {"host": "45.32.62.209",  "country": "Japan",
                  "subnet": "10.9.0", "server_ip": "10.9.0.1"},
    "uk":        {"host": "136.244.65.38", "country": "UK",
                  "subnet": "10.10.0", "server_ip": "10.10.0.1"},
    "usa":       {"host": "149.248.11.196", "country": "USA",
                  "subnet": "10.11.0", "server_ip": "10.11.0.1"},
}
WG_PORT = 443
# .1 = server; Singapore .2 = Arkar's phone (never touch)
RESERVED = {"singapore": {"10.8.0.1", "10.8.0.2"},
            "japan": {"10.9.0.1"}, "uk": {"10.10.0.1"}, "usa": {"10.11.0.1"}}

# plan label -> days
TRIAL_PLAN = "7-Day Trial / 1 Device"
PLANS = {
    TRIAL_PLAN: 7,
    "1 Month / 1 Device": 30,
    "3 Months / 1 Device": 90,
    "6 Months / 1 Device": 180,
    "1 Year / 1 Device": 365,
}

# One trial per Telegram ID, ever — recorded separately from
# vpn_customers.json, because revoke() deletes the customer record on
# expiry. Without this file, an expired trial customer could claim again.
TRIALS_FILE = os.path.join(BASE_DIR, "vpn_trials.json")


def _load_trials():
    try:
        with open(TRIALS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_trials(data):
    tmp = TRIALS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, TRIALS_FILE)


def has_used_trial(telegram_id):
    return str(telegram_id) in _load_trials()


def mark_trial_used(telegram_id, code, expires_at):
    trials = _load_trials()
    trials[str(telegram_id)] = {
        "code": code, "expires_at": expires_at,
        "used_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_trials(trials)


def _load():
    try:
        with open(CUSTOMERS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save(data):
    tmp = CUSTOMERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, CUSTOMERS_FILE)


def _ssh(host, command, timeout=30):
    import paramiko
    if not _ensure_ssh_key():
        return False, "VPN SSH key not installed (set VPN_SSH_KEY env var)."
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        pkey = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        c.connect(host, username="root", pkey=pkey, timeout=15,
                  banner_timeout=15, auth_timeout=15)
        _, out, err = c.exec_command(command, timeout=timeout)
        code = out.channel.recv_exit_status()
        o = out.read().decode("utf-8", "replace").strip()
        e = err.read().decode("utf-8", "replace").strip()
        return (True, o) if code == 0 else (False, f"exit {code}: {e or o}")
    except Exception as ex:
        return False, f"SSH failed: {ex}"
    finally:
        try:
            c.close()
        except Exception:
            pass


def _next_ip(server):
    """Next free client IP in the server's subnet.

    Consults the server's LIVE peer list (via SSH) as well as the bot's own
    customer file: vpn-api sales and manual provisioning allocate from the
    same subnets, and their allocations are invisible to this file. Without
    the live check, the bot could hand out an IP another peer already owns
    (e.g. Singapore 10.8.0.3 = customer Nyi) and WireGuard would steal it.
    """
    used = set(RESERVED.get(server, set()))
    for cust in _load().values():
        ip = (cust.get("ips") or {}).get(server)
        if ip:
            used.add(ip)
    ok, out = _ssh(SERVERS[server]["host"], "wg show wg0 allowed-ips")
    if ok:
        for line in out.splitlines():
            parts = line.split()
            for p in parts[1:]:
                for ip in p.split(","):
                    used.add(ip.split("/")[0].strip())
    base = SERVERS[server]["subnet"]
    for i in range(3, 255):
        cand = f"{base}.{i}"
        if cand not in used:
            return cand
    return None


def provision(name, telegram_id, plan_label):
    """Create a VPN customer on all 4 servers.

    Returns (ok, result): result is a dict with code, configs, expires_at
    on success, or an error string on failure.
    """
    days = PLANS.get(plan_label)
    if not days:
        return False, f"Unknown plan: {plan_label}"
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey)
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return False, "cryptography lib not installed."

    priv = X25519PrivateKey.generate()
    raw_priv = priv.private_bytes(serialization.Encoding.Raw,
                                  serialization.PrivateFormat.Raw,
                                  serialization.NoEncryption())
    raw_pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    client_priv = base64.b64encode(raw_priv).decode()
    client_pub = base64.b64encode(raw_pub).decode()

    ips, configs = {}, {}
    for srv, info in SERVERS.items():
        ip = _next_ip(srv)
        if not ip:
            return False, f"No free IPs on {srv}."
        ok, srv_pub = _ssh(info["host"], "wg show wg0 public-key")
        if not ok:
            return False, f"{srv}: {srv_pub}"
        ok, out = _ssh(info["host"],
                       f"wg set wg0 peer {client_pub} allowed-ips {ip}/32 "
                       f"&& wg-quick save wg0 && echo OK")
        if not ok:
            return False, f"{srv}: {out}"
        ips[srv] = ip
        configs[srv] = (
            f"[Interface]\nPrivateKey = {client_priv}\nAddress = {ip}/32\n"
            f"DNS = 1.1.1.1\n\n[Peer]\nPublicKey = {srv_pub.strip()}\n"
            f"Endpoint = {info['host']}:{WG_PORT}\nAllowedIPs = 0.0.0.0/0\n"
            f"PersistentKeepalive = 25\n")

    now = datetime.now(timezone.utc)
    customers = _load()
    # simple numeric code, easier to read over chat than token_urlsafe
    import random
    code = f"VPN-{random.randint(100000, 999999)}"
    while code in customers:
        code = f"VPN-{random.randint(100000, 999999)}"
    customers[code] = {
        "name": name, "telegram_id": str(telegram_id), "plan": plan_label,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "ips": ips, "client_pub": client_pub, "active": True,
        "trial": plan_label == TRIAL_PLAN,
    }
    _save(customers)
    return True, {"code": code, "configs": configs,
                  "expires_at": customers[code]["expires_at"],
                  "countries": [SERVERS[s]["country"] for s in SERVERS]}


def revoke(code):
    """Remove a customer's peers from all servers."""
    customers = _load()
    cust = customers.pop(code, None)
    if not cust:
        return False, "Unknown code."
    errors = []
    for srv, info in SERVERS.items():
        ok, out = _ssh(info["host"],
                       f"wg set wg0 peer {cust['client_pub']} remove "
                       f"&& wg-quick save wg0 && echo OK")
        if not ok:
            errors.append(f"{srv}: {out}")
    _save(customers)
    return True, errors


def renew(code, days):
    """Extend a subscription. The existing .conf files keep working —
    only the expiry date changes. Returns (ok, new_expires_at_or_error)."""
    customers = _load()
    cust = customers.get(code)
    if not cust:
        return False, "Unknown code."
    days = int(days)
    exp = max(datetime.now(timezone.utc),
              datetime.fromisoformat(cust["expires_at"]))
    new_exp = exp + timedelta(days=days)
    cust["expires_at"] = new_exp.isoformat()
    cust["active"] = True
    _save(customers)
    return True, new_exp.isoformat()


def expire_due_trials():
    """Revoke every trial whose expiry has passed.

    Returns a list of {code, telegram_id, name, errors} for the customers
    revoked, so the caller can notify them. Paid plans are never touched
    here — only records flagged trial=True.
    """
    now = datetime.now(timezone.utc)
    due = []
    for code, cust in _load().items():
        if not cust.get("trial") or not cust.get("active"):
            continue
        try:
            exp = datetime.fromisoformat(cust["expires_at"])
        except (ValueError, TypeError):
            continue
        if exp <= now:
            due.append((code, cust))
    revoked = []
    for code, cust in due:
        ok, errors = revoke(code)
        if ok:
            revoked.append({"code": code,
                            "telegram_id": cust.get("telegram_id"),
                            "name": cust.get("name"), "errors": errors})
    return revoked


def list_trials():
    return {k: v for k, v in _load().items() if v.get("trial")}


def get(code):
    return _load().get(code)


def list_active():
    return {k: v for k, v in _load().items() if v.get("active")}
