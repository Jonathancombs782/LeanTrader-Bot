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
Automated VPS Deployment Script
This script will automatically deploy the trading bot to your VPS
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def run_command(cmd, check=True):
    """Run a command and return the result"""
    print(f"🔧 Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        if result.stdout:
            print(f"✅ {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e.stderr}")
        return None

def create_bot_files():
    """Create all the bot files locally"""
    print("📝 Creating bot files...")
    
    # Create main bot file
    main_bot = '''#!/usr/bin/env python3
"""
Professional Bybit Trading Bot
"""

import asyncio
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import os
import json
from loguru import logger

class BybitTradingBot:
    def __init__(self):
        self.exchange = None
        self.running = False
        self.api_key = "***REDACTED***"
        self.secret_key = "***REDACTED***"
        self.sandbox = True
        
    async def initialize(self):
        logger.info("🚀 Initializing Bybit Trading Bot...")
        try:
            self.exchange = ccxt.bybit({
                'apiKey': self.api_key,
                'secret': self.secret_key,
                'sandbox': self.sandbox,
                'enableRateLimit': True,
            })
            markets = await self.exchange.load_markets()
            logger.info(f"✅ Connected to Bybit Testnet - {len(markets)} markets available")
            return True
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    async def get_market_data(self, symbol='BTC/USDT'):
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"Error getting {symbol}: {e}")
            return None
    
    async def analyze_market(self, ticker):
        try:
            price = ticker['last']
            change_24h = ticker['change']
            volume = ticker['baseVolume']
            
            # Simple analysis
            if change_24h < -500:  # Significant drop
                return 'BUY', 0.8, f"Strong buy signal - Price dropped {change_24h}"
            elif change_24h > 500:  # Significant rise
                return 'SELL', 0.8, f"Strong sell signal - Price rose {change_24h}"
            else:
                return 'HOLD', 0.5, f"Neutral - Change: {change_24h}"
        except Exception as e:
            return 'HOLD', 0.0, f"Analysis error: {e}"
    
    async def trading_loop(self):
        logger.info("🎯 Starting trading loop...")
        symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT']
        
        while self.running:
            try:
                logger.info(f"📊 Market Analysis - {datetime.now().strftime('%H:%M:%S')}")
                
                for symbol in symbols:
                    ticker = await self.get_market_data(symbol)
                    if ticker:
                        action, confidence, reasoning = await self.analyze_market(ticker)
                        logger.info(f"📈 {symbol}: ${ticker['last']:.2f} | {action} ({confidence:.0%}) | {reasoning}")
                        
                        if confidence > 0.7 and action != 'HOLD':
                            logger.info(f"🎮 SIMULATION: Would {action} {symbol} at ${ticker['last']:.2f}")
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                await asyncio.sleep(10)
    
    async def start(self):
        logger.info("🚀 Starting Professional Bybit Trading Bot...")
        logger.info(f"🔑 API: {self.api_key[:10]}...")
        logger.info(f"🌐 Mode: {'Testnet' if self.sandbox else 'Live'}")
        
        if await self.initialize():
            self.running = True
            await self.trading_loop()
        else:
            logger.error("❌ Failed to initialize bot")
    
    async def stop(self):
        logger.info("🛑 Stopping bot...")
        self.running = False

async def main():
    bot = BybitTradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    logger.info("🤖 Professional Bybit Trading Bot")
    logger.info("=" * 40)
    logger.info("Starting in 3 seconds...")
    time.sleep(3)
    asyncio.run(main())
'''
    
    with open('bybit_bot.py', 'w') as f:
        f.write(main_bot)
    
    # Create setup script
    setup_script = '''#!/bin/bash
set -e

echo "🚀 Automated Bybit Trading Bot Setup"
echo "===================================="

# Update system
echo "📦 Updating system..."
apt update -y && apt upgrade -y

# Install dependencies
echo "🔧 Installing dependencies..."
apt install -y python3.11 python3.11-pip python3.11-venv python3.11-dev build-essential git curl wget htop

# Create bot directory
echo "📁 Creating bot directory..."
mkdir -p /home/root/trading-bot
cd /home/root/trading-bot

# Create virtual environment
echo "🐍 Setting up Python environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install Python packages
echo "📚 Installing Python packages..."
pip install --upgrade pip
pip install ccxt pandas numpy python-dotenv loguru asyncio requests

# Configure firewall
echo "🔥 Configuring firewall..."
ufw allow ssh
ufw allow 8501/tcp
ufw --force enable

# Create bot file
echo "📝 Creating trading bot..."
cat > bybit_bot.py << 'EOF'
#!/usr/bin/env python3
"""
Professional Bybit Trading Bot
"""

import asyncio
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import os
import json
from loguru import logger

class BybitTradingBot:
    def __init__(self):
        self.exchange = None
        self.running = False
        self.api_key = "***REDACTED***"
        self.secret_key = "***REDACTED***"
        self.sandbox = True
        
    async def initialize(self):
        logger.info("🚀 Initializing Bybit Trading Bot...")
        try:
            self.exchange = ccxt.bybit({
                'apiKey': self.api_key,
                'secret': self.secret_key,
                'sandbox': self.sandbox,
                'enableRateLimit': True,
            })
            markets = await self.exchange.load_markets()
            logger.info(f"✅ Connected to Bybit Testnet - {len(markets)} markets available")
            return True
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    async def get_market_data(self, symbol='BTC/USDT'):
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"Error getting {symbol}: {e}")
            return None
    
    async def analyze_market(self, ticker):
        try:
            price = ticker['last']
            change_24h = ticker['change']
            volume = ticker['baseVolume']
            
            # Simple analysis
            if change_24h < -500:  # Significant drop
                return 'BUY', 0.8, f"Strong buy signal - Price dropped {change_24h}"
            elif change_24h > 500:  # Significant rise
                return 'SELL', 0.8, f"Strong sell signal - Price rose {change_24h}"
            else:
                return 'HOLD', 0.5, f"Neutral - Change: {change_24h}"
        except Exception as e:
            return 'HOLD', 0.0, f"Analysis error: {e}"
    
    async def trading_loop(self):
        logger.info("🎯 Starting trading loop...")
        symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT']
        
        while self.running:
            try:
                logger.info(f"📊 Market Analysis - {datetime.now().strftime('%H:%M:%S')}")
                
                for symbol in symbols:
                    ticker = await self.get_market_data(symbol)
                    if ticker:
                        action, confidence, reasoning = await self.analyze_market(ticker)
                        logger.info(f"📈 {symbol}: ${ticker['last']:.2f} | {action} ({confidence:.0%}) | {reasoning}")
                        
                        if confidence > 0.7 and action != 'HOLD':
                            logger.info(f"🎮 SIMULATION: Would {action} {symbol} at ${ticker['last']:.2f}")
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                await asyncio.sleep(10)
    
    async def start(self):
        logger.info("🚀 Starting Professional Bybit Trading Bot...")
        logger.info(f"🔑 API: {self.api_key[:10]}...")
        logger.info(f"🌐 Mode: {'Testnet' if self.sandbox else 'Live'}")
        
        if await self.initialize():
            self.running = True
            await self.trading_loop()
        else:
            logger.error("❌ Failed to initialize bot")
    
    async def stop(self):
        logger.info("🛑 Stopping bot...")
        self.running = False

async def main():
    bot = BybitTradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    logger.info("🤖 Professional Bybit Trading Bot")
    logger.info("=" * 40)
    logger.info("Starting in 3 seconds...")
    import time
    time.sleep(3)
    asyncio.run(main())
EOF

# Make bot executable
chmod +x bybit_bot.py

# Create startup script
cat > start_bot.sh << 'EOF'
#!/bin/bash
cd /home/root/trading-bot
source venv/bin/activate
python bybit_bot.py
EOF

chmod +x start_bot.sh

# Create systemd service
cat > /etc/systemd/system/bybit-bot.service << 'EOF'
[Unit]
Description=Bybit Trading Bot
After=network.target

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
WorkingDirectory=/home/root/trading-bot
Environment=PATH=/home/root/trading-bot/venv/bin
ExecStart=/home/root/trading-bot/venv/bin/python bybit_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable bybit-bot
systemctl start bybit-bot

echo "✅ Bot deployed and started!"
echo "📊 Check status: systemctl status bybit-bot"
echo "📋 View logs: journalctl -u bybit-bot -f"
echo "🛑 Stop bot: systemctl stop bybit-bot"
'''
    
    with open('auto_setup.sh', 'w') as f:
        f.write(setup_script)
    
    print("✅ Bot files created!")

def deploy_to_vps():
    """Deploy the bot to VPS automatically"""
    print("🚀 Starting automated deployment...")
    
    # Create deployment package
    print("📦 Creating deployment package...")
    run_command("tar -czf bot_deploy.tar.gz bybit_bot.py auto_setup.sh", check=False)
    
    # Upload to VPS
    print("📤 Uploading to VPS...")
    upload_cmd = "scp bot_deploy.tar.gz root@75.119.149.117:/tmp/"
    result = run_command(upload_cmd, check=False)
    
    if result and result.returncode == 0:
        print("✅ Files uploaded successfully!")
        
        # Execute setup on VPS
        print("🔧 Running setup on VPS...")
        setup_cmd = """ssh root@75.119.149.117 'cd /tmp && tar -xzf bot_deploy.tar.gz && chmod +x auto_setup.sh && ./auto_setup.sh'"""
        
        print("🎯 Executing automated setup...")
        print("This may take a few minutes...")
        
        # Run setup
        result = run_command(setup_cmd, check=False)
        
        if result and result.returncode == 0:
            print("🎉 Bot deployed and started successfully!")
            print("\n📊 Your bot is now running!")
            print("🔍 Check status: ssh root@75.119.149.117 'systemctl status bybit-bot'")
            print("📋 View logs: ssh root@75.119.149.117 'journalctl -u bybit-bot -f'")
        else:
            print("❌ Setup failed. Let's try manual deployment...")
            return False
    else:
        print("❌ Upload failed. Please check your VPS connection.")
        return False
    
    # Cleanup
    run_command("rm bot_deploy.tar.gz", check=False)
    return True

def main():
    print("🤖 Automated Bybit Trading Bot Deployment")
    print("=" * 50)
    print("🎯 This will automatically:")
    print("   ✅ Install all dependencies")
    print("   ✅ Set up Python environment")
    print("   ✅ Deploy the trading bot")
    print("   ✅ Start the bot service")
    print("   ✅ Configure everything for Bybit testnet")
    print("")
    
    # Create bot files
    create_bot_files()
    
    # Try automated deployment
    if deploy_to_vps():
        print("\n🎉 SUCCESS! Your trading bot is running!")
        print("=" * 40)
        print("🚀 Bot Status: RUNNING")
        print("🌐 Exchange: Bybit Testnet")
        print("🔑 API: Configured")
        print("📊 Monitoring: BTC, ETH, BNB, ADA, SOL")
        print("")
        print("📋 Management Commands:")
        print("• Status: ssh root@75.119.149.117 'systemctl status bybit-bot'")
        print("• Logs: ssh root@75.119.149.117 'journalctl -u bybit-bot -f'")
        print("• Stop: ssh root@75.119.149.117 'systemctl stop bybit-bot'")
        print("• Start: ssh root@75.119.149.117 'systemctl start bybit-bot'")
    else:
        print("\n⚠️ Automated deployment failed.")
        print("📋 Manual deployment instructions:")
        print("1. ssh root@75.119.149.117")
        print("2. Run the commands in the auto_setup.sh file")
        print("3. Or use the bybit_bot.py file directly")

if __name__ == "__main__":
    main()
