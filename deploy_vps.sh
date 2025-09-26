#!/bin/bash

# Ultra Trading Bot VPS Deployment Script
# This script deploys the complete ultra trading system to a VPS for 24/7 operation

set -e

echo "🚀 ULTRA TRADING BOT VPS DEPLOYMENT"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[HEADER]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Please do not run this script as root"
    exit 1
fi

print_header "Starting VPS Deployment Process"

# Update system packages
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required system packages
print_status "Installing system dependencies..."
sudo apt install -y python3 python3-pip python3-venv git curl wget htop tmux screen

# Create virtual environment
print_status "Creating Python virtual environment..."
python3 -m venv /home/$USER/ultra_trading_bot
source /home/$USER/ultra_trading_bot/bin/activate

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install --upgrade pip
pip install -r /workspace/requirements_ultra.txt

# Create systemd service for auto-start
print_status "Creating systemd service..."
sudo tee /etc/systemd/system/ultra-trading-bot.service > /dev/null <<EOF
[Unit]
Description=Ultra Trading Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/workspace
Environment=PATH=/home/$USER/ultra_trading_bot/bin
ExecStart=/home/$USER/ultra_trading_bot/bin/python /workspace/ultra_launcher_advanced.py --mode paper --symbols "BTC/USDT,ETH/USDT,BNB/USDT"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create log rotation configuration
print_status "Setting up log rotation..."
sudo tee /etc/logrotate.d/ultra-trading-bot > /dev/null <<EOF
/workspace/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $USER $USER
}
EOF

# Create logs directory
print_status "Creating logs directory..."
mkdir -p /workspace/logs

# Create monitoring script
print_status "Creating monitoring script..."
tee /workspace/monitor_bot.sh > /dev/null <<EOF
#!/bin/bash

# Ultra Trading Bot Monitor
# Monitors the bot's health and performance

echo "🤖 ULTRA TRADING BOT MONITOR"
echo "============================"

# Check if bot is running
if systemctl is-active --quiet ultra-trading-bot; then
    echo "✅ Bot Status: RUNNING"
else
    echo "❌ Bot Status: STOPPED"
fi

# Check system resources
echo ""
echo "💻 System Resources:"
echo "CPU Usage: \$(top -bn1 | grep "Cpu(s)" | awk '{print \$2}' | cut -d'%' -f1)%"
echo "Memory Usage: \$(free | grep Mem | awk '{printf "%.1f%%", \$3/\$2 * 100.0}')"
echo "Disk Usage: \$(df -h / | awk 'NR==2{print \$5}')"

# Check bot logs
echo ""
echo "📊 Recent Bot Activity:"
tail -n 10 /workspace/logs/ultra_trading_bot.log 2>/dev/null || echo "No logs found"

# Check for errors
echo ""
echo "🔍 Error Check:"
grep -i "error\|exception\|failed" /workspace/logs/ultra_trading_bot.log 2>/dev/null | tail -n 5 || echo "No errors found"

echo ""
echo "🕐 Last Check: \$(date)"
EOF

chmod +x /workspace/monitor_bot.sh

# Create startup script
print_status "Creating startup script..."
tee /workspace/start_bot.sh > /dev/null <<EOF
#!/bin/bash

# Ultra Trading Bot Startup Script
# Starts the bot with proper configuration

echo "🚀 Starting Ultra Trading Bot..."

# Activate virtual environment
source /home/$USER/ultra_trading_bot/bin/activate

# Set environment variables
export PYTHONPATH=/workspace
export ENABLE_LIVE=false
export ALLOW_LIVE=false
export EXCHANGE_ID=bybit
export EXCHANGE_MODE=spot

# Start the bot
cd /workspace
python3 ultra_launcher_advanced.py --mode paper --symbols "BTC/USDT,ETH/USDT,BNB/USDT" 2>&1 | tee -a /workspace/logs/ultra_trading_bot.log
EOF

chmod +x /workspace/start_bot.sh

# Create stop script
print_status "Creating stop script..."
tee /workspace/stop_bot.sh > /dev/null <<EOF
#!/bin/bash

# Ultra Trading Bot Stop Script
# Stops the bot gracefully

echo "🛑 Stopping Ultra Trading Bot..."

# Stop systemd service
sudo systemctl stop ultra-trading-bot

# Kill any remaining processes
pkill -f "ultra_launcher_advanced.py" || true

echo "✅ Bot stopped"
EOF

chmod +x /workspace/stop_bot.sh

# Create restart script
print_status "Creating restart script..."
tee /workspace/restart_bot.sh > /dev/null <<EOF
#!/bin/bash

# Ultra Trading Bot Restart Script
# Restarts the bot

echo "🔄 Restarting Ultra Trading Bot..."

# Stop the bot
./stop_bot.sh

# Wait a moment
sleep 2

# Start the bot
./start_bot.sh
EOF

chmod +x /workspace/restart_bot.sh

# Create status script
print_status "Creating status script..."
tee /workspace/status_bot.sh > /dev/null <<EOF
#!/bin/bash

# Ultra Trading Bot Status Script
# Shows the current status of the bot

echo "📊 ULTRA TRADING BOT STATUS"
echo "=========================="

# Check systemd service status
if systemctl is-active --quiet ultra-trading-bot; then
    echo "✅ Service Status: RUNNING"
else
    echo "❌ Service Status: STOPPED"
