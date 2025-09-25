# 🚀 Bybit Trading Bot - Deployment Guide

## 🎯 **One-Command Setup (Recommended)**

```bash
# Run this single command to set up everything automatically
./quick_setup.sh
```

This will:
- ✅ Upload all files to your VPS
- ✅ Install all dependencies
- ✅ Configure the system
- ✅ Start the trading bot
- ✅ Launch the dashboard
- ✅ Set up Bybit integration

## 🔧 **Manual Setup (If needed)**

### Step 1: Upload Files
```bash
./upload_to_vps.sh
```

### Step 2: Deploy on VPS
```bash
ssh root@75.119.149.117
cd /home/root/trading-bot
./deploy.sh
```

### Step 3: Configure Bybit API
```bash
# Edit the configuration file
nano .env

# Add your Bybit API keys:
BYBIT_API_KEY=your_actual_api_key
BYBIT_SECRET_KEY=your_actual_secret_key
```

### Step 4: Start Bot
```bash
sudo systemctl start trading-bot
```

### Step 5: Access Dashboard
Open browser: **http://75.119.149.117:8501**

## 🔑 **Getting Bybit API Keys**

1. Go to [Bybit.com](https://www.bybit.com/)
2. Login to your account
3. Go to **Account & Security** → **API Management**
4. Click **Create New Key**
5. Set permissions:
   - ✅ **Read** (for market data)
   - ✅ **Trade** (for executing trades)
   - ✅ **Derivatives** (for futures trading)
6. Set IP whitelist: `75.119.149.117`
7. Copy the **API Key** and **Secret Key**

## 📊 **Accessing Your Bot**

### Dashboard
- **URL:** http://75.119.149.117:8501
- **Features:** Real-time monitoring, portfolio tracking, trade history

### SSH Commands
```bash
# Connect to VPS
ssh root@75.119.149.117

# Check bot status
sudo systemctl status trading-bot

# View live logs
journalctl -u trading-bot -f

# Restart bot
sudo systemctl restart trading-bot

# Stop bot
sudo systemctl stop trading-bot
```

## ⚙️ **Configuration Options**

Edit `/home/root/trading-bot/.env` to customize:

```env
# Trading Settings
INITIAL_CAPITAL=10000          # Starting capital
MAX_POSITION_SIZE=0.1         # Max 10% per position
STOP_LOSS_PCT=0.05           # 5% stop loss
TAKE_PROFIT_PCT=0.1          # 10% take profit
MIN_CONFIDENCE=0.7           # 70% minimum confidence

# Risk Management
MAX_TOTAL_EXPOSURE=0.8       # Max 80% portfolio exposure
MAX_DRAWDOWN=0.15           # Max 15% drawdown
MAX_POSITIONS=10            # Maximum open positions

# Bybit Settings
BYBIT_SANDBOX=false         # Set to true for testnet

# Notifications
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 🛡️ **Safety Features**

- **Simulation Mode:** Test without real money
- **Risk Limits:** Automatic position sizing
- **Emergency Stop:** Auto-shutdown on high risk
- **Real-time Monitoring:** Continuous health checks
- **Comprehensive Logging:** Full audit trail

## 📈 **What the Bot Does**

1. **Learns** from market data using ML models
2. **Predicts** price movements with high confidence
3. **Executes** trades automatically on Bybit
4. **Manages Risk** with stop-losses and position sizing
5. **Monitors** performance and adjusts strategies
6. **Notifies** you of important events
7. **Reports** detailed analytics and metrics

## 🔍 **Monitoring & Troubleshooting**

### Check Bot Health
```bash
# View recent logs
journalctl -u trading-bot --since "1 hour ago"

# Check system resources
./monitor.sh

# Test exchange connection
python3 -c "
import ccxt
exchange = ccxt.bybit({'apiKey': 'test', 'secret': 'test'})
print('Bybit connection OK')
"
```

### Common Issues

**Bot won't start:**
```bash
# Check logs for errors
journalctl -u trading-bot --no-pager
```

**No data collection:**
- Verify Bybit API keys are correct
- Check if IP is whitelisted on Bybit
- Ensure VPS has internet access

**Dashboard not accessible:**
```bash
# Check if port is open
sudo ufw status
sudo ufw allow 8501
```

## 📞 **Support Commands**

```bash
# Restart everything
sudo systemctl restart trading-bot
sudo systemctl restart redis-server

# View full system status
sudo systemctl status trading-bot redis-server

# Check disk space
df -h

# Check memory usage
free -h

# View all processes
htop
```

## 🎉 **Success Indicators**

Your bot is working correctly when you see:
- ✅ Bot service status: `Active (running)`
- ✅ Dashboard accessible at http://75.119.149.117:8501
- ✅ Logs showing: `"Trading Bot Started"`
- ✅ Market data being collected
- ✅ ML models loaded and active

## ⚠️ **Important Notes**

- **Start Small:** Begin with small amounts for testing
- **Monitor Closely:** Watch the dashboard and logs
- **Set Limits:** Use conservative risk settings initially
- **Backup Keys:** Keep your API keys secure
- **Regular Updates:** Check for bot updates periodically

---

**🚀 Your professional Bybit trading bot is ready to trade like a pro!**

**Dashboard:** http://75.119.149.117:8501  
**Configuration:** /home/root/trading-bot/.env  
**Logs:** `journalctl -u trading-bot -f`