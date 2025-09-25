"""
Database Manager for Trading Bot
SQLite database operations for storing trading data, positions, and metrics
"""

import asyncio
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from loguru import logger
import json
from pathlib import Path

class Database:
    """Database manager for trading bot data"""
    
    def __init__(self):
        self.db_path = Path("data/trading_bot.db")
        self.connection = None
        
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
    async def initialize(self):
        """Initialize database and create tables"""
        logger.info("🗄️ Initializing Database...")
        
        try:
            # Create connection
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
            
            # Create tables
            await self._create_tables()
            
            logger.info("✅ Database initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise
            
    def _create_tables(self):
        """Create database tables"""
        cursor = self.connection.cursor()
        
        # Market data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                source TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timestamp, source)
            )
        ''')
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0,
                stop_loss REAL,
                take_profit REAL,
                status TEXT DEFAULT 'OPEN',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL NOT NULL,
                price REAL NOT NULL,
                timestamp DATETIME NOT NULL,
                confidence REAL,
                reasoning TEXT,
                pnl REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Portfolio history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                total_value REAL NOT NULL,
                available_capital REAL NOT NULL,
                total_exposure REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0,
                realized_pnl REAL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Risk metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                portfolio_value REAL NOT NULL,
                total_exposure REAL NOT NULL,
                max_drawdown REAL NOT NULL,
                var_95 REAL NOT NULL,
                sharpe_ratio REAL NOT NULL,
                volatility REAL NOT NULL,
                correlation_risk REAL NOT NULL,
                concentration_risk REAL NOT NULL,
                leverage_risk REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ML model performance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                accuracy REAL,
                loss REAL,
                precision REAL,
                recall REAL,
                f1_score REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Trading signals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trading_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence REAL NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                reasoning TEXT,
                timestamp DATETIME NOT NULL,
                executed BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Bot status table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                status TEXT NOT NULL,
                running BOOLEAN NOT NULL,
                positions_count INTEGER DEFAULT 0,
                portfolio_value REAL NOT NULL,
                last_signal_time DATETIME,
                error_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp ON market_data(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades(symbol, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_portfolio_history_timestamp ON portfolio_history(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_risk_metrics_timestamp ON risk_metrics(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol_timestamp ON trading_signals(symbol, timestamp)')
        
        self.connection.commit()
        
    async def save_market_data(self, market_data):
        """Save market data to database"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO market_data 
                (symbol, timestamp, open, high, low, close, volume, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                market_data.symbol,
                market_data.timestamp,
                market_data.open,
                market_data.high,
                market_data.low,
                market_data.close,
                market_data.volume,
                market_data.source
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving market data: {e}")
            
    async def save_historical_data(self, symbol: str, data: pd.DataFrame):
        """Save historical data to database"""
        try:
            cursor = self.connection.cursor()
            
            for _, row in data.iterrows():
                cursor.execute('''
                    INSERT OR REPLACE INTO market_data 
                    (symbol, timestamp, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    row['timestamp'],
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row['volume'],
                    row.get('source', 'historical')
                ))
                
            self.connection.commit()
            logger.info(f"💾 Saved {len(data)} historical records for {symbol}")
            
        except Exception as e:
            logger.error(f"Error saving historical data: {e}")
            
    async def get_historical_data(self, symbol: str, limit: Optional[int] = None) -> Optional[pd.DataFrame]:
        """Get historical data for a symbol"""
        try:
            cursor = self.connection.cursor()
            
            query = '''
                SELECT timestamp, open, high, low, close, volume, source
                FROM market_data 
                WHERE symbol = ?
                ORDER BY timestamp DESC
            '''
            
            if limit:
                query += f' LIMIT {limit}'
                
            cursor.execute(query, (symbol,))
            rows = cursor.fetchall()
            
            if rows:
                data = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'source'])
                data['timestamp'] = pd.to_datetime(data['timestamp'])
                return data.sort_values('timestamp')
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            return None
            
    async def save_position(self, position):
        """Save position to database"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO positions 
                (symbol, side, size, entry_price, current_price, unrealized_pnl, stop_loss, take_profit, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                position.symbol,
                position.side,
                position.size,
                position.entry_price,
                position.current_price,
                position.unrealized_pnl,
                position.stop_loss,
                position.take_profit,
                'OPEN'
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving position: {e}")
            
    async def get_active_positions(self) -> List[Dict]:
        """Get all active positions"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                SELECT * FROM positions 
                WHERE status = 'OPEN'
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting active positions: {e}")
            return []
            
    async def update_position(self, symbol: str, **updates):
        """Update position data"""
        try:
            cursor = self.connection.cursor()
            
            set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
            updates['updated_at'] = datetime.now()
            updates['symbol'] = symbol
            
            cursor.execute(f'''
                UPDATE positions 
                SET {set_clause}, updated_at = ?
                WHERE symbol = ?
            ''', list(updates.values()) + [symbol])
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error updating position: {e}")
            
    async def close_position(self, symbol: str, final_pnl: float):
        """Close a position and update P&L"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                UPDATE positions 
                SET status = 'CLOSED', unrealized_pnl = ?, updated_at = ?
                WHERE symbol = ? AND status = 'OPEN'
            ''', (final_pnl, datetime.now(), symbol))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            
    async def save_trade(self, order: Dict, signal):
        """Save trade to database"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT INTO trades 
                (order_id, symbol, side, amount, price, timestamp, confidence, reasoning, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order.get('id', ''),
                signal.symbol,
                signal.action,
                signal.quantity,
                signal.price,
                signal.timestamp or datetime.now(),
                signal.confidence,
                signal.reasoning,
                0.0  # P&L calculated separately
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            
    async def update_trade_pnl(self, order_id: str, pnl: float):
        """Update trade P&L"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                UPDATE trades 
                SET pnl = ?
                WHERE order_id = ?
            ''', (pnl, order_id))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error updating trade P&L: {e}")
            
    async def get_trade_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get trade history"""
        try:
            cursor = self.connection.cursor()
            
            if symbol:
                cursor.execute('''
                    SELECT * FROM trades 
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (symbol, limit))
            else:
                cursor.execute('''
                    SELECT * FROM trades 
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
                
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting trade history: {e}")
            return []
            
    async def save_portfolio_value(self, portfolio_value: float, available_capital: float, total_exposure: float):
        """Save portfolio value to history"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT INTO portfolio_history 
                (timestamp, total_value, available_capital, total_exposure)
                VALUES (?, ?, ?, ?)
            ''', (datetime.now(), portfolio_value, available_capital, total_exposure))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving portfolio value: {e}")
            
    async def get_portfolio_history(self, limit: int = 1000) -> Optional[pd.DataFrame]:
        """Get portfolio history"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                SELECT * FROM portfolio_history 
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            
            if rows:
                data = pd.DataFrame(rows, columns=['id', 'timestamp', 'total_value', 'available_capital', 'total_exposure', 'unrealized_pnl', 'realized_pnl', 'created_at'])
                data['timestamp'] = pd.to_datetime(data['timestamp'])
                return data.sort_values('timestamp')
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting portfolio history: {e}")
            return None
            
    async def save_risk_metrics(self, risk_metrics):
        """Save risk metrics to database"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT INTO risk_metrics 
                (timestamp, portfolio_value, total_exposure, max_drawdown, var_95, sharpe_ratio, volatility, correlation_risk, concentration_risk, leverage_risk)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                risk_metrics.portfolio_value,
                risk_metrics.total_exposure,
                risk_metrics.max_drawdown,
                risk_metrics.var_95,
                risk_metrics.sharpe_ratio,
                risk_metrics.volatility,
                risk_metrics.correlation_risk,
                risk_metrics.concentration_risk,
                risk_metrics.leverage_risk
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving risk metrics: {e}")
            
    async def get_risk_metrics_history(self, limit: int = 1000) -> Optional[pd.DataFrame]:
        """Get risk metrics history"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                SELECT * FROM risk_metrics 
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            
            if rows:
                columns = ['id', 'timestamp', 'portfolio_value', 'total_exposure', 'max_drawdown', 'var_95', 'sharpe_ratio', 'volatility', 'correlation_risk', 'concentration_risk', 'leverage_risk', 'created_at']
                data = pd.DataFrame(rows, columns=columns)
                data['timestamp'] = pd.to_datetime(data['timestamp'])
                return data.sort_values('timestamp')
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting risk metrics history: {e}")
            return None
            
    async def save_model_performance(self, model_name: str, performance_metrics: Dict):
        """Save ML model performance metrics"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT INTO model_performance 
                (model_name, timestamp, accuracy, loss, precision, recall, f1_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                model_name,
                datetime.now(),
                performance_metrics.get('accuracy', 0),
                performance_metrics.get('loss', 0),
                performance_metrics.get('precision', 0),
                performance_metrics.get('recall', 0),
                performance_metrics.get('f1_score', 0)
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving model performance: {e}")
            
    async def save_trading_signal(self, signal):
        """Save trading signal to database"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT INTO trading_signals 
                (symbol, action, confidence, price, quantity, stop_loss, take_profit, reasoning, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal.symbol,
                signal.action,
                signal.confidence,
                signal.price,
                signal.quantity,
                signal.stop_loss,
                signal.take_profit,
                signal.reasoning,
                signal.timestamp or datetime.now()
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving trading signal: {e}")
            
    async def get_recent_signals(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get recent trading signals"""
        try:
            cursor = self.connection.cursor()
            
            if symbol:
                cursor.execute('''
                    SELECT * FROM trading_signals 
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (symbol, limit))
            else:
                cursor.execute('''
                    SELECT * FROM trading_signals 
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
                
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting recent signals: {e}")
            return []
            
    async def save_bot_status(self, status_data: Dict):
        """Save bot status to database"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                INSERT INTO bot_status 
                (timestamp, status, running, positions_count, portfolio_value, last_signal_time, error_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                status_data.get('status', 'UNKNOWN'),
                status_data.get('running', False),
                status_data.get('positions_count', 0),
                status_data.get('portfolio_value', 0),
                status_data.get('last_signal_time'),
                status_data.get('error_count', 0)
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error saving bot status: {e}")
            
    async def get_bot_status_history(self, limit: int = 100) -> List[Dict]:
        """Get bot status history"""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute('''
                SELECT * FROM bot_status 
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting bot status history: {e}")
            return []
            
    async def get_performance_summary(self) -> Dict:
        """Get trading performance summary"""
        try:
            cursor = self.connection.cursor()
            
            # Get total trades
            cursor.execute('SELECT COUNT(*) as total_trades FROM trades')
            total_trades = cursor.fetchone()['total_trades']
            
            # Get winning trades
            cursor.execute('SELECT COUNT(*) as winning_trades FROM trades WHERE pnl > 0')
            winning_trades = cursor.fetchone()['winning_trades']
            
            # Get total P&L
            cursor.execute('SELECT SUM(pnl) as total_pnl FROM trades')
            total_pnl = cursor.fetchone()['total_pnl'] or 0
            
            # Get win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Get current portfolio value
            cursor.execute('''
                SELECT total_value FROM portfolio_history 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''')
            portfolio_row = cursor.fetchone()
            current_value = portfolio_row['total_value'] if portfolio_row else 0
            
            # Get initial capital
            initial_capital = float(os.getenv('INITIAL_CAPITAL', 10000))
            
            # Calculate returns
            total_return = ((current_value - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
            
            return {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'current_portfolio_value': current_value,
                'initial_capital': initial_capital,
                'total_return_pct': total_return
            }
            
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {}
            
    async def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to keep database size manageable"""
        try:
            cursor = self.connection.cursor()
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            # Clean up old market data (keep only recent data)
            cursor.execute('DELETE FROM market_data WHERE timestamp < ?', (cutoff_date,))
            deleted_market = cursor.rowcount
            
            # Clean up old bot status records
            cursor.execute('DELETE FROM bot_status WHERE timestamp < ?', (cutoff_date,))
            deleted_status = cursor.rowcount
            
            self.connection.commit()
            
            logger.info(f"🧹 Cleaned up {deleted_market} market data records and {deleted_status} status records")
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            
    async def is_healthy(self) -> bool:
        """Check if database is healthy"""
        try:
            cursor = self.connection.cursor()
            cursor.execute('SELECT 1')
            return True
        except Exception:
            return False
            
    async def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("🗄️ Database connection closed")