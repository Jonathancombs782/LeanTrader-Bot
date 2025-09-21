#!/bin/bash

echo "🚀 COMPLETE VPS SETUP FOR ULTRA TRADING SYSTEM"
echo "=============================================="
echo ""

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install required packages
echo "📦 Installing required packages..."
apt install -y python3 python3-pip python3-venv git curl wget htop nano

# Install Python packages
echo "🐍 Installing Python packages..."
pip3 install --break-system-packages ccxt pandas numpy scikit-learn loguru beautifulsoup4 lxml requests python-telegram-bot schedule joblib sqlite3

# Create bot directory
echo "📁 Creating bot directory..."
mkdir -p /root/ultra_trading_bot
cd /root/ultra_trading_bot

# Create startup script
echo "📝 Creating startup script..."
cat > start_bot.sh << 'EOF'
#!/bin/bash

echo "🚀 Starting ULTRA TRADING SYSTEM..."
echo "📱 Multi-Channel Notifications Enabled"
echo "🔄 Running continuously on VPS"
echo ""

# Kill any existing bot processes
pkill -f multi_channel_ultra_bot.py

# Start the bot
python3 multi_channel_ultra_bot.py
EOF

chmod +x start_bot.sh

# Create systemd service for auto-start
echo "⚙️ Creating systemd service..."
cat > /etc/systemd/system/ultra-trading-bot.service << 'EOF'
[Unit]
Description=Ultra Trading System Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ultra_trading_bot
ExecStart=/usr/bin/python3 /root/ultra_trading_bot/multi_channel_ultra_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
systemctl daemon-reload
systemctl enable ultra-trading-bot.service

echo ""
echo "✅ VPS SETUP COMPLETE!"
echo "======================"
echo ""
echo "📁 Bot directory: /root/ultra_trading_bot"
echo "🚀 Start command: ./start_bot.sh"
echo "⚙️ Service name: ultra-trading-bot"
echo ""
echo "🔧 SERVICE COMMANDS:"
echo "  Start: systemctl start ultra-trading-bot"
echo "  Stop:  systemctl stop ultra-trading-bot"
echo "  Status: systemctl status ultra-trading-bot"
echo "  Logs:  journalctl -u ultra-trading-bot -f"
echo ""
echo "📱 CHANNELS CONFIGURED:"
echo "  Free Channel: -1002930953007"
echo "  VIP Channel: -1002983007302 (with trade buttons)"
echo "  Admin Chat: 5329503447 (system updates only)"
echo ""
echo "🎯 Ready to start the bot!"
echo ""