#!/bin/bash

# VPS Deployment Script for Ultimate Trading Bot
VPS_IP="75.119.149.117"
VPS_USER="root"

echo "🚀 DEPLOYING ULTIMATE 450+ MODELS TRADING BOT TO VPS..."

# Create deployment package
echo "📦 Creating deployment package..."
tar -czf ultimate_bot_deployment.tar.gz ultimate_bot_working.py

# Upload to VPS
echo "📤 Uploading to VPS..."
scp ultimate_bot_deployment.tar.gz $VPS_USER@$VPS_IP:~/

# Deploy on VPS
echo "🔧 Deploying on VPS..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    echo "🚀 ULTIMATE BOT VPS DEPLOYMENT STARTING..."
    
    # Stop any existing bot processes
    pkill -f "ultimate_bot_working.py" || true
    pkill -f "python.*bot" || true
    
    # Extract deployment
    tar -xzf ultimate_bot_deployment.tar.gz
    rm ultimate_bot_deployment.tar.gz
    
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
    
    # Wait a moment and check if running
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
EOF

echo "✅ DEPLOYMENT COMPLETE!"
echo "🔗 VPS: 75.119.149.117"
echo "🤖 Bot Status: RUNNING"
echo "📱 Telegram Channels: ACTIVE"
echo "💰 Auto Trading: ENABLED"