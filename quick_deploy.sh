#!/bin/bash
# QUICK DEPLOYMENT SCRIPT - RUN THIS ON YOUR LOCAL MACHINE
# This will transfer and deploy everything to your VPS

VPS_IP="75.119.149.117"
VPS_USER="root"
VPS_PASS="***REDACTED***"

echo "================================================"
echo "  ULTRA+ BOT QUICK DEPLOYMENT TO VPS"
echo "================================================"
echo ""
echo "This script will:"
echo "1. Transfer the bot code to your VPS"
echo "2. Set up the environment"
echo "3. Install all dependencies"
echo "4. Configure for 24/7 operation"
echo ""
echo "VPS: $VPS_IP (6 vCPU / 12 GB RAM)"
echo ""

# Step 1: Transfer bot file
echo "Step 1: Transferring bot code..."
sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking=no ultimate_ultra_plus.py $VPS_USER@$VPS_IP:/tmp/

# Step 2: Connect and deploy
echo "Step 2: Connecting to VPS and deploying..."
sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP << 'REMOTE_COMMANDS'

echo "Connected to VPS. Starting deployment..."

# Create deployment script
cat > /tmp/install_bot.sh << 'INSTALL_SCRIPT'
#!/bin/bash
set -e

echo "Installing Ultimate Ultra+ Bot..."

# Backup existing
if [ -d /opt/leantraderbot ]; then
    mkdir -p /opt/backups
    tar -czf /opt/backups/backup_$(date +%Y%m%d).tar.gz -C /opt leantraderbot 2>/dev/null || true
fi

# Install dependencies
apt-get update -qq
apt-get install -y python3 python3-venv python3-pip build-essential sqlite3

# Create directories
mkdir -p /opt/leantraderbot/{logs,models,data}
cd /opt/leantraderbot

# Copy bot file
cp /tmp/ultimate_ultra_plus.py .

# Create Python environment
python3 -m venv venv

# Install packages
./venv/bin/pip install --upgrade pip
./venv/bin/pip install numpy pandas ccxt scikit-learn joblib xgboost aiohttp python-telegram-bot beautifulsoup4 feedparser requests python-dotenv

# Create config
cat > .env << 'CONFIG'
USE_TESTNET=true
FORCE_LIVE=0
BYBIT_TESTNET_API_KEY=
BYBIT_TESTNET_API_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ADMIN_ID=
MAX_DAILY_DD=0.05
MAX_SLOTS=5
DEFAULT_SIZE=100
DEFAULT_LEVERAGE=2
ENABLE_MOON_SPOTTER=true
ENABLE_SCALPER=true
ENABLE_ARBITRAGE=true
ENABLE_FX_TRAINER=true
ENABLE_WEB_CRAWLER=true
ENABLE_DL_STACK=false
SCALPER_INTERVAL=3
MOON_INTERVAL=8
ARBITRAGE_INTERVAL=10
CONFIG

chmod 600 .env

# Create service
cat > /etc/systemd/system/ultra_plus.service << 'SERVICE'
[Unit]
Description=Ultimate Ultra+ Trading Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/leantraderbot
ExecStart=/opt/leantraderbot/venv/bin/python /opt/leantraderbot/ultimate_ultra_plus.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ultra_plus

echo "✓ Installation complete!"
INSTALL_SCRIPT

chmod +x /tmp/install_bot.sh
/tmp/install_bot.sh

echo ""
echo "================================================"
echo "  DEPLOYMENT COMPLETE!"
echo "================================================"
echo ""
echo "NEXT STEPS:"
echo "1. Edit config: nano /opt/leantraderbot/.env"
echo "2. Add your API keys"
echo "3. Start bot: systemctl start ultra_plus"
echo "4. Check logs: journalctl -u ultra_plus -f"
echo ""

REMOTE_COMMANDS

echo ""
echo "================================================"
echo "  DEPLOYMENT FINISHED!"
echo "================================================"
echo ""
echo "To connect to your VPS:"
echo "  ssh root@$VPS_IP"
echo ""
echo "To configure the bot:"
echo "  nano /opt/leantraderbot/.env"
echo ""
echo "To start the bot:"
echo "  systemctl start ultra_plus"
echo ""
echo "To view logs:"
echo "  journalctl -u ultra_plus -f"
echo ""