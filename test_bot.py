#!/usr/bin/env python3
"""
Test script for the unified trading bot
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unified_trading_bot import UnifiedTradingBot


async def test_bot():
    """Test the trading bot in paper mode"""
    print("🤖 Testing Unified Trading Bot...")
    
    # Set environment for paper trading
    os.environ["ENABLE_LIVE"] = "false"
    os.environ["ALLOW_LIVE"] = "false"
    os.environ["LIVE_CONFIRM"] = "NO"
    os.environ["LOG_LEVEL"] = "INFO"
    
    # Create bot instance
    bot = UnifiedTradingBot()
    
    print(f"📊 Bot Status: {bot.get_status()}")
    
    # Test component initialization
    print("🔧 Testing components...")
    
    # Test exchange manager
    try:
        exchanges = bot.exchange_manager.get_available_exchanges()
        print(f"✅ Exchange Manager: {len(exchanges)} exchanges available")
    except Exception as e:
        print(f"❌ Exchange Manager error: {e}")
    
    # Test risk manager
    try:
        risk_metrics = bot.risk_manager.get_risk_metrics()
        print(f"✅ Risk Manager: Portfolio value ${risk_metrics['portfolio_value']:.2f}")
    except Exception as e:
        print(f"❌ Risk Manager error: {e}")
    
    # Test order manager
    try:
        order_stats = bot.order_manager.get_statistics()
        print(f"✅ Order Manager: {order_stats['total_orders']} orders tracked")
    except Exception as e:
        print(f"❌ Order Manager error: {e}")
    
    # Test strategy engine
    try:
        await bot.initialize_strategies()
        signal_stats = bot.strategy_engine.get_signal_statistics()
        print(f"✅ Strategy Engine: {signal_stats['active_strategies']} strategies active")
    except Exception as e:
        print(f"❌ Strategy Engine error: {e}")
    
    # Test paper trading
    print("📈 Testing paper trading...")
    
    try:
        # Create a test order
        from core.order_manager import OrderSide, OrderType
        
        test_order = await bot.order_manager.create_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.001,
            exchange="binance",
            live=False
        )
        
        print(f"✅ Test order created: {test_order.id} - {test_order.status.value}")
        
        # Test signal generation
        from core.strategy_engine import MarketData
        import pandas as pd
        import numpy as np
        
        # Create mock market data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
        prices = 50000 + np.cumsum(np.random.randn(100) * 100)
        
        mock_ohlcv = pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices,
            'volume': np.random.rand(100) * 1000
        })
        
        market_data = MarketData(
            symbol="BTC/USDT",
            timeframe="1h",
            ohlcv=mock_ohlcv,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Test RSI strategy
        rsi_strategy = bot.strategy_engine.strategies.get("RSI")
        if rsi_strategy:
            signal = await rsi_strategy.generate_signal(market_data)
            if signal:
                print(f"✅ RSI Signal: {signal.signal_type.value} - confidence {signal.confidence:.2f}")
            else:
                print("ℹ️  RSI Strategy: No signal generated")
        
        print("✅ Paper trading test completed")
        
    except Exception as e:
        print(f"❌ Paper trading test error: {e}")
    
    # Test risk management
    print("🛡️  Testing risk management...")
    
    try:
        from core.risk_manager import RiskCheck, OrderSide, OrderType
        
        risk_check = await bot.risk_manager.check_order_risk(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.1,
            price=50000,
            order_type=OrderType.MARKET
        )
        
        print(f"✅ Risk Check: {'PASSED' if risk_check.allowed else 'FAILED'} - {risk_check.reason}")
        
        if risk_check.warnings:
            print(f"⚠️  Warnings: {', '.join(risk_check.warnings)}")
        
    except Exception as e:
        print(f"❌ Risk management test error: {e}")
    
    print("\n🎉 Bot testing completed!")
    print(f"📊 Final Status: {bot.get_status()}")


if __name__ == "__main__":
    asyncio.run(test_bot())