"""Biggest Seller VPN - backend API for the Android app and Telegram bot.

Endpoints:
  POST /api/login            {code} -> customer configs + expiry (used by the app)
  POST /api/admin/create     {admin_secret, name, telegram_id, days} -> {code, configs}
  POST /api/admin/renew      {admin_secret, code, days} -> {expires_at}
  POST /api/admin/revoke     {admin_secret, code} -> removes WireGuard peers
  GET  /api/admin/list       ?admin_secret=... -> customer list
  GET  /health               -> ok

WireGuard provisioning: SSH to each of the 4 VPN servers, add the client's
public key as a peer with the next free IP in that server's subnet.
"""
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CUSTOMERS_FILE = os.path.join(DATA_DIR, "vpn_customers.json")
SSH_KEY = os.path.join(DATA_DIR, "ssh", "id_ed25519")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")

# VPN fleet (mirrors agent-bot config)
SERVERS = {
    "singapore": {"host": "149.28.150.78", "country": "Singapore", "subnet": "10.8.0", "server_ip": "10.8.0.1"},
    "japan":     {"host": "45.32.62.209",  "country": "Japan",     "subnet": "10.9.0", "server_ip": "10.9.0.1"},
    "uk":        {"host": "136.244.65.38", "country": "UK",        "subnet": "10.10.0", "server_ip": "10.10.0.1"},
    "usa":       {"host": "149.248.11.196", "country": "USA",       "subnet": "10.11.0", "server_ip": "10.11.0.1"},
}
WG_PORT = 443
# .1 = server, .2 = Arkar's phone (Singapore only); customers start at .3
RESERVED_IPS = {"singapore": {"10.8.0.1", "10.8.0.2"}}

app = Flask(__name__)


