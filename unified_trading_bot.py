"""
Unified Trading Bot
Main trading bot that integrates all components
"""

from __future__ import annotations
import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from core.order_manager import OrderManager, OrderSide, OrderType
from core.risk_manager import RiskManager
from core.strategy_engine import StrategyEngine, RSIStrategy, MACDStrategy, BollingerBandsStrategy
from exchange_manager import ExchangeManager


class UnifiedTradingBot:
    """Main trading bot that coordinates all components"""
    
    def __init__(self, config_file: str = "api_config.json"):
        # Load environment variables
        load_dotenv()
        
        # Initialize logging
        self.setup_logging()
        self.logger = logging.getLogger("unified_trading_bot")
        
        # Load configuration
        self.config = self.load_config()
        
        # Initialize components
        self.exchange_manager = ExchangeManager(config_file)
        self.risk_manager = RiskManager(self.config.get("risk", {}))
        self.order_manager = OrderManager(self.exchange_manager, self.risk_manager)
        self.strategy_engine = StrategyEngine(
            self.exchange_manager, 
            self.order_manager, 
            self.risk_manager
        )
        
        # Bot state
        self.running = False
        self.symbols = self.config.get("symbols", ["BTC/USDT", "ETH/USDT"])
        self.timeframes = self.config.get("timeframes", ["1m", "5m", "15m"])
        self.live_trading = self.config.get("live_trading", False)
        
        # Performance tracking
        self.start_time = None
        self.trades_executed = 0
        self.total_pnl = 0.0
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Setup callbacks
        self.setup_callbacks()
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("trading_bot.log")
            ]
        )
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from environment and files"""
        config = {
            "symbols": os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT").split(","),
            "timeframes": os.getenv("TIMEFRAMES", "1m,5m,15m").split(","),
            "live_trading": os.getenv("ENABLE_LIVE", "false").lower() == "true",
            "risk": {
                "max_position_size": float(os.getenv("MAX_POSITION_SIZE", "0.1")),
                "max_total_exposure": float(os.getenv("MAX_TOTAL_EXPOSURE", "0.8")),
                "max_drawdown": float(os.getenv("MAX_DRAWDOWN", "0.15")),
                "max_var": float(os.getenv("MAX_VAR", "0.05")),
                "max_correlation": float(os.getenv("MAX_CORRELATION", "0.7")),
                "max_concentration": float(os.getenv("MAX_CONCENTRATION", "0.3")),
                "initial_capital": float(os.getenv("INITIAL_CAPITAL", "10000"))
            },
            "strategies": {
                "rsi": {
                    "enabled": True,
                    "oversold_level": 30,
                    "overbought_level": 70,
                    "rsi_period": 14,
                    "min_confidence": 0.6
                },
                "macd": {
                    "enabled": True,
                    "fast_period": 12,
                    "slow_period": 26,
                    "signal_period": 9,
                    "min_confidence": 0.6
                },
                "bollinger_bands": {
                    "enabled": True,
                    "bb_period": 20,
                    "bb_std": 2,
                    "min_confidence": 0.6
                }
            }
        }
        
        return config
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down gracefully...")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def setup_callbacks(self):
        """Setup component callbacks"""
        # Order manager callbacks
        self.order_manager.on_order_update = self.on_order_update
        self.order_manager.on_fill = self.on_fill
        
        # Strategy engine callbacks
        self.strategy_engine.on_signal = self.on_signal
    
    async def on_order_update(self, order):
        """Handle order updates"""
        self.logger.info(f"Order update: {order.id} - {order.status.value}")
        
        if order.status.value == "filled":
            self.trades_executed += 1
    
    async def on_fill(self, fill):
        """Handle trade fills"""
        self.logger.info(f"Fill: {fill.symbol} {fill.side.value} {fill.amount} @ {fill.price}")
        
        # Update risk manager
        pnl = fill.amount * fill.price if fill.side.value == "sell" else -fill.amount * fill.price
        self.total_pnl += pnl
        self.risk_manager.add_daily_pnl(pnl)
    
    async def on_signal(self, signal):
        """Handle trading signals"""
        self.logger.info(f"Signal: {signal.symbol} {signal.signal_type.value} "
                        f"confidence={signal.confidence:.2f} strength={signal.strength.value}")
        
        if not self.live_trading:
            self.logger.info("Live trading disabled, signal ignored")
            return
        
        # Convert signal to order
        await self.execute_signal(signal)
    
    async def execute_signal(self, signal):
        """Execute a trading signal"""
        try:
            # Determine order side
            if signal.signal_type.value == "buy":
                side = OrderSide.BUY
            elif signal.signal_type.value == "sell":
                side = OrderSide.SELL
            else:
                return
            
            # Calculate position size
            position_size = self.risk_manager.calculate_position_size(
                symbol=signal.symbol,
                side=side,
                confidence=signal.confidence,
                stop_loss_pct=0.02  # 2% stop loss
            )
            
            if position_size <= 0:
                self.logger.warning(f"Position size too small for {signal.symbol}")
                return
            
            # Create order
            order = await self.order_manager.create_order(
                symbol=signal.symbol,
                side=side,
                order_type=OrderType.MARKET,
                amount=position_size,
                exchange="binance",  # Default exchange
                live=self.live_trading
            )
            
            if order.status.value == "rejected":
                self.logger.warning(f"Order rejected: {order.metadata.get('rejection_reason', 'Unknown')}")
            
        except Exception as e:
            self.logger.error(f"Failed to execute signal: {e}")
    
    async def initialize_strategies(self):
        """Initialize trading strategies"""
        strategy_configs = self.config.get("strategies", {})
        
        # RSI Strategy
        if strategy_configs.get("rsi", {}).get("enabled", True):
            rsi_strategy = RSIStrategy(strategy_configs.get("rsi", {}))
            self.strategy_engine.add_strategy(rsi_strategy)
        
        # MACD Strategy
        if strategy_configs.get("macd", {}).get("enabled", True):
            macd_strategy = MACDStrategy(strategy_configs.get("macd", {}))
            self.strategy_engine.add_strategy(macd_strategy)
        
        # Bollinger Bands Strategy
        if strategy_configs.get("bollinger_bands", {}).get("enabled", True):
            bb_strategy = BollingerBandsStrategy(strategy_configs.get("bollinger_bands", {}))
            self.strategy_engine.add_strategy(bb_strategy)
        
        self.logger.info(f"Initialized {len(self.strategy_engine.strategies)} strategies")
    
    async def update_portfolio_value(self):
        """Update portfolio value from exchange balances"""
        try:
            # This would fetch actual balance from exchange
            # For now, use initial capital
            portfolio_value = self.config["risk"]["initial_capital"]
            self.risk_manager.update_portfolio_value(portfolio_value)
        except Exception as e:
            self.logger.error(f"Failed to update portfolio value: {e}")
    
    async def run_trading_loop(self):
        """Main trading loop"""
        self.logger.info("Starting trading loop...")
        
        while self.running:
            try:
                # Update portfolio value
                await self.update_portfolio_value()
                
                # Run strategies for all symbols
                await self.strategy_engine.run_all_symbols()
                
                # Log statistics
                await self.log_statistics()
                
                # Wait before next iteration
                await asyncio.sleep(60)  # 1 minute intervals
                
            except Exception as e:
                self.logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def log_statistics(self):
        """Log current statistics"""
        order_stats = self.order_manager.get_statistics()
        risk_metrics = self.risk_manager.get_risk_metrics()
        signal_stats = self.strategy_engine.get_signal_statistics()
        
        self.logger.info(f"Orders: {order_stats['total_orders']} total, "
                        f"{order_stats['filled_orders']} filled, "
                        f"{order_stats['open_orders']} open")
        
        self.logger.info(f"Portfolio: ${risk_metrics['portfolio_value']:.2f}, "
                        f"Drawdown: {risk_metrics['current_drawdown']:.2%}, "
                        f"Exposure: {risk_metrics['exposure_ratio']:.2%}")
        
        self.logger.info(f"Signals: {signal_stats['total_signals']} total, "
                        f"Avg confidence: {signal_stats.get('avg_confidence', 0):.2f}")
    
    async def start(self):
        """Start the trading bot"""
        if self.running:
            self.logger.warning("Bot is already running")
            return
        
        self.logger.info("Starting Unified Trading Bot...")
        self.running = True
        self.start_time = datetime.now(timezone.utc)
        
        try:
            # Initialize strategies
            await self.initialize_strategies()
            
            # Set symbols for strategy engine
            self.strategy_engine.set_symbols(self.symbols)
            
            # Start strategy engine
            self.strategy_engine.start()
            
            # Run main trading loop
            await self.run_trading_loop()
            
        except Exception as e:
            self.logger.error(f"Error starting bot: {e}")
            await self.stop()
    
    async def stop(self):
        """Stop the trading bot"""
        if not self.running:
            return
        
        self.logger.info("Stopping Unified Trading Bot...")
        self.running = False
        
        try:
            # Stop strategy engine
            self.strategy_engine.stop()
            
            # Cancel all open orders
            await self.order_manager.close_all_orders()
            
            # Close exchange connections
            await self.exchange_manager.close_all_connections()
            
            # Log final statistics
            await self.log_statistics()
            
            self.logger.info("Bot stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        uptime = None
        if self.start_time:
            uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        return {
            "running": self.running,
            "live_trading": self.live_trading,
            "uptime_seconds": uptime,
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "trades_executed": self.trades_executed,
            "total_pnl": self.total_pnl,
            "order_stats": self.order_manager.get_statistics(),
            "risk_metrics": self.risk_manager.get_risk_metrics(),
            "signal_stats": self.strategy_engine.get_signal_statistics()
        }


async def main():
    """Main entry point"""
    bot = UnifiedTradingBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())