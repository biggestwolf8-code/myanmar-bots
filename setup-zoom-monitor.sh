#!/bin/bash
# Setup Zoom license monitor on Vultr VM
# Run after setup-vm.sh
set -e

echo "=== Installing Playwright and Chromium ==="
apt-get update -qq
apt-get install -y -qq python3 python3-pip > /dev/null 2>&1
pip3 install --break-system-packages -q playwright requests > /dev/null 2>&1
python3 -m playwright install chromium > /dev/null 2>&1
python3 -m playwright install-deps chromium > /dev/null 2>&1 || true

echo "=== Creating monitor directory ==="
mkdir -p /opt/zoom-monitor/states
mkdir -p /opt/zoom-monitor/logs

echo "=== Done ==="
echo ""
echo "Next steps:"
echo "1. Create /opt/zoom-monitor/creds.json with your Zoom credentials:"
echo '   {"email1@gmail.com": "password1", "email2@gmail.com": "password2"}'
echo "2. The monitor script will be placed at /opt/zoom-monitor/check.py"
echo "3. Set INGEST_SECRET env var with your bot's ingest secret"
