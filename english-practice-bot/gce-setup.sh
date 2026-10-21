#!/bin/bash
# Setup script for the Masterclass English practice bot on a GCE VM.
# Run as root on a fresh Debian/Ubuntu VM.
# Env vars required (export before running):
#   BOT_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY, ADMIN_CHAT_ID
set -euo pipefail

: "${BOT_TOKEN:?Set BOT_TOKEN}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY}"
: "${ADMIN_CHAT_ID:?Set ADMIN_CHAT_ID}"

BOT_USER="botrunner"
REPO="https://github.com/biggestwolf8-code/myanmar-bots.git"
APP_DIR="/opt/english-practice-bot"
DATA_DIR="/opt/english-practice-bot/data"

echo "=== Installing dependencies ==="
apt-get update -qq
apt-get install -y -qq python3 python3-pip git > /dev/null

echo "=== Creating service user ==="
id "$BOT_USER" &>/dev/null || useradd -m -s /bin/bash "$BOT_USER"

echo "=== Cloning bot code ==="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull -q
else
  rm -rf "$APP_DIR"
  git clone -q "$REPO" /opt/myanmar-bots
  cp -r /opt/myanmar-bots/english-practice-bot "$APP_DIR"
  chown -R "$BOT_USER:$BOT_USER" "$APP_DIR"
fi

echo "=== Installing Python deps ==="
pip3 install -q -r "$APP_DIR/requirements.txt"

echo "=== Setting up data dir ==="
mkdir -p "$DATA_DIR"
chown -R "$BOT_USER:$BOT_USER" "$DATA_DIR"

echo "=== Writing systemd service ==="
cat > /etc/systemd/system/english-practice-bot.service <<EOF
[Unit]
Description=Masterclass English Practice Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$APP_DIR
Environment=BOT_TOKEN=$BOT_TOKEN
Environment=ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
Environment=OPENAI_API_KEY=$OPENAI_API_KEY
Environment=ADMIN_CHAT_ID=$ADMIN_CHAT_ID
Environment=BOT_USERNAME=MasterclassPractice_Bot
Environment=DATA_DIR=$DATA_DIR
Environment=DAILY_LIMIT=100
ExecStart=/usr/bin/python3 $APP_DIR/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable -q english-practice-bot
systemctl restart english-practice-bot

echo "=== Done ==="
sleep 3
systemctl is-active english-practice-bot
echo "--- recent logs ---"
journalctl -u english-practice-bot -n 15 --no-pager
