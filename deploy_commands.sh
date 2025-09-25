#!/bin/bash
# ============================================================
# ULTIMATE ULTRA+ BOT DEPLOYMENT COMMANDS
# Execute these commands on your VPS
# ============================================================

cat << 'DEPLOY_SCRIPT' > /tmp/deploy_ultra.sh
#!/bin/bash
set -e

echo "============================================================"
echo "   ULTIMATE ULTRA+ BOT DEPLOYMENT - FULL GOD MODE"
echo "   VPS: 6 vCPU / 12 GB RAM - OPTIMIZED"
echo "============================================================"

# Step 1: Backup existing installation
echo -e "\n[1/15] Creating backup..."
if [ -d /opt/leantraderbot ]; then
    mkdir -p /opt/backups
    tar -czf /opt/backups/backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /opt leantraderbot 2>/dev/null || true
    echo "✓ Backup created"
else
    echo "✓ No existing installation to backup"
fi

# Step 2: System dependencies
echo -e "\n[2/15] Installing system dependencies..."
apt-get update -qq
apt-get install -y python3.10 python3.10-venv python3-pip \
    build-essential libssl-dev libffi-dev python3-dev \
    git curl wget htop iotop net-tools sqlite3 \
    libxml2-dev libxslt1-dev libjpeg-dev zlib1g-dev \
    redis-server postgresql-client 2>/dev/null
echo "✓ System packages installed"

# Step 3: Create directory structure
echo -e "\n[3/15] Creating directories..."
mkdir -p /opt/leantraderbot/{logs,models,data,backups}
mkdir -p /opt/backups
echo "✓ Directories created"

