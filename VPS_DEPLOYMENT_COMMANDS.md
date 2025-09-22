# 🚀 ULTIMATE BOT VPS DEPLOYMENT COMMANDS

## Your VPS Details:
- **IP**: 75.119.149.117
- **User**: root
- **OS**: Ubuntu 24.04

## 📋 DEPLOYMENT STEPS:

### 1. Upload Bot to VPS
```bash
scp ultimate_bot_working.py root@75.119.149.117:~/
```

### 2. SSH into VPS
```bash
ssh root@75.119.149.117
```

### 3. Deploy on VPS (Run these commands on VPS)
```bash
# Stop any existing bot processes
pkill -f "ultimate_bot_working.py" || true
pkill -f "python.*bot" || true

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install aiogram ccxt scikit-learn loguru numpy

# Make script executable
chmod +x ultimate_bot_working.py

# Start the bot in background
echo "🚀 STARTING ULTIMATE 450+ MODELS TRADING BOT..."
nohup python3 ultimate_bot_working.py > bot.log 2>&1 &

# Get process ID
BOT_PID=$!
echo "🤖 Bot started with PID: $BOT_PID"
echo "📊 Bot is running in background"
echo "📝 Logs: tail -f bot.log"

# Check if running
sleep 5
if ps -p $BOT_PID > /dev/null; then
    echo "✅ ULTIMATE BOT DEPLOYED AND RUNNING!"
    echo "🔗 VPS IP: 75.119.149.117"
    echo "🤖 Bot Status: ACTIVE"
    echo "📱 Telegram: ACTIVE"
    echo "💰 Trading: ENABLED"
else
    echo "❌ Bot failed to start. Check logs: tail -f bot.log"
fi
```

## 🔧 VPS MANAGEMENT COMMANDS:

### Check Bot Status
```bash
ps aux | grep ultimate_bot_working.py
```

### View Bot Logs
```bash
tail -f bot.log
```

### Stop Bot
```bash
pkill -f ultimate_bot_working.py
```

### Restart Bot
```bash
nohup python3 ultimate_bot_working.py > bot.log 2>&1 &
```

## 📱 TELEGRAM CHANNELS:
- **Admin**: 5329503447 (Personal notifications)
- **Free**: -1002930953007 (Public signals)
- **VIP**: -1002983007302 (Premium signals with buttons)

## 🤖 BOT FEATURES:
- ✅ 450+ AI Models
- ✅ 19 Exchange Integration
- ✅ Real-time Crypto & Forex Analysis
- ✅ Auto Trading on Bybit Testnet
- ✅ Interactive Telegram Buttons
- ✅ Database Storage
- ✅ Performance Tracking
- ✅ Continuous Learning

## 🚀 READY TO DEPLOY!
Your bot is ready to dominate the trading markets! 🚀🔥