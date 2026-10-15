#!/bin/bash
# Setup script for Vultr Singapore VM
# Run: curl -sSL https://raw.githubusercontent.com/biggestwolf8-code/myanmar-bots/main/setup-vm.sh | bash
set -e

echo "=== Updating system ==="
apt-get update -qq
apt-get install -y -qq python3 python3-pip curl wget git ufw > /dev/null 2>&1

echo "=== Installing Python packages ==="
pip3 install --break-system-packages -q paramiko requests flask 2>&1 | tail -1

echo "=== Configuring firewall ==="
ufw allow 22/tcp > /dev/null 2>&1
ufw allow 51820/udp > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1

echo "=== Installing WireGuard ==="
apt-get install -y -qq wireguard qrencode > /dev/null 2>&1

# Generate WireGuard keys
mkdir -p /etc/wireguard
umask 077
wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
wg genkey | tee /etc/wireguard/client.key | wg pubkey > /etc/wireguard/client.pub

SERVER_PRIV=$(cat /etc/wireguard/server.key)
CLIENT_PUB=$(cat /etc/wireguard/client.pub)
CLIENT_PRIV=$(cat /etc/wireguard/client.key)
SERVER_PUB=$(cat /etc/wireguard/server.pub)

# Get server's public IP
PUB_IP=$(curl -s -m 10 ifconfig.me || curl -s -m 10 icanhazip.com)

# Server config
cat > /etc/wireguard/wg0.conf << EOF
[Interface]
PrivateKey = $SERVER_PRIV
Address = 10.8.0.1/24
ListenPort = 51820
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

[Peer]
PublicKey = $CLIENT_PUB
AllowedIPs = 10.8.0.2/32
EOF

# Enable IP forwarding
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-wireguard.conf
sysctl -q -p /etc/sysctl.d/99-wireguard.conf

# Start WireGuard
systemctl enable wg-quick@wg0 > /dev/null 2>&1
systemctl start wg-quick@wg0

# Client config
cat > /root/wg-client.conf << EOF
[Interface]
PrivateKey = $CLIENT_PRIV
Address = 10.8.0.2/24
DNS = 1.1.1.1

[Peer]
PublicKey = $SERVER_PUB
Endpoint = $PUB_IP:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

echo ""
echo "=== WireGuard client config ==="
cat /root/wg-client.conf
echo ""
echo "=== QR code for mobile ==="
qrencode -t ansiutf8 < /root/wg-client.conf 2>/dev/null || echo "(qrencode failed, use config above)"

echo ""
echo "=== Setup complete ==="
echo "Server IP: $PUB_IP"
echo "Client config saved to /root/wg-client.conf"