def _load_customers():
    try:
        with open(CUSTOMERS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_customers(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CUSTOMERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, CUSTOMERS_FILE)


def _ssh_exec(host, command, timeout=30):
    """Run a command on a VPN server via SSH key. Returns (ok, output)."""
    import paramiko
    if not os.path.exists(SSH_KEY):
        return False, "SSH key not installed for vpn-api service."
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        pkey = paramiko.Ed25519Key.from_private_key_file(SSH_KEY)
        client.connect(host, username="root", pkey=pkey, timeout=15,
                       banner_timeout=15, auth_timeout=15)
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace").strip()
        err = stderr.read().decode("utf-8", "replace").strip()
        if code != 0:
            return False, f"exit {code}: {err or out}"
        return True, out
    except Exception as e:
        return False, f"SSH failed: {e}"
    finally:
        try:
            client.close()
        except Exception:
            pass


def _next_ip(server):
    """Next free client IP in the server's subnet.

    Consults the server's LIVE peer list (via SSH) as well as vpn-api's own
    customer file: the catalog bot and manual provisioning allocate from the
    same subnets, and their allocations are invisible to this file. Without
    the live check, vpn-api could hand out an IP another peer already owns
    (e.g. Singapore 10.8.0.3 = customer Nyi) and WireGuard would steal it.
    """
    customers = _load_customers()
    used = set(RESERVED_IPS.get(server, set()))
    for c in customers.values():
        ip = (c.get("ips") or {}).get(server)
        if ip:
            used.add(ip)
    ok, out = _ssh_exec(SERVERS[server]["host"], "wg show wg0 allowed-ips")
    if ok:
        for line in out.splitlines():
            parts = line.split()
            for p in parts[1:]:
                used.add(p.split("/")[0].rstrip(","))
    base = SERVERS[server]["subnet"]
    for i in range(3, 255):
        cand = f"{base}.{i}"
        if cand not in used:
            return cand
    return None


def _provision_customer(name, telegram_id, days):
    """Create WireGuard peers on all 4 servers. Returns (code, customer_dict)."""
    import paramiko  # noqa - ensures installed
    customers = _load_customers()
    code = secrets.token_urlsafe(9)  # ~12 char access code
    # One client keypair reused across all 4 servers (simpler for the app)
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    priv = X25519PrivateKey.generate()
    priv_b64 = serialization.Encoding.Raw
    import base64
    priv_raw = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    client_priv = base64.b64encode(priv_raw).decode()
    client_pub = base64.b64encode(pub_raw).decode()

    ips, server_pubs, configs = {}, {}, {}
    for srv, info in SERVERS.items():
        ip = _next_ip(srv)
        if not ip:
            raise RuntimeError(f"No free IPs on {srv}")
        # get server public key
        ok, out = _ssh_exec(info["host"], "wg show wg0 public-key")
        if not ok:
            raise RuntimeError(f"{srv}: cannot read server key: {out}")
        server_pub = out.strip()
        # add peer (persistent)
        cmd = (f"wg set wg0 peer {client_pub} allowed-ips {ip}/32 && "
               f"wg-quick save wg0 && echo OK")
        ok, out = _ssh_exec(info["host"], cmd)
        if not ok:
            raise RuntimeError(f"{srv}: failed to add peer: {out}")
        ips[srv] = ip
        server_pubs[srv] = server_pub
        configs[srv] = (
            f"[Interface]\nPrivateKey = {client_priv}\nAddress = {ip}/32\n"
            f"DNS = 1.1.1.1\n\n[Peer]\nPublicKey = {server_pub}\n"
            f"Endpoint = {info['host']}:{WG_PORT}\nAllowedIPs = 0.0.0.0/0\n"
            f"PersistentKeepalive = 25\n"
        )

    now = datetime.now(timezone.utc)
    customer = {
        "name": name,
        "telegram_id": telegram_id,
        "code": code,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "days": days,
        "ips": ips,
        "client_pub": client_pub,
        "configs": configs,
        "active": True,
    }
    customers[code] = customer
    _save_customers(customers)
    return code, customer, configs


def _require_admin(data):
    return bool(ADMIN_SECRET) and data.get("admin_secret") == ADMIN_SECRET


@app.get("/health")
def health():
    return jsonify(ok=True, service="vpn-api")


@app.post("/api/login")
def login():
    """App login: {code, device_id} -> configs + subscription status.

    Device control: a code allows up to max_devices (default 1) unique
    devices. The first devices to log in bind automatically; further
    unique devices are rejected (403). Admin can raise max_devices or
    unbind via the admin endpoints.
    """
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip()
    device_id = (data.get("device_id") or "").strip()
    customers = _load_customers()
    c = customers.get(code)
    if not c or not c.get("active"):
        return jsonify(ok=False, error="Invalid code."), 401
    exp = datetime.fromisoformat(c["expires_at"])
    now = datetime.now(timezone.utc)
    if now > exp:
        return jsonify(ok=False, error="Subscription expired."), 403

    # Migrate old single-device format
    if "device_ids" not in c:
        c["device_ids"] = [c.pop("device_id")] if c.get("device_id") else []
    max_devices = int(c.get("max_devices", 1))
    device_ids = c.get("device_ids", [])
    if device_id and device_id not in device_ids:
        if len(device_ids) >= max_devices:
            return jsonify(ok=False, error="This code has reached its device limit."), 403
        device_ids.append(device_id)
        c["device_ids"] = device_ids
        _save_customers(customers)

    days_left = (exp - now).days
    return jsonify(ok=True, name=c.get("name"), expires_at=c["expires_at"],
                   days_left=days_left, configs=c.get("configs", {}),
                   servers={k: v["country"] for k, v in SERVERS.items()})


@app.post("/api/admin/ssh-key")
def admin_ssh_key():
    """Install the SSH private key used for provisioning (one-time setup)."""
    data = request.get_json(force=True, silent=True) or {}
    if not _require_admin(data):
        return jsonify(ok=False, error="Unauthorized."), 403
    key = (data.get("private_key") or "").strip()
    if "PRIVATE KEY" not in key:
        return jsonify(ok=False, error="That doesn't look like a private key."), 400
    os.makedirs(os.path.dirname(SSH_KEY), exist_ok=True)
    with open(SSH_KEY, "w") as f:
        f.write(key + "\n")
    os.chmod(SSH_KEY, 0o600)
    return jsonify(ok=True, installed=True)


@app.post("/api/admin/create")
def admin_create():
    data = request.get_json(force=True, silent=True) or {}
    if not _require_admin(data):
        return jsonify(ok=False, error="Unauthorized."), 403
    name = (data.get("name") or "customer").strip()
    telegram_id = data.get("telegram_id")
    days = int(data.get("days", 30))
    try:
        max_devices = int(data.get("max_devices", 1))
    except (TypeError, ValueError):
        max_devices = 1
    if max_devices < 1:
        max_devices = 1
    try:
        code, customer, configs = _provision_customer(name, telegram_id, days)
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e)), 500
    # set device limit
    customers = _load_customers()
    customers[code]["max_devices"] = max_devices
    customers[code]["device_ids"] = []
    _save_customers(customers)
    return jsonify(ok=True, code=code, expires_at=customer["expires_at"],
                   max_devices=max_devices, configs=configs)


@app.post("/api/admin/renew")
def admin_renew():
    data = request.get_json(force=True, silent=True) or {}
    if not _require_admin(data):
        return jsonify(ok=False, error="Unauthorized."), 403
    customers = _load_customers()
    c = customers.get(data.get("code", ""))
    if not c:
        return jsonify(ok=False, error="Unknown code."), 404
    days = int(data.get("days", 30))
    exp = max(datetime.now(timezone.utc),
              datetime.fromisoformat(c["expires_at"]))
    c["expires_at"] = (exp + timedelta(days=days)).isoformat()
    c["active"] = True
    _save_customers(customers)
    return jsonify(ok=True, expires_at=c["expires_at"])


