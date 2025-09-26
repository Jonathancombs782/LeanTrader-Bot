#!/bin/bash

# Ultra Advanced Trading System Startup Script
# This script starts the complete trading system with all advanced engines

echo "🚀 Starting Ultra Advanced Trading System..."
echo "💰 Target: Grow $48 → $3000-5000 by November"
echo ""

# Set environment variables
export PYTHONPATH="/workspace:$PYTHONPATH"
export ULTRA_MODE="paper"  # Change to "live" for real trading
export ULTRA_SYMBOLS="BTC/USDT,ETH/USDT,BNB/USDT"

# Create logs directory
mkdir -p logs

# Start the system
echo "Starting Ultra Launcher Advanced..."
python3 ultra_launcher_advanced.py \
    --mode paper \
    --symbols "BTC/USDT,ETH/USDT,BNB/USDT" \
    --log_file "logs/ultra_trading.log"

echo "Trading system stopped."