#!/bin/bash
# Complete Zoom monitor setup for Vultr VM - single command install
# This sets up 6-hour automated Zoom license checks
set -e

echo "=== Zoom Monitor Full Setup ==="
echo ""

# 1. Install dependencies
echo "[1/5] Installing Playwright and Chromium..."
apt-get update -qq 2>&1 | tail -1
apt-get install -y -qq python3 python3-pip > /dev/null 2>&1
pip3 install --break-system-packages -q playwright requests 2>&1 | tail -1
python3 -m playwright install chromium > /dev/null 2>&1 || echo "Chromium install attempted"
python3 -m playwright install-deps chromium > /dev/null 2>&1 || true
echo "  Done"

# 2. Create directories
echo "[2/5] Creating directories..."
mkdir -p /opt/zoom-monitor/states
mkdir -p /opt/zoom-monitor/logs
echo "  Done"

# 3. Download check script
echo "[3/5] Downloading monitor script..."
curl -sSL https://raw.githubusercontent.com/biggestwolf8-code/myanmar-bots/main/zoom-check.py -o /opt/zoom-monitor/check.py
chmod +x /opt/zoom-monitor/check.py
echo "  Done"

# 4. Create systemd service
echo "[4/5] Setting up systemd service..."
cat > /etc/systemd/system/zoom-monitor.service << 'SERVICE_EOF'
[Unit]
Description=Zoom License Monitor Check
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/opt/zoom-monitor
EnvironmentFile=/opt/zoom-monitor/env.conf
ExecStart=/usr/bin/python3 /opt/zoom-monitor/check.py
StandardOutput=append:/opt/zoom-monitor/logs/check.log
StandardError=append:/opt/zoom-monitor/logs/check.log
SERVICE_EOF

# 5. Create systemd timer (every 6 hours)
cat > /etc/systemd/system/zoom-monitor.timer << 'TIMER_EOF'
[Unit]
Description=Run Zoom License Monitor every 6 hours

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
Unit=zoom-monitor.service

[Install]
WantedBy=timers.target
TIMER_EOF

systemctl daemon-reload
systemctl enable zoom-monitor.timer > /dev/null 2>&1
systemctl start zoom-monitor.timer
echo "  Timer enabled (runs every 6 hours)"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "NEXT STEPS:"
echo "1. Create /opt/zoom-monitor/creds.json with your Zoom credentials"
echo "   Format: {\"email@gmail.com\": \"password\", ...}"
echo ""
echo "2. Create /opt/zoom-monitor/env.conf with:"
echo "   INGEST_URL=https://zoom-license-bot-production.up.railway.app/ingest"
echo "   INGEST_SECRET=your_secret_here"
echo ""
echo "3. Test with: systemctl start zoom-monitor.service"
echo "   Then check: tail -50 /opt/zoom-monitor/logs/check.log"
echo ""
echo "Timer status:"
systemctl status zoom-monitor.timer --no-pager | head -10
