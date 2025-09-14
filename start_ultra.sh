#!/bin/bash

# Ultra Trading System - Quick Start Script
# The easiest way to launch the most brilliant trader ever created

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           ULTRA TRADING SYSTEM - QUICK START                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | grep -Po '(?<=Python )\d+\.\d+')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then 
    echo "❌ Error: Python 3.8+ is required (found $python_version)"
    exit 1
fi

echo "✅ Python version: $python_version"

# Install basic requirements if not present
echo "📦 Checking dependencies..."
pip3 install -q numpy pandas ccxt scikit-learn 2>/dev/null

# Create necessary directories
mkdir -p runtime/models
mkdir -p runtime/market_cache
mkdir -p runtime/training_data
mkdir -p data
mkdir -p reports
mkdir -p logs

echo "✅ Directories created"

# Default mode
MODE=${1:-paper}

# Check if first run
if [ ! -f "runtime/models/latest" ]; then
    echo "🎯 First run detected - training initial models..."
    python3 ultra_launcher.py --mode paper --train --symbols BTC/USDT ETH/USDT
else
    echo "🚀 Starting Ultra Trading System in $MODE mode..."
    python3 ultra_launcher.py --mode $MODE
fi

echo ""
echo "✅ Ultra Trading System is running!"
echo ""
echo "Commands:"
echo "  • Press Ctrl+C to stop"
echo "  • Check reports/ folder for results"
echo "  • Monitor runtime/models/ for trained models"
echo ""