# Step 4: Create Python virtual environment
echo -e "\n[4/15] Setting up Python environment..."
cd /opt/leantraderbot
if [ ! -d venv ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment exists"
fi

# Step 5: Install Python packages (optimized for VPS)
echo -e "\n[5/15] Installing Python packages..."
cat > /tmp/requirements_ultra.txt << 'EOF'
# Core
numpy==1.24.3
pandas==2.0.3
scipy==1.11.1

# Trading
ccxt==4.1.22
yfinance==0.2.28
pandas-ta==0.3.14b0

# Machine Learning (CPU optimized)
scikit-learn==1.3.0
joblib==1.3.2
xgboost==1.7.6
lightgbm==4.0.0

# Database
sqlalchemy==2.0.19
redis==4.6.0

# Async
aiohttp==3.8.5
asyncio==3.4.3
nest-asyncio==1.5.8

# Telegram
python-telegram-bot==20.4

# Web scraping
beautifulsoup4==4.12.2
feedparser==6.0.10
requests==2.31.0
lxml==4.9.3

# Crypto/Web3
web3==6.11.3
pycryptodome==3.19.0

# Utilities
python-dotenv==1.0.0
pyyaml==6.0.1
pytz==2023.3
psutil==5.9.5

# Technical Analysis
ta==0.10.2
EOF

/opt/leantraderbot/venv/bin/pip install --upgrade pip setuptools wheel
/opt/leantraderbot/venv/bin/pip install -r /tmp/requirements_ultra.txt
echo "✓ Python packages installed"

# Step 6: Download bot code from GitHub or create it
echo -e "\n[6/15] Deploying bot code..."
# The bot code will be added via the second script
echo "✓ Ready for bot code deployment"

# Step 7: Create optimized configuration
echo -e "\n[7/15] Creating configuration..."
cat > /opt/leantraderbot/.env << 'EOF'
# ULTIMATE ULTRA+ BOT CONFIGURATION
# Optimized for Maximum Profit & 24/7 Operation
# ================================================

# TRADING MODE - START WITH TESTNET
USE_TESTNET=true
FORCE_LIVE=0

# BYBIT API (Testnet - get from testnet.bybit.com)
BYBIT_TESTNET_API_KEY=
BYBIT_TESTNET_API_SECRET=

# BYBIT LIVE (Add when ready for real trading)
BYBIT_API_KEY=
BYBIT_API_SECRET=

# BINANCE (Optional spot mirror)
BINANCE_API_KEY=
BINANCE_API_SECRET=

# TELEGRAM (Required)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ADMIN_ID=

# RISK MANAGEMENT
MAX_DAILY_DD=0.05        # 5% max daily drawdown
MAX_SLOTS=5              # Max concurrent positions
DEFAULT_SIZE=100         # Position size in USD
DEFAULT_LEVERAGE=2       # Start with 2x leverage

# ALL ENGINES ON FOR MAXIMUM PROFIT
ENABLE_MOON_SPOTTER=true      # Find 0.00000x gems
ENABLE_SCALPER=true           # 1m/5m scalping
ENABLE_ARBITRAGE=true         # Cross-exchange opportunities
ENABLE_FX_TRAINER=true        # Forex + XAUUSD
ENABLE_DL_STACK=false         # Keep OFF to save CPU
ENABLE_WEB_CRAWLER=true       # News sentiment

# OPTIMIZED INTERVALS FOR 6 vCPU / 12GB RAM
HEARTBEAT_INTERVAL=5          # 5 min heartbeat
SCALPER_INTERVAL=3            # Ultra-fast scalping
MOON_INTERVAL=8               # Moon token scanning
ARBITRAGE_INTERVAL=10         # Arbitrage scanning
FX_RETRAIN_INTERVAL=1800      # 30 min model retrain
NEWS_CRAWL_INTERVAL=180       # 3 min news updates

# ADVANCED FEATURES (God Mode)
ENABLE_QUANTUM=true           # Quantum price prediction
ENABLE_NEURAL_SWARM=true      # 100 agent swarm
ENABLE_FRACTAL=true           # Fractal market analysis
ENABLE_SMART_MONEY=true       # Whale tracking

# MODEL PERSISTENCE
MODEL_SAVE_PATH=/opt/leantraderbot/models
MODEL_BACKUP_ENABLED=true
MODEL_VERSION_CONTROL=true
AUTO_RETRAIN=true
RETAIN_KNOWLEDGE=true

# PERFORMANCE TARGETS
DAILY_PROFIT_TARGET=0.03      # 3% daily target
WEEKLY_PROFIT_TARGET=0.20     # 20% weekly target
COMPOUND_PROFITS=true         # Reinvest profits
EOF

chmod 600 /opt/leantraderbot/.env
echo "✓ Configuration created"

# Step 8: Create systemd service for 24/7 operation
echo -e "\n[8/15] Installing systemd service..."
cat > /etc/systemd/system/ultra_plus.service << 'EOF'
[Unit]
Description=Ultimate Ultra+ Trading Bot - Hedge Fund Grade
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/leantraderbot
Environment="PYTHONPATH=/opt/leantraderbot"
Environment="PYTHONUNBUFFERED=1"

# Main bot execution
ExecStart=/opt/leantraderbot/venv/bin/python /opt/leantraderbot/ultimate_ultra_plus.py

# Auto-restart for 24/7 operation
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Resource optimization for your VPS
CPUQuota=500%
MemoryLimit=10G
TasksMax=100

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ultra_plus

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ultra_plus
echo "✓ Service installed and enabled for 24/7 operation"

# Step 9: Create monitoring script
echo -e "\n[9/15] Setting up auto-monitoring..."
cat > /opt/leantraderbot/monitor.sh << 'EOF'
#!/bin/bash
# Ultra+ Bot Health Monitor - Ensures 24/7 operation

LOG_FILE="/opt/leantraderbot/logs/monitor.log"

while true; do
    # Check if service is running
    if ! systemctl is-active ultra_plus >/dev/null 2>&1; then
        echo "$(date): Bot stopped, auto-restarting..." >> $LOG_FILE
        systemctl start ultra_plus
    fi
    
    # Check memory usage
    MEM_USED=$(free | grep Mem | awk '{print int(($3/$2) * 100)}')
    if [ "$MEM_USED" -gt 90 ]; then
        echo "$(date): High memory ($MEM_USED%), restarting bot..." >> $LOG_FILE
        systemctl restart ultra_plus
    fi
    
    # Check if bot is responsive
    if [ -f /opt/leantraderbot/logs/ultra_plus.log ]; then
        LAST_LOG=$(stat -c %Y /opt/leantraderbot/logs/ultra_plus.log)
        CURRENT=$(date +%s)
        DIFF=$((CURRENT - LAST_LOG))
        
        # If no logs for 10 minutes, restart
        if [ $DIFF -gt 600 ]; then
            echo "$(date): Bot unresponsive, restarting..." >> $LOG_FILE
            systemctl restart ultra_plus
        fi
    fi
    
    sleep 60
done
EOF

chmod +x /opt/leantraderbot/monitor.sh
echo "✓ Monitor script created"

# Step 10: Add to crontab for startup
echo -e "\n[10/15] Setting up auto-start on boot..."
(crontab -l 2>/dev/null | grep -v monitor.sh; echo "@reboot /opt/leantraderbot/monitor.sh > /dev/null 2>&1 &") | crontab -
echo "✓ Auto-start configured"

# Step 11: Create log rotation
echo -e "\n[11/15] Setting up log rotation..."
cat > /etc/logrotate.d/ultra_plus << 'EOF'
/opt/leantraderbot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOF
echo "✓ Log rotation configured"

# Step 12: Initialize database
echo -e "\n[12/15] Initializing database..."
touch /opt/leantraderbot/ultra_plus.db
chmod 664 /opt/leantraderbot/ultra_plus.db
echo "✓ Database prepared"

# Step 13: Create model directories
echo -e "\n[13/15] Setting up model persistence..."
mkdir -p /opt/leantraderbot/models/{fx,crypto,quantum,neural}
echo "✓ Model directories created"

# Step 14: Set permissions
echo -e "\n[14/15] Setting permissions..."
chown -R root:root /opt/leantraderbot
chmod -R 755 /opt/leantraderbot
chmod 600 /opt/leantraderbot/.env
echo "✓ Permissions set"

# Step 15: Create quick commands
echo -e "\n[15/15] Creating quick commands..."
cat > /usr/local/bin/ultra << 'EOF'
#!/bin/bash
case "$1" in
    start)
        systemctl start ultra_plus
        echo "Bot started"
        ;;
    stop)
        systemctl stop ultra_plus
        echo "Bot stopped"
        ;;
    restart)
        systemctl restart ultra_plus
        echo "Bot restarted"
        ;;
    status)
        systemctl status ultra_plus
        ;;
    logs)
        journalctl -u ultra_plus -f
        ;;
    config)
        nano /opt/leantraderbot/.env
        ;;
    *)
        echo "Usage: ultra {start|stop|restart|status|logs|config}"
        ;;
