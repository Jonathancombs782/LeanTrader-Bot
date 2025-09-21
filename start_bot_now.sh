#!/bin/bash

# Start Bybit Trading Bot with Testnet API Keys
# Run this on your VPS: 75.119.149.117

set -e

echo "🚀 Starting Professional Bybit Trading Bot"
echo "=========================================="
echo "📍 VPS: $(hostname)"
echo "🔑 Using Bybit Testnet API"
echo ""

# Create project directory
echo "📁 Setting up project structure..."
mkdir -p trading-bot
cd trading-bot

# Download and install Python dependencies
echo "🐍 Installing Python and dependencies..."
apt update
apt install -y python3.11 python3.11-pip python3.11-venv python3.11-dev build-essential cmake git curl wget sqlite3 redis-server

# Create virtual environment
echo "🔧 Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install required packages
echo "📚 Installing Python packages..."
pip install numpy==1.24.3 pandas==2.0.3 scikit-learn==1.3.0 tensorflow==2.13.0 torch==2.0.1 yfinance==0.2.18 ccxt==4.0.77 websocket-client==1.6.3 fastapi==0.103.1 uvicorn==0.23.2 streamlit==1.25.0 plotly==5.15.0 dash==2.13.0 sqlalchemy==2.0.19 redis==4.6.0 python-dotenv==1.0.0 schedule==1.2.0 loguru==0.7.0 requests==2.31.0 aiohttp==3.8.5 cryptography==41.0.3 bcrypt==4.0.1 asyncio concurrent.futures joblib==1.3.2

# Create necessary directories
mkdir -p {data,logs,models,config,scripts,dashboard}
mkdir -p data/{historical,realtime,backtest}
mkdir -p logs/{trading,errors,performance}
mkdir -p models/{ml,strategies}

# Create environment file with Bybit testnet API keys
echo "⚙️ Creating environment configuration..."
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

# Notification Configuration
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=
EMAIL_PASSWORD=

# Dashboard Configuration
DASHBOARD_PORT=8501
DASHBOARD_HOST=0.0.0.0

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/trading/trading_bot.log
EOF

# Start Redis
echo "🗄️ Starting Redis..."
systemctl enable redis-server
systemctl start redis-server

# Set up firewall
echo "🔥 Configuring firewall..."
ufw allow ssh
ufw allow 8501/tcp
ufw allow 8000/tcp
ufw --force enable

echo "✅ Environment setup complete!"
echo ""
echo "🎯 Next: Run the bot with: python main.py"
echo "📊 Dashboard will be at: http://75.119.149.117:8501"