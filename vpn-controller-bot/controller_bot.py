"""
vpn-v2 controller bot — Telegram provisioning bot (requests long polling).

What it does:
  * /start shows region buttons (UDP + Stealth 443) and Smart Location.
  * Tapping a button provisions an ephemeral WireGuard peer on the chosen
    node (via the node's TLS agent API), then sends the user a QR code
    and a .conf file.
  * Smart Location picks the online node with the fewest active peers.

What it does NOT do (yet):
  * Payments / subscriptions. See the TODO in provision_tunnel() — the
    existing subscription bot owns plans, prices and payment methods
    (KBZPay / WavePay / AYAPay). This controller is provisioning-only
    for now; do NOT invent prices here.

How node TLS works (see README.md for the full story):
  * Each node serves its agent API over TLS with a self-signed cert.
  * The operator copies each node's /opt/vpn-agent/cert.pem to the
    controller host (certs/<region>-cert.pem). httpx trusts ONLY that
    exact cert file for that node — that is certificate pinning.
  * The agent's /health also reports the cert's SHA-256 fingerprint.
    If VPN_NODE_FP_<REGION> is set, a mismatch refuses provisioning.

Configuration (environment, see .env.example):
  TELEGRAM_BOT_TOKEN    BotFather token for this bot.
  AGENT_API_SECRET      Shared secret for the node agent API (x-api-key).
  VPN_NODE_<CODE>       Public IP of each node, e.g. VPN_NODE_SG.
  VPN_NODE_CERT_<CODE>  Path to that node's TLS cert PEM.
  VPN_NODE_FP_<CODE>    Expected SHA-256 fingerprint of that node's cert.

Run:  python3 controller_bot.py
"""

import base64
import io
import ipaddress
import logging
import os
import time

import httpx
import qrcode
import requests
from nacl.public import PrivateKey

# ---------------------------------------------------------------- config ---

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
AGENT_API_SECRET = os.environ.get("AGENT_API_SECRET", "")
BOT_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Node IPs are placeholders (TEST-NET-3, 203.0.113.0/24). Replace with the
# real node IPs from Terraform output / the Vultr panel via .env.
NODES = {
    "sg": {
        "name": "Singapore",
        "ip": os.environ.get("VPN_NODE_SG", "203.0.113.10"),
        "cert": os.environ.get("VPN_NODE_CERT_SG", "certs/sg-cert.pem"),
        "fingerprint": os.environ.get("VPN_NODE_FP_SG", ""),
    },
}
# Other regions (us/uk/nl) are added here as nodes come online. The
# placeholders were removed so the bot never offers a region with no node.

# Ephemeral in-memory IP allocator per region (never written to disk).
# 10.66.66.1 is the gateway; the pool is .2 - .254.
SUBNET = ipaddress.ip_network("10.66.66.0/24")
AVAILABLE_IPS = {
    code: [str(ip) for ip in list(SUBNET.hosts())[1:]] for code in NODES
}


# ------------------------------------------------------- telegram helpers ---

def tg_api(method, **params):
    """POST a Bot API method with a JSON body. Returns the `result` field."""
    resp = requests.post(f"{BOT_API}/{method}", json=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error on {method}: {data}")
    return data["result"]


def tg_file(method, files, data):
    """POST a Bot API method with multipart files (photo / document)."""
    resp = requests.post(f"{BOT_API}/{method}", files=files, data=data, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error on {method}: {result}")
    return result["result"]


def get_updates(offset, timeout=30):
    resp = requests.get(
        f"{BOT_API}/getUpdates",
        params={"offset": offset, "timeout": timeout},
        timeout=timeout + 10,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def send_message(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        params["reply_markup"] = reply_markup
    return tg_api("sendMessage", **params)


def answer_callback_query(callback_query_id, text=None):
    params = {"callback_query_id": callback_query_id}
    if text:
        params["text"] = text
    return tg_api("answerCallbackQuery", **params)


def send_photo(chat_id, png_bytes, caption):
    files = {"photo": ("qr.png", png_bytes, "image/png")}
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    return tg_file("sendPhoto", files, data)


def send_document(chat_id, filename, content_bytes):
    files = {"document": (filename, content_bytes, "text/plain")}
    data = {"chat_id": chat_id}
    return tg_file("sendDocument", files, data)


# --------------------------------------------------------- node API calls ---

def fetch_node_health(code):
    """GET https://<node>:8443/health with cert pinning + fingerprint check."""
    node = NODES[code]
    url = f"https://{node['ip']}:8443/health"
    with httpx.Client(verify=node["cert"], timeout=4.0) as client:
        resp = client.get(url, headers={"x-api-key": AGENT_API_SECRET})
        resp.raise_for_status()
        health = resp.json()
    expected_fp = (node.get("fingerprint") or "").strip().lower()
    if expected_fp:
        reported_fp = (health.get("tls_cert_sha256") or "").strip().lower()
        if reported_fp != expected_fp:
            raise RuntimeError(
                f"node {code}: TLS fingerprint mismatch — refusing to provision"
            )
    elif not health.get("tls_cert_sha256"):
        logging.warning("node %s: agent reports no TLS fingerprint", code)
    return health


def select_smart_location():
    """Online node with the lowest active peer load. Raises if none answer."""
    best_region = None
    lowest_peers = None
    for code in NODES:
        try:
            health = fetch_node_health(code)
        except Exception:
            logging.warning("node %s unreachable for smart location", code)
            continue
        peers = health.get("active_peers", 0)
        if lowest_peers is None or peers < lowest_peers:
            lowest_peers = peers
            best_region = code
    if best_region is None:
        raise RuntimeError("No VPN nodes are currently reachable.")
    return best_region


# ------------------------------------------------------------ provisioning ---

def generate_wireguard_keypair():
    """Fresh Curve25519 WireGuard keypair, generated in RAM (pynacl)."""
    priv = PrivateKey.generate()
    priv_b64 = base64.b64encode(bytes(priv)).decode("ascii")
    pub_b64 = base64.b64encode(bytes(priv.public_key)).decode("ascii")
    return priv_b64, pub_b64


def build_wg_config(client_priv, assigned_ip, server_pub, endpoint):
    return (
        "[Interface]\n"
        f"PrivateKey = {client_priv}\n"
        f"Address = {assigned_ip}/32\n"
        "DNS = 10.66.66.1\n"
        "MTU = 1420\n\n"
        "[Peer]\n"
        f"PublicKey = {server_pub}\n"
        f"Endpoint = {endpoint}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "PersistentKeepalive = 25\n"
    )


def make_qr_png(text):
    img = qrcode.make(text)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


def provision_tunnel(region, stealth=False):
    """Provision one ephemeral peer on the node and build the client config.

    TODO (payments): before provisioning, check the user's plan here.
    Plans, prices and payment methods (KBZPay / WavePay / AYAPay) live in
    the existing subscription bot. This controller is provisioning-only
    until that check is wired in — do NOT invent prices here.
    """
    if not AVAILABLE_IPS[region]:
        # Pool exhausted — stale sessions are purged by the node GC, so
        # recycling the pool is safe.
        AVAILABLE_IPS[region] = [str(ip) for ip in list(SUBNET.hosts())[1:]]

    assigned_ip = AVAILABLE_IPS[region].pop(0)
    client_priv, client_pub = generate_wireguard_keypair()
    node = NODES[region]

    # 1. Fetch the node's current RAM public key (+ fingerprint check).
    health = fetch_node_health(region)
    server_pub = health["server_public_key"]

    # 2. Register the peer in the node's kernel memory.
    with httpx.Client(verify=node["cert"], timeout=5.0) as client:
        resp = client.post(
            f"https://{node['ip']}:8443/peers/add",
            json={"client_pubkey": client_pub, "assigned_ip": f"{assigned_ip}/32"},
            headers={"x-api-key": AGENT_API_SECRET},
        )
        resp.raise_for_status()

    endpoint = "127.0.0.1:51820" if stealth else f"{node['ip']}:51820"
    config = build_wg_config(client_priv, assigned_ip, server_pub, endpoint)

    stealth_cmd = None
    if stealth:
        stealth_cmd = (
            "wstunnel client "
            "-L udp://127.0.0.1:51820:127.0.0.1:51820 "
            f"wss://{node['ip']}:443"
        )

    return {
        "region_code": region,
        "region_name": node["name"],
        "assigned_ip": assigned_ip,
        "config": config,
        "stealth_cmd": stealth_cmd,
    }


# ---------------------------------------------------------------- handlers ---

def handle_start(chat_id):
    keyboard = {"inline_keyboard": [
        [{"text": "⚡ Smart Location (Fastest)", "callback_data": "conn:smart:std"}],
    ]}
    for code, info in NODES.items():
        keyboard["inline_keyboard"].append([
            {"text": f"🌐 {info['name']} (UDP)", "callback_data": f"conn:{code}:std"},
            {"text": "🛡️ Stealth 443", "callback_data": f"conn:{code}:stealth"},
        ])
    send_message(
        chat_id,
        "🔒 <b>Zero-Log RAM VPN</b>\n"
        "Select a location or Stealth mode (TCP 443):\n"
        "Stealth 443 is the mode that gets through MPT's blocking.",
        reply_markup=keyboard,
    )


def handle_callback(query):
    data = query.get("data", "")
    chat_id = query["message"]["chat"]["id"]
    answer_callback_query(query["id"], "Provisioning your tunnel…")

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "conn":
        return
    _, region_choice, mode = parts
    stealth = (mode == "stealth")

    try:
        region = select_smart_location() if region_choice == "smart" else region_choice
        if region not in NODES:
            raise RuntimeError("unknown region")
        tunnel = provision_tunnel(region, stealth=stealth)

        caption = (
            f"✅ <b>Connected to {tunnel['region_name']}</b>\n"
            f"• Internal IP: <code>{tunnel['assigned_ip']}</code>\n"
            "• DNS: <code>10.66.66.1</code> (Zero-Log Unbound)\n"
            "• Storage: volatile RAM (tmpfs)\n"
        )
        if tunnel["stealth_cmd"]:
            caption += (
                "\n🛡️ <b>Stealth TCP 443:</b> start the wrapper first, "
                "then import the .conf below:\n"
                f"<code>{tunnel['stealth_cmd']}</code>\n"
                "Self-signed setup: the wrapper must trust the node "
                "certificate — see client/NOTES.md."
            )

        qr_png = make_qr_png(tunnel["config"])
        send_photo(chat_id, qr_png, caption)
        send_document(chat_id, f"vpn-{region}.conf", tunnel["config"].encode("utf-8"))
    except Exception as exc:
        logging.exception("provisioning failed")
        send_message(chat_id, f"❌ Provisioning error: {exc}")


# -------------------------------------------------------------------- main ---

def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in the environment (see .env.example).")
    if not AGENT_API_SECRET or AGENT_API_SECRET == "CHANGE_ME":
        raise SystemExit("Set AGENT_API_SECRET in the environment (see .env.example).")

    logging.info("vpn-v2 controller starting. Nodes: %s", ", ".join(NODES))
    offset = None
    while True:
        try:
            updates = get_updates(offset)
        except Exception:
            logging.exception("getUpdates failed; retrying in 5s")
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                if "message" in update:
                    msg = update["message"]
                    if msg.get("text", "").startswith("/start"):
                        handle_start(msg["chat"]["id"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
            except Exception:
                logging.exception("failed to handle update %s", update.get("update_id"))


if __name__ == "__main__":
    main()
