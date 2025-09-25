#!/bin/bash
# ===============================================
# ULTIMATE ULTRA+ BOT DEPLOYMENT SCRIPT
# Complete deployment with all features
# ===============================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BOT_DIR="/opt/leantraderbot"
BACKUP_DIR="/opt/backups"
VENV_PATH="$BOT_DIR/venv"
SERVICE_NAME="ultra_plus"
DB_PATH="$BOT_DIR/ultra_plus.db"
LOG_DIR="$BOT_DIR/logs"
MODEL_DIR="$BOT_DIR/models"

echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
echo -e "${BLUE}    ULTIMATE ULTRA+ BOT DEPLOYMENT                    ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"

# ===============================================
# PHASE 1: BACKUP
# ===============================================
echo -e "\n${YELLOW}[1/8] Creating backups...${NC}"

# Create backup directory
sudo mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/ultra_plus_backup_$TIMESTAMP"

# Backup existing installation if exists
if [ -d "$BOT_DIR" ]; then
    echo "Backing up existing installation..."
    sudo tar -czf "$BACKUP_PATH.tar.gz" -C /opt leantraderbot 2>/dev/null || true
    
    # Backup database separately
    if [ -f "$DB_PATH" ]; then
        sudo cp "$DB_PATH" "$BACKUP_PATH.db"
        echo -e "${GREEN}✓ Database backed up${NC}"
    fi
    
    echo -e "${GREEN}✓ Backup created: $BACKUP_PATH.tar.gz${NC}"
else
    echo "No existing installation found, skipping backup"
fi

# ===============================================
# PHASE 2: SYSTEM PREPARATION
# ===============================================
echo -e "\n${YELLOW}[2/8] Preparing system...${NC}"

# Create user if not exists
if ! id -u trader &>/dev/null; then
    sudo useradd -m -s /bin/bash trader
    echo -e "${GREEN}✓ Created trader user${NC}"
fi

# Create directories
sudo mkdir -p "$BOT_DIR"
sudo mkdir -p "$LOG_DIR"
sudo mkdir -p "$MODEL_DIR"
sudo chown -R trader:trader "$BOT_DIR"

echo -e "${GREEN}✓ Directories created${NC}"

# ===============================================
# PHASE 3: PYTHON ENVIRONMENT
# ===============================================
echo -e "\n${YELLOW}[3/8] Setting up Python environment...${NC}"

# Install Python and dependencies
sudo apt-get update -qq
sudo apt-get install -y python3.10 python3.10-venv python3-pip build-essential \
    libssl-dev libffi-dev python3-dev libxml2-dev libxslt1-dev \
    libjpeg-dev zlib1g-dev libpq-dev redis-server postgresql \
    git curl wget htop iotop net-tools 2>/dev/null

echo -e "${GREEN}✓ System packages installed${NC}"

# Create virtual environment
if [ ! -d "$VENV_PATH" ]; then
    sudo -u trader python3 -m venv "$VENV_PATH"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# ===============================================
# PHASE 4: INSTALL PYTHON PACKAGES
# ===============================================
echo -e "\n${YELLOW}[4/8] Installing Python packages (CPU optimized)...${NC}"

# Create requirements file
cat > /tmp/requirements_ultra.txt << 'EOF'
# Core
numpy==1.24.3
pandas==2.0.3
scipy==1.11.1

# Trading
ccxt==4.1.22
yfinance==0.2.28
pandas-ta==0.3.14b0

# Machine Learning (CPU versions)
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

# Telegram
python-telegram-bot==20.4

# Web scraping
beautifulsoup4==4.12.2
feedparser==6.0.10
requests==2.31.0

# Utilities
python-dotenv==1.0.0
pyyaml==6.0.1
pytz==2023.3

# Monitoring
psutil==5.9.5
EOF

# Install packages
sudo -u trader $VENV_PATH/bin/pip install --upgrade pip setuptools wheel
sudo -u trader $VENV_PATH/bin/pip install -r /tmp/requirements_ultra.txt

echo -e "${GREEN}✓ Python packages installed${NC}"

# ===============================================
# PHASE 5: DEPLOY BOT CODE
# ===============================================
echo -e "\n${YELLOW}[5/8] Deploying bot code...${NC}"

# Copy main bot file
sudo cp ultimate_ultra_plus.py "$BOT_DIR/"
sudo chown trader:trader "$BOT_DIR/ultimate_ultra_plus.py"
sudo chmod 755 "$BOT_DIR/ultimate_ultra_plus.py"

echo -e "${GREEN}✓ Bot code deployed${NC}"

# ===============================================
# PHASE 6: DATABASE SETUP
# ===============================================
echo -e "\n${YELLOW}[6/8] Setting up database...${NC}"

