#!/bin/bash

# Upload Trading Bot to VPS
# VPS: 75.119.149.117 (Ubuntu 24.04)

set -e

VPS_IP="75.119.149.117"
VPS_USER="root"  # Change this to your actual username if different
VPS_PATH="/home/$VPS_USER/trading-bot"

echo "🚀 Uploading Professional Trading Bot to VPS..."
echo "📍 VPS: $VPS_IP"
echo "👤 User: $VPS_USER"
echo "📁 Path: $VPS_PATH"
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "❌ Error: main.py not found. Please run this script from the trading-bot directory."
    exit 1
fi

echo "📦 Creating archive of all files..."
tar -czf trading-bot.tar.gz \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='venv' \
    --exclude='.env' \
    --exclude='data' \
    --exclude='logs' \
    --exclude='models' \
    .

echo "📤 Uploading files to VPS..."
scp trading-bot.tar.gz $VPS_USER@$VPS_IP:/tmp/

echo "🔧 Extracting files on VPS..."
ssh $VPS_USER@$VPS_IP << 'EOF'
    # Create trading-bot directory
    mkdir -p /home/root/trading-bot
    
    # Extract files
    cd /home/root/trading-bot
    tar -xzf /tmp/trading-bot.tar.gz
    
    # Clean up
    rm /tmp/trading-bot.tar.gz
    
    # Set permissions
    chmod +x deploy.sh
    chmod +x start_dashboard.sh
    chmod +x monitor.sh
    
    echo "✅ Files extracted successfully"
EOF

echo "🧹 Cleaning up local archive..."
rm trading-bot.tar.gz

echo "✅ Upload completed successfully!"
echo ""
echo "🔧 Next steps:"
echo "1. SSH into your VPS: ssh $VPS_USER@$VPS_IP"
echo "2. Navigate to: cd /home/$VPS_USER/trading-bot"
echo "3. Run deployment: ./deploy.sh"
echo "4. Configure API keys in .env file"
echo "5. Start the bot: sudo systemctl start trading-bot"
echo ""
echo "📊 Dashboard will be available at: http://$VPS_IP:8501"