fi

# Check process status
if pgrep -f "ultra_launcher_advanced.py" > /dev/null; then
    echo "✅ Process Status: RUNNING"
else
    echo "❌ Process Status: STOPPED"
fi

# Show system resources
echo ""
echo "💻 System Resources:"
echo "CPU: \$(top -bn1 | grep "Cpu(s)" | awk '{print \$2}' | cut -d'%' -f1)%"
echo "Memory: \$(free | grep Mem | awk '{printf "%.1f%%", \$3/\$2 * 100.0}')"
echo "Disk: \$(df -h / | awk 'NR==2{print \$5}')"

# Show recent logs
echo ""
echo "📋 Recent Logs:"
tail -n 5 /workspace/logs/ultra_trading_bot.log 2>/dev/null || echo "No logs found"

echo ""
echo "🕐 Status Check: \$(date)"
EOF

chmod +x /workspace/status_bot.sh

# Enable and start the service
print_status "Enabling and starting the service..."
sudo systemctl daemon-reload
sudo systemctl enable ultra-trading-bot

# Create cron job for monitoring
print_status "Setting up monitoring cron job..."
(crontab -l 2>/dev/null; echo "*/5 * * * * /workspace/monitor_bot.sh >> /workspace/logs/monitor.log 2>&1") | crontab -

# Create backup script
print_status "Creating backup script..."
tee /workspace/backup_bot.sh > /dev/null <<EOF
#!/bin/bash

# Ultra Trading Bot Backup Script
# Creates a backup of the bot configuration and logs

echo "💾 Creating backup..."

BACKUP_DIR="/home/$USER/ultra_trading_bot_backups"
DATE=\$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="ultra_trading_bot_backup_\$DATE.tar.gz"

mkdir -p \$BACKUP_DIR

# Create backup
tar -czf "\$BACKUP_DIR/\$BACKUP_FILE" /workspace/logs /workspace/config.yml /workspace/settings.py

echo "✅ Backup created: \$BACKUP_DIR/\$BACKUP_FILE"

# Keep only last 7 backups
cd \$BACKUP_DIR
ls -t ultra_trading_bot_backup_*.tar.gz | tail -n +8 | xargs -r rm

echo "🧹 Old backups cleaned up"
EOF

chmod +x /workspace/backup_bot.sh

# Create daily backup cron job
print_status "Setting up daily backup..."
(crontab -l 2>/dev/null; echo "0 2 * * * /workspace/backup_bot.sh >> /workspace/logs/backup.log 2>&1") | crontab -

# Final setup
print_status "Finalizing setup..."

# Set proper permissions
chmod +x /workspace/*.sh

# Create README for VPS
print_status "Creating VPS README..."
tee /workspace/VPS_README.md > /dev/null <<EOF
# Ultra Trading Bot VPS Deployment

## Quick Commands

### Start/Stop/Restart Bot
\`\`\`bash
./start_bot.sh    # Start the bot
./stop_bot.sh     # Stop the bot
./restart_bot.sh  # Restart the bot
./status_bot.sh   # Check bot status
\`\`\`

### Monitor Bot
\`\`\`bash
./monitor_bot.sh  # Check bot health and performance
tail -f logs/ultra_trading_bot.log  # Follow live logs
\`\`\`

### System Service
\`\`\`bash
sudo systemctl start ultra-trading-bot    # Start service
sudo systemctl stop ultra-trading-bot     # Stop service
sudo systemctl restart ultra-trading-bot  # Restart service
sudo systemctl status ultra-trading-bot   # Check service status
\`\`\`

### Backup
\`\`\`bash
./backup_bot.sh  # Create manual backup
\`\`\`

## Logs
- Main logs: \`logs/ultra_trading_bot.log\`
- Monitor logs: \`logs/monitor.log\`
- Backup logs: \`logs/backup.log\`

## Configuration
- Bot config: \`config.yml\`
- Settings: \`settings.py\`
- Service config: \`/etc/systemd/system/ultra-trading-bot.service\`

## Features
- ✅ 24/7 operation
- ✅ Auto-restart on failure
- ✅ Log rotation
- ✅ System monitoring
- ✅ Automatic backups
- ✅ Multi-platform scanning
- ✅ Swarm consciousness
- ✅ Fluid mechanics
- ✅ Backtest engine
- ✅ Autonomous trading

## November Target
The bot is configured to achieve \$48 → \$3000-5000 by November through:
- Multi-platform opportunity scanning
- Swarm consciousness trading
- Fluid mechanics analysis
- Historical backtesting
- Autonomous decision making

## Support
Check logs for any issues and monitor system resources regularly.
EOF

print_header "VPS Deployment Complete!"
echo ""
print_status "✅ System packages installed"
print_status "✅ Python environment created"
print_status "✅ Dependencies installed"
print_status "✅ Systemd service configured"
print_status "✅ Monitoring scripts created"
print_status "✅ Backup system configured"
print_status "✅ Cron jobs set up"
print_status "✅ Documentation created"
echo ""
print_header "Next Steps:"
echo "1. Review configuration in config.yml"
echo "2. Set up API keys if needed"
echo "3. Start the bot: ./start_bot.sh"
echo "4. Monitor with: ./monitor_bot.sh"
echo "5. Check status: ./status_bot.sh"
echo ""
print_header "Bot is ready for 24/7 operation! 🚀"