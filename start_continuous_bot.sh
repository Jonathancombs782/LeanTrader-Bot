#!/bin/bash

echo "🚀 Starting CONTINUOUS ULTRA TRADING SYSTEM on VPS..."
echo "📱 Telegram notifications will be sent to your chat"
echo "🔄 Bot will run continuously until you stop it with Ctrl+C"
echo ""

# Kill any existing bot processes
pkill -f continuous_ultra_bot.py

# Start the continuous bot
echo "Starting bot in 3 seconds..."
sleep 3

# Run the bot continuously
python3 continuous_ultra_bot.py

echo "Bot stopped."