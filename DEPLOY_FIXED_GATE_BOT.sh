#!/bin/bash

echo "🚀 DEPLOYING FIXED GATE.IO PROFIT BOT..."

# Create deployment commands
cat > deploy_commands.txt << 'DEPLOY'
# 1. Copy the fixed bot to VPS
scp REAL_TRADING_BOT_FIXED_GATE.py root@vmi2817884.contaboserver.net:/opt/leantraderbot/REAL_TRADING_BOT.py

# 2. SSH to VPS and setup
ssh root@vmi2817884.contaboserver.net << 'VPS_COMMANDS'
cd /opt/leantraderbot

# Stop current bot
systemctl stop real_trading_bot.service

# Make executable
chmod +x REAL_TRADING_BOT.py

# Test the fixed bot
echo "🧪 Testing FIXED Gate.io bot..."
source venv/bin/activate
python3 -c "
from REAL_TRADING_BOT import GATE_PROFIT_BOT
bot = GATE_PROFIT_BOT()
print('🚀 FIXED Gate.io bot initialized successfully!')
balance = bot.check_gate_balance()
print(f'💰 Your Gate.io Balance: \${balance}')
"

# Start the fixed bot
systemctl start real_trading_bot.service
echo "🚀 FIXED Gate.io Profit Bot started!"

# Monitor the bot
echo "📊 Monitoring FIXED bot..."
journalctl -u real_trading_bot.service -f
VPS_COMMANDS
DEPLOY

echo "✅ DEPLOYMENT COMMANDS CREATED!"
echo "📋 Copy and run these commands:"
echo ""
cat deploy_commands.txt