esac
EOF

chmod +x /usr/local/bin/ultra
echo "✓ Quick commands created"

echo ""
echo "============================================================"
echo "   DEPLOYMENT COMPLETE - BOT READY FOR 24/7 OPERATION!"
echo "============================================================"
echo ""
echo "QUICK COMMANDS:"
echo "  ultra start   - Start the bot"
echo "  ultra stop    - Stop the bot"
echo "  ultra restart - Restart the bot"
echo "  ultra status  - Check status"
echo "  ultra logs    - View live logs"
echo "  ultra config  - Edit configuration"
echo ""
echo "NEXT STEPS:"
echo "1. Add your API keys: nano /opt/leantraderbot/.env"
echo "2. Start the bot: ultra start"
echo "3. Check status: ultra status"
echo "4. Monitor logs: ultra logs"
echo ""
echo "The bot will:"
echo "✓ Run 24/7 with auto-restart"
echo "✓ Trade on all markets (crypto, forex, metals)"
echo "✓ Find moon tokens (0.00000x gems)"
echo "✓ Execute scalping strategies"
echo "✓ Track arbitrage opportunities"
echo "✓ Analyze news sentiment"
echo "✓ Send signals to Telegram"
echo "✓ Save and retain all models"
echo "✓ Optimize for daily/weekly profits"
echo ""
echo "🚀 ULTRA+ BOT IS READY TO DOMINATE THE MARKETS!"

DEPLOY_SCRIPT

echo "============================================"
echo "DEPLOYMENT SCRIPT CREATED"
echo "============================================"
echo ""
echo "TO DEPLOY ON YOUR VPS:"
echo ""
echo "1. SSH into your VPS:"
echo "   ssh root@75.119.149.117"
echo ""
echo "2. Run this command to create the deployment script:"
echo "   cat > /tmp/deploy_ultra.sh << 'EOF'"
echo "   [PASTE THE CONTENT ABOVE]"
echo "   EOF"
echo ""
echo "3. Make it executable and run:"
echo "   chmod +x /tmp/deploy_ultra.sh"
echo "   /tmp/deploy_ultra.sh"
echo ""
echo "4. Then copy the bot code (see next file)"
echo ""