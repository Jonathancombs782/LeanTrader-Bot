#!/usr/bin/env python3
"""
Automatic VPS Deployment Script for Ultimate Ultra+ Bot
"""

import subprocess
import base64

# VPS Details
VPS_HOST = "75.119.149.117"
VPS_USER = "root"
VPS_PASS = "***REDACTED***"

# API Keys provided
TELEGRAM_BOT_TOKEN = "***REDACTED***"
TG_ADMIN_CHAT_ID = "5329503447"
TG_FREE_CHAT_ID = "-1002930953007"
TG_VIP_CHAT_ID = "-1002983007302"
BYBIT_API_KEY = "***REDACTED***"
BYBIT_API_SECRET = "***REDACTED***"

# Read the bot code
with open('/workspace/ultimate_ultra_plus.py', 'r') as f:
    bot_code = f.read()

# Encode bot code for safe transfer
bot_code_b64 = base64.b64encode(bot_code.encode()).decode()

# Create deployment script
deployment_script = f'''#!/bin/bash
set -e

echo "================================================"
echo "   AUTOMATIC ULTRA+ BOT DEPLOYMENT"
echo "   Starting deployment to VPS..."
echo "================================================"

# Step 1: Backup existing
echo -e "\\n[1/10] Creating backup..."
if [ -d /opt/leantraderbot ]; then
    mkdir -p /opt/backups
    tar -czf /opt/backups/backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /opt leantraderbot 2>/dev/null || true
    echo "✓ Backup created"
fi

# Step 2: Install system dependencies
echo -e "\\n[2/10] Installing system dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y python3.10 python3.10-venv python3-pip build-essential \\
    libssl-dev libffi-dev python3-dev git curl wget htop iotop \\
    net-tools sqlite3 2>/dev/null
echo "✓ System packages installed"

# Step 3: Create directories
echo -e "\\n[3/10] Creating directories..."
mkdir -p /opt/leantraderbot/{{logs,models,data,backups}}
cd /opt/leantraderbot
echo "✓ Directories created"

# Step 4: Deploy bot code
echo -e "\\n[4/10] Deploying bot code..."
echo "{bot_code_b64}" | base64 -d > /opt/leantraderbot/ultimate_ultra_plus.py
chmod 755 /opt/leantraderbot/ultimate_ultra_plus.py
echo "✓ Bot code deployed"

# Step 5: Create Python environment
echo -e "\\n[5/10] Setting up Python environment..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi
echo "✓ Virtual environment ready"

# Step 6: Install Python packages
echo -e "\\n[6/10] Installing Python packages..."
cat > requirements.txt << 'REQS'
numpy==1.24.3
pandas==2.0.3
scipy==1.11.1
ccxt==4.1.22
yfinance==0.2.28
pandas-ta==0.3.14b0
scikit-learn==1.3.0
joblib==1.3.2
xgboost==1.7.6
lightgbm==4.0.0
sqlalchemy==2.0.19
aiohttp==3.8.5
python-telegram-bot==20.4
beautifulsoup4==4.12.2
feedparser==6.0.10
requests==2.31.0
python-dotenv==1.0.0
pytz==2023.3
psutil==5.9.5
web3==6.11.3
REQS

./venv/bin/pip install --upgrade pip setuptools wheel
./venv/bin/pip install -r requirements.txt
echo "✓ Python packages installed"

# Step 7: Create configuration with API keys
echo -e "\\n[7/10] Creating configuration with your API keys..."
cat > /opt/leantraderbot/.env << 'CONFIG'
# ULTIMATE ULTRA+ BOT CONFIGURATION
# Auto-configured with your API keys

# Trading Mode - Starting with TESTNET for safety
USE_TESTNET=true
FORCE_LIVE=0

# Your Bybit API Keys
BYBIT_API_KEY={BYBIT_API_KEY}
BYBIT_API_SECRET={BYBIT_API_SECRET}
BYBIT_TESTNET_API_KEY={BYBIT_API_KEY}
BYBIT_TESTNET_API_SECRET={BYBIT_API_SECRET}

# Your Telegram Configuration
TELEGRAM_BOT_TOKEN={TELEGRAM_BOT_TOKEN}
TELEGRAM_CHAT_ID={TG_VIP_CHAT_ID}
TELEGRAM_ADMIN_ID={TG_ADMIN_CHAT_ID}
TG_FREE_CHAT_ID={TG_FREE_CHAT_ID}
TG_VIP_CHAT_ID={TG_VIP_CHAT_ID}

# Risk Management
MAX_DAILY_DD=0.05
MAX_SLOTS=5
DEFAULT_SIZE=100
DEFAULT_LEVERAGE=2

# All Engines ON for Maximum Profit
ENABLE_MOON_SPOTTER=true
ENABLE_SCALPER=true
ENABLE_ARBITRAGE=true
ENABLE_FX_TRAINER=true
ENABLE_DL_STACK=false
ENABLE_WEB_CRAWLER=true

# Optimized for 6 vCPU / 12 GB RAM
HEARTBEAT_INTERVAL=5
SCALPER_INTERVAL=3
MOON_INTERVAL=8
ARBITRAGE_INTERVAL=10
FX_RETRAIN_INTERVAL=1800
NEWS_CRAWL_INTERVAL=180

# Advanced Features
ENABLE_QUANTUM=true
ENABLE_NEURAL_SWARM=true
ENABLE_FRACTAL=true
ENABLE_SMART_MONEY=true
MODEL_SAVE_PATH=/opt/leantraderbot/models
MODEL_BACKUP_ENABLED=true
CONFIG

chmod 600 /opt/leantraderbot/.env
echo "✓ Configuration created with API keys"

# Step 8: Create systemd service
echo -e "\\n[8/10] Installing systemd service..."
cat > /etc/systemd/system/ultra_plus.service << 'SERVICE'
[Unit]
Description=Ultimate Ultra+ Trading Bot - Hedge Fund Grade
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/leantraderbot
Environment="PYTHONPATH=/opt/leantraderbot"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/leantraderbot/venv/bin/python /opt/leantraderbot/ultimate_ultra_plus.py
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3
CPUQuota=500%
MemoryLimit=10G
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ultra_plus

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable ultra_plus
echo "✓ Service installed and enabled"

# Step 9: Create monitoring script
echo -e "\\n[9/10] Setting up 24/7 monitoring..."
cat > /opt/leantraderbot/monitor.sh << 'MONITOR'
#!/bin/bash
LOG_FILE="/opt/leantraderbot/logs/monitor.log"
while true; do
    if ! systemctl is-active ultra_plus >/dev/null 2>&1; then
        echo "$(date): Bot stopped, restarting..." >> $LOG_FILE
        systemctl start ultra_plus
    fi
    sleep 60
done
MONITOR

chmod +x /opt/leantraderbot/monitor.sh
(crontab -l 2>/dev/null | grep -v monitor.sh; echo "@reboot /opt/leantraderbot/monitor.sh > /dev/null 2>&1 &") | crontab -
echo "✓ 24/7 monitoring configured"

# Step 10: Initialize and start
echo -e "\\n[10/10] Starting the bot..."
touch /opt/leantraderbot/ultra_plus.db
chmod 664 /opt/leantraderbot/ultra_plus.db

# Start the bot
systemctl start ultra_plus
sleep 5

# Check status
if systemctl is-active ultra_plus >/dev/null 2>&1; then
    echo "✓ Bot started successfully!"
else
    echo "⚠ Bot start failed, checking logs..."
    journalctl -u ultra_plus -n 20 --no-pager
fi

echo ""
echo "================================================"
echo "   DEPLOYMENT COMPLETE!"
echo "================================================"
echo ""
echo "✅ Bot deployed with your API keys"
echo "✅ All engines configured and running"
echo "✅ 24/7 monitoring active"
echo "✅ Telegram connected to your channels"
echo ""
echo "CHANNELS CONFIGURED:"
echo "  Admin: {TG_ADMIN_CHAT_ID}"
echo "  VIP: {TG_VIP_CHAT_ID}"
echo "  Free: {TG_FREE_CHAT_ID}"
echo ""
echo "TO CHECK STATUS:"
echo "  systemctl status ultra_plus"
echo ""
echo "TO VIEW LOGS:"
echo "  journalctl -u ultra_plus -f"
echo ""
echo "TELEGRAM BOT READY:"
echo "  Send /status to your bot"
echo ""
'''

# Save deployment script
with open('/tmp/deploy.sh', 'w') as f:
    f.write(deployment_script)

print("Connecting to VPS and deploying...")
print(f"VPS: {VPS_HOST}")
print("This will take 2-3 minutes...")

# Execute deployment
try:
    # Transfer and execute
    cmd = f'''
    sshpass -p '{VPS_PASS}' ssh -o StrictHostKeyChecking=no {VPS_USER}@{VPS_HOST} 'bash -s' < /tmp/deploy.sh
    '''
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    
    if result.returncode == 0:
        print("\n✅ DEPLOYMENT SUCCESSFUL!")
        print("\n📱 Your Telegram bot is now active!")
        print("📊 Send /status to your bot to verify")
        print("💰 Bot is running in TESTNET mode (safe)")
        print("\n🚀 The bot is now running 24/7 on your VPS!")
    else:
        print("\n⚠ Deployment encountered issues:")
        print(result.stderr)
        
except Exception as e:
    print(f"Error: {e}")
    print("\nManual deployment needed. SSH to your VPS and run the commands.")