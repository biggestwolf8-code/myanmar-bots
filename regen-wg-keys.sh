#!/bin/bash
# Regenerate WireGuard client keys and update server
set -e

cd /etc/wireguard

# Generate new client keypair
CLIENT_PRIV=$(wg genkey)
CLIENT_PUB=$(echo "$CLIENT_PRIV" | wg pubkey)
# Get server public key from its private key in wg0.conf
SERVER_PRIV=$(grep -A5 '\[Interface\]' /etc/wireguard/wg0.conf | grep PrivateKey | awk '{print $3}')
SERVER_PUB=$(echo "$SERVER_PRIV" | wg pubkey)

echo "New client public key: $CLIENT_PUB"

# Update server config - replace the peer public key
# Backup first
cp wg0.conf wg0.conf.bak

# Replace peer public key line (the one after [Peer])
# Use python for reliable replacement
python3 << PYEOF
import re
with open('/etc/wireguard/wg0.conf') as f:
    content = f.read()
# Replace the PublicKey line in the [Peer] section
content = re.sub(
    r'(\[Peer\]\s*\nPublicKey = )[^\n]+',
    r'\g<1>$CLIENT_PUB',
    content
)
with open('/etc/wireguard/wg0.conf', 'w') as f:
    f.write(content)
print("Server config updated")
PYEOF

# Restart WireGuard
systemctl restart wg-quick@wg0
sleep 2

# Generate new client config
cat > /root/wg-client-new.conf << EOF
[Interface]
PrivateKey = $CLIENT_PRIV
Address = 10.8.0.2/24
DNS = 1.1.1.1

[Peer]
PublicKey = $SERVER_PUB
Endpoint = 149.28.150.78:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

chmod 600 /root/wg-client-new.conf
echo ""
echo "=== New client config written to /root/wg-client-new.conf ==="
echo "Client public key: $CLIENT_PUB"
wg show | head -20
