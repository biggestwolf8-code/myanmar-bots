#!/bin/bash
# Fix WireGuard VPN routing
set -e

echo "=== Fixing IP forwarding ==="
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-wireguard.conf
sysctl -p /etc/sysctl.d/99-wireguard.conf

echo "=== Fixing NAT rules ==="
# Get the main network interface
IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
echo "Main interface: $IFACE"

# Clear old rules
iptables -t nat -D POSTROUTING -o $IFACE -j MASQUERADE 2>/dev/null || true
iptables -D FORWARD -i wg0 -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -o wg0 -j ACCEPT 2>/dev/null || true

# Add correct rules
iptables -A FORWARD -i wg0 -j ACCEPT
iptables -A FORWARD -o wg0 -j ACCEPT
iptables -t nat -A POSTROUTING -o $IFACE -j MASQUERADE

# Make rules persistent
apt-get install -y -qq iptables-persistent > /dev/null 2>&1 || true
netfilter-persistent save > /dev/null 2>&1 || iptables-save > /etc/iptables/rules.v4 2>/dev/null || true

echo "=== Restarting WireGuard ==="
systemctl restart wg-quick@wg0
sleep 2
systemctl is-active wg-quick@wg0

echo ""
echo "=== VPN fix complete ==="
echo "Try connecting from your phone now."
