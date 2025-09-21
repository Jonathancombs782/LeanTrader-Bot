"""
Main Trading Bot Class
Handles trading logic, order execution, and portfolio management
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from loguru import logger
import ccxt
from dataclasses import dataclass

@dataclass
class TradeSignal:
    """Trade signal data structure"""
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float
    price: float
    quantity: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasoning: str = ""
    timestamp: datetime = None

@dataclass
class Position:
    """Position data structure"""
    symbol: str
    side: str  # 'LONG', 'SHORT'
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: datetime = None

class TradingBot:
    """Professional Trading Bot with ML-powered decision making"""
    
    def __init__(self, data_collector, ml_engine, risk_manager, notification_manager, database):
        self.data_collector = data_collector
        self.ml_engine = ml_engine
        self.risk_manager = risk_manager
        self.notification_manager = notification_manager
        self.database = database
        
        # Trading state
        self.positions: Dict[str, Position] = {}
        self.pending_orders: Dict[str, dict] = {}
        self.trade_history: List[dict] = []
        self.portfolio_value = 0
        self.available_capital = 0
        
        # Exchange connections
        self.exchanges = {}
        self.active_exchange = None
        
        # Configuration
        self.config = {
            'max_positions': int(os.getenv('MAX_POSITIONS', 10)),
            'position_size_pct': float(os.getenv('POSITION_SIZE_PCT', 0.1)),
            'stop_loss_pct': float(os.getenv('STOP_LOSS_PCT', 0.05)),
            'take_profit_pct': float(os.getenv('TAKE_PROFIT_PCT', 0.1)),
            'min_confidence': float(os.getenv('MIN_CONFIDENCE', 0.7)),
            'trading_enabled': os.getenv('TRADING_ENABLED', 'true').lower() == 'true'
        }
        
        self.running = False
        
    async def initialize(self):
        """Initialize the trading bot"""
        logger.info("🤖 Initializing Trading Bot...")
        
        try:
            # Initialize exchanges
            await self._initialize_exchanges()
            
            # Load existing positions
            await self._load_positions()
            
            # Load portfolio data
            await self._load_portfolio()
            
            logger.info("✅ Trading Bot initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize trading bot: {e}")
            raise
            
    async def _initialize_exchanges(self):
        """Initialize exchange connections"""
        logger.info("🔌 Initializing exchange connections...")
        
        # Binance
        if os.getenv('BINANCE_API_KEY') and os.getenv('BINANCE_SECRET_KEY'):
            self.exchanges['binance'] = ccxt.binance({
                'apiKey': os.getenv('BINANCE_API_KEY'),
                'secret': os.getenv('BINANCE_SECRET_KEY'),
                'sandbox': os.getenv('BINANCE_SANDBOX', 'false').lower() == 'true',
                'enableRateLimit': True,
            })
            
        # Coinbase Pro
        if os.getenv('COINBASE_API_KEY') and os.getenv('COINBASE_SECRET_KEY'):
            self.exchanges['coinbase'] = ccxt.coinbasepro({
                'apiKey': os.getenv('COINBASE_API_KEY'),
                'secret': os.getenv('COINBASE_SECRET_KEY'),
                'passphrase': os.getenv('COINBASE_PASSPHRASE', ''),
                'sandbox': os.getenv('COINBASE_SANDBOX', 'false').lower() == 'true',
                'enableRateLimit': True,
            })
            
        # Set active exchange (prefer Binance)
        if 'binance' in self.exchanges:
            self.active_exchange = self.exchanges['binance']
        elif 'coinbase' in self.exchanges:
            self.active_exchange = self.exchanges['coinbase']
        else:
            logger.warning("⚠️ No exchange configured - running in simulation mode")
            
    async def _load_positions(self):
        """Load existing positions from database"""
        positions_data = await self.database.get_active_positions()
        for pos_data in positions_data:
            position = Position(**pos_data)
            self.positions[position.symbol] = position
            
        logger.info(f"📊 Loaded {len(self.positions)} active positions")
        
    async def _load_portfolio(self):
        """Load portfolio information"""
        try:
            if self.active_exchange:
                balance = await self.active_exchange.fetch_balance()
                self.portfolio_value = balance['total']['USDT'] if 'USDT' in balance['total'] else 0
                self.available_capital = balance['free']['USDT'] if 'USDT' in balance['free'] else 0
            else:
                # Simulation mode
                self.portfolio_value = float(os.getenv('INITIAL_CAPITAL', 10000))
                self.available_capital = self.portfolio_value
                
            logger.info(f"💰 Portfolio value: ${self.portfolio_value:.2f}")
            logger.info(f"💵 Available capital: ${self.available_capital:.2f}")
            
        except Exception as e:
            logger.error(f"Failed to load portfolio: {e}")
            self.portfolio_value = float(os.getenv('INITIAL_CAPITAL', 10000))
            self.available_capital = self.portfolio_value
            
    async def start(self):
        """Start the trading bot"""
        logger.info("🎯 Starting Trading Bot...")
        self.running = True
        
        # Start trading loop
        await self._trading_loop()
        
    async def stop(self):
        """Stop the trading bot"""
        logger.info("🛑 Stopping Trading Bot...")
        self.running = False
        
        # Close all positions if configured
        if os.getenv('CLOSE_ON_STOP', 'false').lower() == 'true':
            await self._close_all_positions()
            
    async def _trading_loop(self):
        """Main trading loop"""
        while self.running:
            try:
                # Get latest market data
                market_data = await self.data_collector.get_latest_data()
                
                # Generate trading signals
                signals = await self.ml_engine.generate_signals(market_data)
                
                # Process signals
                for signal in signals:
                    await self._process_signal(signal)
                    
                # Update positions
                await self._update_positions()
                
                # Check for exit conditions
                await self._check_exit_conditions()
                
                # Update portfolio
                await self._update_portfolio()
                
                # Risk management checks
                await self.risk_manager.check_risk_limits(self.positions, self.portfolio_value)
                
                # Wait before next iteration
                await asyncio.sleep(5)  # 5-second trading loop
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)
                
    async def _process_signal(self, signal: TradeSignal):
        """Process a trading signal"""
        try:
            logger.info(f"📈 Processing signal: {signal.symbol} {signal.action} (confidence: {signal.confidence:.2f})")
            
            # Check if signal meets minimum confidence
            if signal.confidence < self.config['min_confidence']:
                logger.info(f"⚠️ Signal confidence too low: {signal.confidence:.2f} < {self.config['min_confidence']}")
                return
                
            # Risk management check
            if not await self.risk_manager.can_open_position(signal.symbol, signal.quantity * signal.price):
                logger.warning(f"🚫 Risk management blocked position for {signal.symbol}")
                return
                
            # Execute trade
            if signal.action == 'BUY':
                await self._execute_buy(signal)
            elif signal.action == 'SELL':
                await self._execute_sell(signal)
                
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            
    async def _execute_buy(self, signal: TradeSignal):
        """Execute a buy order"""
        try:
            # Calculate position size
            position_value = self.available_capital * self.config['position_size_pct']
            quantity = position_value / signal.price
            
            # Check if we already have a position
            if signal.symbol in self.positions:
                logger.info(f"⚠️ Already have position in {signal.symbol}, skipping")
                return
                
            # Check max positions limit
            if len(self.positions) >= self.config['max_positions']:
                logger.warning(f"🚫 Maximum positions limit reached ({self.config['max_positions']})")
                return
                
            # Execute order
            if self.config['trading_enabled'] and self.active_exchange:
                order = await self.active_exchange.create_market_buy_order(
                    signal.symbol, quantity
                )
                logger.info(f"✅ Buy order executed: {order}")
            else:
                # Simulation mode
                order = {
                    'id': f"sim_{datetime.now().timestamp()}",
                    'symbol': signal.symbol,
                    'side': 'buy',
                    'amount': quantity,
                    'price': signal.price,
                    'timestamp': datetime.now()
                }
                logger.info(f"🎮 Simulated buy order: {order}")
                
            # Create position
            position = Position(
                symbol=signal.symbol,
                side='LONG',
                size=quantity,
                entry_price=signal.price,
                current_price=signal.price,
                unrealized_pnl=0,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                timestamp=datetime.now()
            )
            
            self.positions[signal.symbol] = position
            
            # Save to database
            await self.database.save_position(position)
            await self.database.save_trade(order, signal)
            
            # Send notification
            await self.notification_manager.send_notification(
                "📈 New Position Opened",
                f"Bought {quantity:.4f} {signal.symbol} at ${signal.price:.2f}\n"
                f"Confidence: {signal.confidence:.2f}\n"
                f"Reasoning: {signal.reasoning}"
            )
            
        except Exception as e:
            logger.error(f"Error executing buy order: {e}")
            
    async def _execute_sell(self, signal: TradeSignal):
        """Execute a sell order"""
        try:
            # Check if we have a position to sell
            if signal.symbol not in self.positions:
                logger.info(f"⚠️ No position to sell in {signal.symbol}")
                return
                
            position = self.positions[signal.symbol]
            
            # Execute order
            if self.config['trading_enabled'] and self.active_exchange:
                order = await self.active_exchange.create_market_sell_order(
                    signal.symbol, position.size
                )
                logger.info(f"✅ Sell order executed: {order}")
            else:
                # Simulation mode
                order = {
                    'id': f"sim_{datetime.now().timestamp()}",
                    'symbol': signal.symbol,
                    'side': 'sell',
                    'amount': position.size,
                    'price': signal.price,
                    'timestamp': datetime.now()
                }
                logger.info(f"🎮 Simulated sell order: {order}")
                
            # Calculate P&L
            pnl = (signal.price - position.entry_price) * position.size
            pnl_pct = (signal.price - position.entry_price) / position.entry_price * 100
            
            # Remove position
            del self.positions[signal.symbol]
            
            # Save to database
            await self.database.save_trade(order, signal)
            await self.database.update_position_pnl(signal.symbol, pnl)
            
            # Send notification
            await self.notification_manager.send_notification(
                "📉 Position Closed",
                f"Sold {position.size:.4f} {signal.symbol} at ${signal.price:.2f}\n"
                f"P&L: ${pnl:.2f} ({pnl_pct:.2f}%)\n"
                f"Reasoning: {signal.reasoning}"
            )
            
        except Exception as e:
            logger.error(f"Error executing sell order: {e}")
            
    async def _update_positions(self):
        """Update current prices and P&L for all positions"""
        for symbol, position in self.positions.items():
            try:
                # Get current price
                current_price = await self.data_collector.get_current_price(symbol)
                if current_price:
                    position.current_price = current_price
                    position.unrealized_pnl = (current_price - position.entry_price) * position.size
                    
            except Exception as e:
                logger.error(f"Error updating position {symbol}: {e}")
                
    async def _check_exit_conditions(self):
        """Check for stop loss and take profit conditions"""
        for symbol, position in self.positions.items():
            try:
                current_price = position.current_price
                entry_price = position.entry_price
                
                # Check stop loss
                if position.stop_loss and current_price <= position.stop_loss:
                    logger.info(f"🛑 Stop loss triggered for {symbol}")
                    signal = TradeSignal(
                        symbol=symbol,
                        action='SELL',
                        confidence=1.0,
                        price=current_price,
                        quantity=position.size,
                        reasoning="Stop loss triggered"
                    )
                    await self._execute_sell(signal)
                    
                # Check take profit
                elif position.take_profit and current_price >= position.take_profit:
                    logger.info(f"🎯 Take profit triggered for {symbol}")
                    signal = TradeSignal(
                        symbol=symbol,
                        action='SELL',
                        confidence=1.0,
                        price=current_price,
                        quantity=position.size,
                        reasoning="Take profit triggered"
                    )
                    await self._execute_sell(signal)
                    
            except Exception as e:
                logger.error(f"Error checking exit conditions for {symbol}: {e}")
                
    async def _update_portfolio(self):
        """Update portfolio value and available capital"""
        try:
            total_value = self.available_capital
            
            for position in self.positions.values():
                total_value += position.size * position.current_price
                
            self.portfolio_value = total_value
            
            # Update database
            await self.database.update_portfolio_value(self.portfolio_value)
            
        except Exception as e:
            logger.error(f"Error updating portfolio: {e}")
            
    async def _close_all_positions(self):
        """Close all open positions"""
        logger.info("🔄 Closing all positions...")
        
        for symbol in list(self.positions.keys()):
            try:
                position = self.positions[symbol]
                signal = TradeSignal(
                    symbol=symbol,
                    action='SELL',
                    confidence=1.0,
                    price=position.current_price,
                    quantity=position.size,
                    reasoning="Bot shutdown - closing position"
                )
                await self._execute_sell(signal)
                
            except Exception as e:
                logger.error(f"Error closing position {symbol}: {e}")
                
    async def get_status(self) -> dict:
        """Get current bot status"""
        return {
            'running': self.running,
            'positions_count': len(self.positions),
            'portfolio_value': self.portfolio_value,
            'available_capital': self.available_capital,
            'positions': [
                {
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'size': pos.size,
                    'entry_price': pos.entry_price,
                    'current_price': pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'timestamp': pos.timestamp.isoformat() if pos.timestamp else None
                }
                for pos in self.positions.values()
            ],
            'config': self.config
        }