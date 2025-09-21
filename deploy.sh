#!/bin/bash

# Professional Trading Bot Deployment Script
# For VPS: 75.119.149.117 (Ubuntu 24.04)

set -e

echo "🚀 Starting Professional Trading Bot Deployment..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
echo "🐍 Installing Python and development tools..."
sudo apt install -y python3.11 python3.11-pip python3.11-venv python3.11-dev
sudo apt install -y build-essential cmake git curl wget
sudo apt install -y sqlite3 redis-server

# Install TA-Lib dependencies
echo "📊 Installing TA-Lib dependencies..."
sudo apt install -y build-essential wget
cd /tmp
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
sudo ldconfig

# Create project directory
echo "📁 Setting up project structure..."
cd /home/$USER
mkdir -p trading-bot
cd trading-bot

# Create virtual environment
echo "🔧 Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python packages
echo "📚 Installing Python packages..."
pip install -r requirements.txt

# Create necessary directories
mkdir -p {data,logs,models,config,scripts,dashboard}
mkdir -p data/{historical,realtime,backtest}
mkdir -p logs/{trading,errors,performance}
mkdir -p models/{ml,strategies}

# Set up environment file
echo "⚙️ Creating environment configuration..."
cat > .env << 'EOF'
# Trading Bot Configuration
BOT_NAME=ProfessionalTradingBot
VERSION=1.0.0

# Database Configuration
DATABASE_URL=sqlite:///data/trading_bot.db
REDIS_URL=redis://localhost:6379

# Exchange APIs (Add your keys here)
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key
COINBASE_API_KEY=your_coinbase_api_key
COINBASE_SECRET_KEY=your_coinbase_secret_key

# Trading Configuration
INITIAL_CAPITAL=10000
MAX_POSITION_SIZE=0.1
RISK_PER_TRADE=0.02
STOP_LOSS_PERCENT=0.05
TAKE_PROFIT_PERCENT=0.1

# ML Configuration
MODEL_RETRAIN_HOURS=24
LOOKBACK_PERIOD=1000
FEATURE_WINDOW=50
PREDICTION_HORIZON=5

# Notification Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_email_password

# Dashboard Configuration
DASHBOARD_PORT=8501
DASHBOARD_HOST=0.0.0.0

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/trading/trading_bot.log
EOF

# Set up systemd service
echo "🔧 Setting up systemd service..."
sudo tee /etc/systemd/system/trading-bot.service > /dev/null << EOF
[Unit]
Description=Professional Trading Bot
After=network.target redis.service

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/trading-bot
Environment=PATH=/home/$USER/trading-bot/venv/bin
ExecStart=/home/$USER/trading-bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Set up firewall
echo "🔥 Configuring firewall..."
sudo ufw allow ssh
sudo ufw allow 8501/tcp  # Dashboard
sudo ufw allow 8000/tcp  # API
sudo ufw --force enable

# Start Redis
echo "🗄️ Starting Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Reload systemd and enable service
echo "🔄 Enabling trading bot service..."
sudo systemctl daemon-reload
sudo systemctl enable trading-bot

# Create startup script
cat > start_bot.sh << 'EOF'
#!/bin/bash
cd /home/$USER/trading-bot
source venv/bin/activate
python main.py
EOF

chmod +x start_bot.sh

# Create monitoring script
cat > monitor.sh << 'EOF'
#!/bin/bash
echo "=== Trading Bot Status ==="
systemctl status trading-bot --no-pager
echo ""
echo "=== System Resources ==="
top -bn1 | head -20
echo ""
echo "=== Disk Usage ==="
df -h
echo ""
echo "=== Memory Usage ==="
free -h
EOF

chmod +x monitor.sh

echo "✅ Deployment completed successfully!"
echo ""
echo "🔧 Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Configure your trading parameters"
echo "3. Start the bot with: sudo systemctl start trading-bot"
echo "4. Check status with: sudo systemctl status trading-bot"
echo "5. View logs with: journalctl -u trading-bot -f"
echo "6. Access dashboard at: http://75.119.149.117:8501"
echo ""
echo "📊 Dashboard will be available at: http://75.119.149.117:8501"
echo "🔍 Monitor with: ./monitor.sh"