# Initialize database (will be created by bot on first run)
sudo -u trader touch "$DB_PATH"
sudo chmod 664 "$DB_PATH"

echo -e "${GREEN}✓ Database prepared${NC}"

# ===============================================
# PHASE 7: CONFIGURATION
# ===============================================
echo -e "\n${YELLOW}[7/8] Creating configuration...${NC}"

# Create .env file template
cat > "$BOT_DIR/.env" << 'EOF'
# ULTIMATE ULTRA+ BOT CONFIGURATION
# =================================

# Trading Mode
USE_TESTNET=true
FORCE_LIVE=0

# Bybit API (Testnet)
BYBIT_TESTNET_API_KEY=your_testnet_api_key
BYBIT_TESTNET_API_SECRET=your_testnet_api_secret

# Bybit API (Live - BE CAREFUL!)
BYBIT_API_KEY=
BYBIT_API_SECRET=

# Binance (Optional spot mirror)
BINANCE_API_KEY=
BINANCE_API_SECRET=

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ADMIN_ID=your_admin_id

# Risk Management
MAX_DAILY_DD=0.05
MAX_SLOTS=5
DEFAULT_SIZE=100
DEFAULT_LEVERAGE=1

# Engine Toggles
ENABLE_MOON_SPOTTER=true
ENABLE_SCALPER=true
ENABLE_ARBITRAGE=true
ENABLE_FX_TRAINER=true
ENABLE_DL_STACK=false
ENABLE_WEB_CRAWLER=true

# Intervals (optimized for 6 vCPU, 12GB RAM)
HEARTBEAT_INTERVAL=5
SCALPER_INTERVAL=5
MOON_INTERVAL=10
ARBITRAGE_INTERVAL=12
FX_RETRAIN_INTERVAL=1800
NEWS_CRAWL_INTERVAL=300
EOF

sudo chown trader:trader "$BOT_DIR/.env"
sudo chmod 600 "$BOT_DIR/.env"

echo -e "${GREEN}✓ Configuration template created${NC}"
echo -e "${YELLOW}  ⚠️  Edit $BOT_DIR/.env with your API keys${NC}"

# ===============================================
# PHASE 8: SYSTEMD SERVICE
# ===============================================
echo -e "\n${YELLOW}[8/8] Installing systemd service...${NC}"

# Copy service file
sudo cp ultra_plus.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable $SERVICE_NAME

echo -e "${GREEN}✓ Service installed and enabled${NC}"

# ===============================================
# VERIFICATION
# ===============================================
echo -e "\n${BLUE}═══════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                DEPLOYMENT COMPLETE                   ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"

echo -e "\n${GREEN}✅ DEPLOYMENT CHECKLIST:${NC}"
echo -e "✓ Backup created: $BACKUP_PATH"
echo -e "✓ Python venv: $VENV_PATH"
echo -e "✓ Bot code: $BOT_DIR/ultimate_ultra_plus.py"
echo -e "✓ Database: $DB_PATH"
echo -e "✓ Service: $SERVICE_NAME"
echo -e "✓ Logs: $LOG_DIR"
echo -e "✓ Models: $MODEL_DIR"

echo -e "\n${YELLOW}NEXT STEPS:${NC}"
echo -e "1. Edit configuration:"
echo -e "   ${BLUE}sudo nano $BOT_DIR/.env${NC}"
echo -e ""
echo -e "2. Start the bot:"
echo -e "   ${BLUE}sudo systemctl start $SERVICE_NAME${NC}"
echo -e ""
echo -e "3. Check status:"
echo -e "   ${BLUE}sudo systemctl status $SERVICE_NAME${NC}"
echo -e ""
echo -e "4. View logs:"
echo -e "   ${BLUE}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e ""
echo -e "5. Stop the bot:"
echo -e "   ${BLUE}sudo systemctl stop $SERVICE_NAME${NC}"

echo -e "\n${GREEN}ROLLBACK INSTRUCTIONS:${NC}"
echo -e "If needed, restore from backup:"
echo -e "   ${BLUE}sudo systemctl stop $SERVICE_NAME${NC}"
echo -e "   ${BLUE}sudo tar -xzf $BACKUP_PATH.tar.gz -C /opt${NC}"
echo -e "   ${BLUE}sudo cp $BACKUP_PATH.db $DB_PATH${NC}"
echo -e "   ${BLUE}sudo systemctl start $SERVICE_NAME${NC}"

echo -e "\n${GREEN}🚀 Bot is ready to trade!${NC}"
echo -e "${YELLOW}⚠️  Remember: Currently in TESTNET mode (no real money)${NC}"