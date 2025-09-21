# 🤖 Professional Trading Bot

Advanced ML-powered trading bot with real-time learning, risk management, and comprehensive monitoring.

## 🚀 Features

### 🧠 Machine Learning Engine
- **LSTM Neural Networks** for price prediction
- **Random Forest** and **Gradient Boosting** ensemble models
- **Real-time feature engineering** with technical indicators
- **Automated model retraining** with performance monitoring
- **Ensemble predictions** combining multiple models

### 📊 Data Collection
- **Multi-exchange support** (Binance, Coinbase Pro, Yahoo Finance)
- **Real-time WebSocket** data feeds
- **Historical data collection** and storage
- **Technical indicators** (RSI, MACD, Bollinger Bands, etc.)
- **Volume and momentum analysis**

### 🛡️ Risk Management
- **Advanced risk metrics** (VaR, Sharpe ratio, drawdown)
- **Position sizing** using Kelly Criterion
- **Stop-loss and take-profit** automation
- **Portfolio exposure limits**
- **Correlation and concentration risk** monitoring
- **Emergency stop** functionality

### 📱 Notifications
- **Telegram** bot integration
- **Email** alerts
- **SMS** notifications (Twilio)
- **Webhook** support
- **Rate limiting** and smart filtering

### 📈 Dashboard
- **Real-time monitoring** with Streamlit
- **Portfolio visualization** and performance tracking
- **ML model performance** metrics
- **Risk monitoring** and alerts
- **Trade history** and analysis

## 🛠️ Installation

### Prerequisites
- Ubuntu 24.04 VPS
- Python 3.11+
- 2GB+ RAM
- 20GB+ SSD storage

### Quick Setup

1. **Upload the bot to your VPS:**
```bash
# On your local machine
scp -r /workspace/* user@75.119.149.117:/home/user/trading-bot/
```

2. **SSH into your VPS:**
```bash
ssh user@75.119.149.117
```

3. **Run the deployment script:**
```bash
cd /home/user/trading-bot
chmod +x deploy.sh
./deploy.sh
```

4. **Configure your API keys:**
```bash
nano .env
# Add your exchange API keys and notification settings
```

5. **Start the bot:**
```bash
sudo systemctl start trading-bot
```

6. **Access the dashboard:**
Open your browser and go to: `http://75.119.149.117:8501`

## ⚙️ Configuration

### Environment Variables (.env file)

```env
# Bot Configuration
BOT_NAME=ProfessionalTradingBot
VERSION=1.0.0
TRADING_ENABLED=true

# Exchange APIs
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key
BINANCE_SANDBOX=false

COINBASE_API_KEY=your_coinbase_api_key
COINBASE_SECRET_KEY=your_coinbase_secret_key
COINBASE_PASSPHRASE=your_passphrase

# Trading Parameters
INITIAL_CAPITAL=10000
MAX_POSITION_SIZE=0.1
MAX_POSITIONS=10
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.1
MIN_CONFIDENCE=0.7

# Risk Management
MAX_TOTAL_EXPOSURE=0.8
MAX_DRAWDOWN=0.15
MAX_VAR=0.05
MAX_CORRELATION=0.7
MAX_CONCENTRATION=0.3

# ML Configuration
MODEL_RETRAIN_HOURS=24
LOOKBACK_PERIOD=1000
FEATURE_WINDOW=50
PREDICTION_HORIZON=5

# Notifications
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_email_password

TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+1234567890
TWILIO_TO_NUMBER=+1234567890

# Dashboard
DASHBOARD_PORT=8501
DASHBOARD_HOST=0.0.0.0

# Logging
LOG_LEVEL=INFO
```

## 🎯 Usage

### Starting the Bot
```bash
# Start the trading bot service
sudo systemctl start trading-bot

# Check status
sudo systemctl status trading-bot

# View logs
journalctl -u trading-bot -f
```

### Dashboard Access
- **URL:** http://75.119.149.117:8501
- **Features:** Real-time monitoring, portfolio tracking, risk metrics
- **Controls:** Start/stop bot, view trades, monitor performance

### Manual Controls
```bash
# Start bot manually
cd /home/user/trading-bot
source venv/bin/activate
python main.py

# Start dashboard only
./start_dashboard.sh

# Monitor system
./monitor.sh
```

## 📊 Monitoring

### Bot Status
```bash
# Check if bot is running
sudo systemctl status trading-bot

# View recent logs
journalctl -u trading-bot --since "1 hour ago"

# Monitor system resources
./monitor.sh
```

### Performance Metrics
- **Win Rate:** Percentage of profitable trades
- **Sharpe Ratio:** Risk-adjusted returns
- **Maximum Drawdown:** Largest peak-to-trough decline
- **Value at Risk (VaR):** Potential loss at 95% confidence
- **Total Return:** Overall portfolio performance

## 🛡️ Security

### API Key Security
- Store API keys in `.env` file (never commit to git)
- Use read-only keys when possible
- Enable IP whitelisting on exchanges
- Regularly rotate API keys

### VPS Security
- Keep system updated: `sudo apt update && sudo apt upgrade`
- Configure firewall: `sudo ufw enable`
- Use SSH keys instead of passwords
- Monitor system logs regularly

### Trading Safety
- Start with **small amounts** in simulation mode
- Set conservative **risk limits**
- Monitor **drawdown** closely
- Use **stop-losses** on all positions

## 🔧 Troubleshooting

### Common Issues

1. **Bot won't start:**
```bash
# Check logs
journalctl -u trading-bot -f

# Check Python environment
cd /home/user/trading-bot
source venv/bin/activate
python -c "import ccxt; print('CCXT OK')"
```

2. **No data collection:**
```bash
# Check exchange connections
python -c "
import ccxt
exchange = ccxt.binance()
print(exchange.fetch_ticker('BTC/USDT'))
"
```

3. **Dashboard not accessible:**
```bash
# Check if port is open
sudo ufw status
sudo ufw allow 8501

# Check if dashboard is running
ps aux | grep streamlit
```

4. **High memory usage:**
```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head

# Restart bot if needed
sudo systemctl restart trading-bot
```

## 📈 Performance Optimization

### VPS Optimization
```bash
# Increase file descriptor limits
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# Optimize system settings
echo "vm.swappiness=10" >> /etc/sysctl.conf
echo "vm.vfs_cache_pressure=50" >> /etc/sysctl.conf
```

### Bot Optimization
- **Reduce update intervals** for faster response
- **Limit historical data** to essential periods
- **Use feature selection** to reduce model complexity
- **Optimize database queries** with proper indexing

## 📞 Support

### Getting Help
1. Check the logs: `journalctl -u trading-bot -f`
2. Review configuration in `.env` file
3. Test individual components
4. Monitor system resources

### Useful Commands
```bash
# Restart bot
sudo systemctl restart trading-bot

# View full logs
journalctl -u trading-bot --no-pager

# Check disk space
df -h

# Check memory usage
free -h

# Monitor processes
htop
```

## ⚠️ Disclaimer

This trading bot is for educational and research purposes. Cryptocurrency trading involves significant risk of loss. Always:

- Start with small amounts
- Test thoroughly in simulation mode
- Monitor performance closely
- Set appropriate risk limits
- Never invest more than you can afford to lose

The developers are not responsible for any financial losses incurred through the use of this software.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

**Happy Trading! 🚀📈**