@app.post("/api/admin/revoke")
def admin_revoke():
    data = request.get_json(force=True, silent=True) or {}
    if not _require_admin(data):
        return jsonify(ok=False, error="Unauthorized."), 403
    customers = _load_customers()
    c = customers.pop(data.get("code", ""), None)
    if not c:
        return jsonify(ok=False, error="Unknown code."), 404
    # remove peers from all servers
    errors = []
    for srv, info in SERVERS.items():
        ok, out = _ssh_exec(info["host"],
                            f"wg set wg0 peer {c['client_pub']} remove && wg-quick save wg0 && echo OK")
        if not ok:
            errors.append(f"{srv}: {out}")
    _save_customers(customers)
    return jsonify(ok=True, errors=errors)


@app.post("/api/admin/unbind")
def admin_unbind():
    """Clear all device bindings for a code (e.g. customer got new phones)."""
    data = request.get_json(force=True, silent=True) or {}
    if not _require_admin(data):
        return jsonify(ok=False, error="Unauthorized."), 403
    customers = _load_customers()
    c = customers.get(data.get("code", ""))
    if not c:
        return jsonify(ok=False, error="Unknown code."), 404
    c.pop("device_id", None)
    c["device_ids"] = []
    _save_customers(customers)
    return jsonify(ok=True, unbound=True)


@app.post("/api/admin/set_max_devices")
def admin_set_max_devices():
    """Set how many devices a code allows (e.g. customer buys 2-device plan)."""
    data = request.get_json(force=True, silent=True) or {}
    if not _require_admin(data):
        return jsonify(ok=False, error="Unauthorized."), 403
    customers = _load_customers()
    c = customers.get(data.get("code", ""))
    if not c:
        return jsonify(ok=False, error="Unknown code."), 404
    try:
        n = int(data.get("max_devices", 1))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="max_devices must be a number."), 400
    if n < 1:
        return jsonify(ok=False, error="max_devices must be >= 1."), 400
    c["max_devices"] = n
    _save_customers(customers)
    return jsonify(ok=True, max_devices=n)


@app.get("/api/admin/list")
def admin_list():
    if request.args.get("admin_secret") != ADMIN_SECRET or not ADMIN_SECRET:
        return jsonify(ok=False, error="Unauthorized."), 403
    customers = _load_customers()
    out = [{"code": k, "name": v.get("name"), "expires_at": v.get("expires_at"),
            "active": v.get("active"),
            "device_ids": v.get("device_ids", []),
            "max_devices": v.get("max_devices", 1)}
           for k, v in customers.items()]
    return jsonify(ok=True, customers=out)


# ---------- simple admin web forms (same-origin, secret-gated) ----------
# For operators who hold the ADMIN_SECRET (e.g. via the Railway dashboard)
# but have no JSON tooling handy. Same secret check as the JSON API; the
# page itself contains no data.

_ADMIN_PAGE = """<!doctype html>
<title>vpn-api admin</title>
<h1>Biggest VPN - vpn-api admin</h1>
<h2>1. Install provisioning SSH key</h2>
<form method="post" action="/admin/install-key">
  <p><input type="password" name="admin_secret" placeholder="Admin secret" size="40"></p>
  <p><textarea name="private_key" rows="8" cols="64" placeholder="Paste the full private key"></textarea></p>
  <p><button type="submit">Install SSH key</button></p>
</form>
<h2>2. Create a customer code</h2>
<form method="post" action="/admin/create-code">
  <p><input type="password" name="admin_secret" placeholder="Admin secret" size="40"></p>
  <p><input type="text" name="name" placeholder="Customer name" size="40"></p>
  <p><input type="number" name="days" value="30" min="1" max="3650"> days</p>
  <p><button type="submit">Create code</button></p>
</form>
"""


@app.get("/admin")
def admin_page():
    return _ADMIN_PAGE


def _form_admin_ok():
    return bool(ADMIN_SECRET) and request.form.get("admin_secret") == ADMIN_SECRET


@app.post("/admin/install-key")
def admin_install_key_form():
    if not _form_admin_ok():
        return "Unauthorized.", 403
    key = (request.form.get("private_key") or "").strip()
    if "PRIVATE KEY" not in key:
        return "That doesn't look like a private key.", 400
    os.makedirs(os.path.dirname(SSH_KEY), exist_ok=True)
    with open(SSH_KEY, "w") as f:
        f.write(key + "\n")
    os.chmod(SSH_KEY, 0o600)
    return "SSH key installed."


@app.post("/admin/create-code")
def admin_create_code_form():
    import html
    if not _form_admin_ok():
        return "Unauthorized.", 403
    name = (request.form.get("name") or "customer").strip()
    try:
        days = int(request.form.get("days", 30))
    except ValueError:
        return "Days must be a number.", 400
    try:
        code, customer, configs = _provision_customer(name, None, days)
    except RuntimeError as e:
        return f"Provisioning failed: {html.escape(str(e))}", 500
    return (f"Code created for {html.escape(name)}: <b>{html.escape(code)}</b> "
            f"(expires {html.escape(customer['expires_at'])})")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
