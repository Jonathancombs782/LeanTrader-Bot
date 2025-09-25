# 🚀 Start Your Bybit Trading Bot - VPS Commands

## **Copy and paste these commands on your VPS (75.119.149.117)**

### **Step 1: Connect to your VPS**
```bash
ssh root@75.119.149.117
```

### **Step 2: Run these commands one by one**

```bash
# Update system and install dependencies
apt update && apt upgrade -y
apt install -y python3.11 python3.11-pip python3.11-venv python3.11-dev build-essential cmake git curl wget sqlite3 redis-server

# Create project directory
mkdir -p /home/root/trading-bot
cd /home/root/trading-bot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python packages
pip install --upgrade pip
pip install numpy pandas scikit-learn tensorflow torch yfinance ccxt websocket-client fastapi uvicorn streamlit plotly dash sqlalchemy redis python-dotenv schedule loguru requests aiohttp cryptography bcrypt joblib

# Create directories
mkdir -p {data,logs,models,config,scripts,dashboard}
mkdir -p data/{historical,realtime,backtest}
mkdir -p logs/{trading,errors,performance}
mkdir -p models/{ml,strategies}

# Start Redis
systemctl enable redis-server
systemctl start redis-server

# Configure firewall
ufw allow ssh
ufw allow 8501/tcp
ufw allow 8000/tcp
ufw --force enable
```

### **Step 3: Create the environment file with your Bybit API keys**

```bash
cat > .env << 'EOF'
# Trading Bot Configuration
BOT_NAME=ProfessionalTradingBot
VERSION=1.0.0

# Database Configuration
DATABASE_URL=sqlite:///data/trading_bot.db
REDIS_URL=redis://localhost:6379

# Exchange APIs - Bybit Testnet
BYBIT_API_KEY=***REDACTED***
BYBIT_SECRET_KEY=***REDACTED***
BYBIT_SANDBOX=true

# Trading Configuration
INITIAL_CAPITAL=10000
MAX_POSITION_SIZE=0.1
RISK_PER_TRADE=0.02
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.1
MAX_POSITIONS=10
MIN_CONFIDENCE=0.7
TRADING_ENABLED=true

# ML Configuration
MODEL_RETRAIN_HOURS=24
LOOKBACK_PERIOD=1000
FEATURE_WINDOW=50
PREDICTION_HORIZON=5

# Risk Management
MAX_TOTAL_EXPOSURE=0.8
MAX_DRAWDOWN=0.15
MAX_VAR=0.05
MAX_CORRELATION=0.7
MAX_CONCENTRATION=0.3

# Dashboard Configuration
DASHBOARD_PORT=8501
DASHBOARD_HOST=0.0.0.0

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/trading/trading_bot.log
EOF
```

### **Step 4: Download the bot files**

Now I need to upload the bot files to your VPS. Let me create a simple way to do this: