#!/usr/bin/env python3
"""
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