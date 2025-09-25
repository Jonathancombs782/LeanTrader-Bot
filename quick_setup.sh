#!/bin/bash

# Quick Setup Script for Bybit Trading Bot
# This is the simplest way to get everything running

echo "🚀 Quick Setup for Bybit Trading Bot"
echo "===================================="
echo ""

# Check if we have SSH access
echo "🔍 Checking SSH access to VPS..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes root@75.119.149.117 exit 2>/dev/null; then
    echo "❌ SSH access failed. Please ensure:"
    echo "   - You have SSH access to root@75.119.149.117"
    echo "   - SSH keys are configured or password auth is enabled"
    echo "   - The VPS is running and accessible"
    exit 1
fi

echo "✅ SSH access confirmed"
echo ""

# Run the complete setup
echo "🎯 Running complete setup..."
./setup_bybit_bot.sh

echo ""
echo "🎉 Setup Complete! Your Bybit trading bot is ready!"
echo ""
echo "📊 Dashboard: http://75.119.149.117:8501"
echo "🔧 Configuration: /home/root/trading-bot/.env"
echo ""
echo "💡 Next steps:"
echo "1. Open the dashboard to monitor the bot"
echo "2. Configure your Bybit API keys in the .env file"
echo "3. Set up notifications (Telegram, email, etc.)"
echo "4. Start with small amounts for testing"
echo ""
echo "🚀 Happy trading!"