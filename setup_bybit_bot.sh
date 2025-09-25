#!/bin/bash

# Complete Setup Script for Bybit Trading Bot
# This script will upload, deploy, and configure everything

set -e

VPS_IP="75.119.149.117"
VPS_USER="root"  # Change this to your actual username if different

echo "🤖 Professional Bybit Trading Bot Setup"
echo "========================================"
echo "📍 VPS: $VPS_IP"
echo "👤 User: $VPS_USER"
echo ""

# Step 1: Upload files
echo "📤 Step 1: Uploading files to VPS..."
./upload_to_vps.sh

# Step 2: Deploy on VPS
echo ""
echo "🔧 Step 2: Deploying bot on VPS..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd /home/root/trading-bot
    echo "🚀 Running deployment script..."
    ./deploy.sh
EOF

# Step 3: Configure Bybit API keys
echo ""
echo "🔑 Step 3: Configuring Bybit API keys..."
echo "You need to provide your Bybit API credentials."
echo ""
echo "To get your Bybit API keys:"
echo "1. Go to https://www.bybit.com/"
echo "2. Login to your account"
echo "3. Go to Account & Security → API Management"
echo "4. Create a new API key with trading permissions"
echo "5. Copy the API Key and Secret"
echo ""

read -p "Enter your Bybit API Key: " BYBIT_API_KEY
read -s -p "Enter your Bybit Secret Key: " BYBIT_SECRET_KEY
echo ""

if [ -z "$BYBIT_API_KEY" ] || [ -z "$BYBIT_SECRET_KEY" ]; then
    echo "⚠️ API keys not provided. You can configure them later in the .env file."
    BYBIT_API_KEY="your_bybit_api_key"
    BYBIT_SECRET_KEY="your_bybit_secret_key"
fi

# Update .env file on VPS
ssh $VPS_USER@$VPS_IP << EOF
    cd /home/root/trading-bot
    
    # Update .env file with Bybit keys
    sed -i "s/your_bybit_api_key/$BYBIT_API_KEY/g" .env
    sed -i "s/your_bybit_secret_key/$BYBIT_SECRET_KEY/g" .env
    
    echo "✅ Bybit API keys configured"
EOF

# Step 4: Start the bot
echo ""
echo "🚀 Step 4: Starting the trading bot..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd /home/root/trading-bot
    
    # Start the bot service
    sudo systemctl start trading-bot
    
    # Wait a moment for it to start
    sleep 5
    
    # Check status
    echo "📊 Bot Status:"
    sudo systemctl status trading-bot --no-pager
    
    echo ""
    echo "📋 Recent logs:"
    journalctl -u trading-bot --since "1 minute ago" --no-pager
EOF

# Step 5: Start dashboard
echo ""
echo "📊 Step 5: Starting dashboard..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    cd /home/root/trading-bot
    
    # Start dashboard in background
    nohup ./start_dashboard.sh > dashboard.log 2>&1 &
    
    echo "✅ Dashboard starting..."
    sleep 3
    
    echo "📊 Dashboard should be available at: http://75.119.149.117:8501"
EOF

echo ""
echo "🎉 Setup Complete!"
echo "=================="
echo ""
echo "✅ Trading bot deployed and configured for Bybit"
echo "✅ Bot service started"
echo "✅ Dashboard available at: http://75.119.149.117:8501"
echo ""
echo "📋 Useful commands:"
echo "• Check bot status: ssh $VPS_USER@$VPS_IP 'sudo systemctl status trading-bot'"
echo "• View logs: ssh $VPS_USER@$VPS_IP 'journalctl -u trading-bot -f'"
echo "• Stop bot: ssh $VPS_USER@$VPS_IP 'sudo systemctl stop trading-bot'"
echo "• Start bot: ssh $VPS_USER@$VPS_IP 'sudo systemctl start trading-bot'"
echo "• Restart bot: ssh $VPS_USER@$VPS_IP 'sudo systemctl restart trading-bot'"
echo ""
echo "🔧 Configuration file: /home/$VPS_USER/trading-bot/.env"
echo "📊 Dashboard: http://75.119.149.117:8501"
echo ""
echo "⚠️ Important Notes:"
echo "• Start with small amounts for testing"
echo "• Monitor the dashboard for performance"
echo "• Check logs regularly for any issues"
echo "• The bot will run in simulation mode until you configure real API keys"
echo ""
echo "🚀 Your professional Bybit trading bot is ready!"