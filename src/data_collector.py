"""
Data Collector for Trading Bot
Real-time and historical market data collection from multiple sources
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from loguru import logger
import ccxt
import yfinance as yf
import websocket
import json
import sqlite3
from dataclasses import dataclass

@dataclass
class MarketData:
    """Market data structure"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str

class DataCollector:
    """Advanced data collector for multiple exchanges and data sources"""
    
    def __init__(self, database):
        self.database = database
        
        # Exchange connections
        self.exchanges = {}
        self.websocket_connections = {}
        
        # Data storage
        self.realtime_data = {}
        self.historical_data = {}
        
        # Configuration
        self.config = {
            'symbols': ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT'],
            'timeframes': ['1m', '5m', '15m', '1h', '4h', '1d'],
            'update_interval': 5,  # seconds
            'historical_days': 365,
            'max_retries': 3,
            'retry_delay': 5
        }
        
        # State
        self.running = False
        self.last_update = {}
        
    async def initialize(self):
        """Initialize the data collector"""
        logger.info("📊 Initializing Data Collector...")
        
        try:
            # Initialize exchanges
            await self._initialize_exchanges()
            
            # Load historical data
            await self._load_historical_data()
            
            # Initialize real-time data storage
            for symbol in self.config['symbols']:
                self.realtime_data[symbol] = pd.DataFrame()
                self.last_update[symbol] = None
                
            logger.info("✅ Data Collector initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize data collector: {e}")
            raise
            
    async def start(self):
        """Start the data collector"""
        logger.info("🎯 Starting Data Collector...")
        self.running = True
        
        # Start data collection tasks
        await asyncio.gather(
            self._realtime_data_loop(),
            self._historical_data_update_loop(),
            self._websocket_data_loop()
        )
        
    async def stop(self):
        """Stop the data collector"""
        logger.info("🛑 Stopping Data Collector...")
        self.running = False
        
        # Close websocket connections
        for ws in self.websocket_connections.values():
            if ws:
                ws.close()
                
    async def _initialize_exchanges(self):
        """Initialize exchange connections"""
        logger.info("🔌 Initializing exchange connections...")
        
        # Bybit
        try:
            self.exchanges['bybit'] = ccxt.bybit({
                'apiKey': os.getenv('BYBIT_API_KEY', ''),
                'secret': os.getenv('BYBIT_SECRET_KEY', ''),
                'sandbox': os.getenv('BYBIT_SANDBOX', 'false').lower() == 'true',
                'enableRateLimit': True,
                'rateLimit': 1000
            })
            
            # Test connection
            await self.exchanges['bybit'].load_markets()
            logger.info("✅ Bybit connection established")
            
        except Exception as e:
            logger.warning(f"⚠️ Bybit connection failed: {e}")
            
        # Coinbase Pro
        try:
            self.exchanges['coinbase'] = ccxt.coinbasepro({
                'apiKey': os.getenv('COINBASE_API_KEY', ''),
                'secret': os.getenv('COINBASE_SECRET_KEY', ''),
                'passphrase': os.getenv('COINBASE_PASSPHRASE', ''),
                'sandbox': os.getenv('COINBASE_SANDBOX', 'false').lower() == 'true',
                'enableRateLimit': True,
                'rateLimit': 1000
            })
            
            # Test connection
            await self.exchanges['coinbase'].load_markets()
            logger.info("✅ Coinbase Pro connection established")
            
        except Exception as e:
            logger.warning(f"⚠️ Coinbase Pro connection failed: {e}")
            
        # Set active exchange (prefer Bybit)
        if 'bybit' in self.exchanges:
            self.active_exchange = self.exchanges['bybit']
        elif 'coinbase' in self.exchanges:
            self.active_exchange = self.exchanges['coinbase']
        else:
            logger.warning("⚠️ No exchange configured - running in simulation mode")
            
        # Yahoo Finance (fallback)
        logger.info("✅ Yahoo Finance available as fallback")
        
    async def _load_historical_data(self):
        """Load historical data for all symbols"""
        logger.info("📈 Loading historical data...")
        
        for symbol in self.config['symbols']:
            try:
                # Try to get from database first
                data = await self.database.get_historical_data(symbol, limit=1000)
                
                if data is None or len(data) == 0:
                    # Load from exchanges
                    data = await self._fetch_historical_data(symbol)
                    
                    if data is not None and len(data) > 0:
                        # Save to database
                        await self.database.save_historical_data(symbol, data)
                        
                if data is not None:
                    self.historical_data[symbol] = data
                    logger.info(f"✅ Loaded {len(data)} historical records for {symbol}")
                else:
                    logger.warning(f"⚠️ No historical data available for {symbol}")
                    
            except Exception as e:
                logger.error(f"Error loading historical data for {symbol}: {e}")
                
    async def _fetch_historical_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch historical data from exchanges"""
        for exchange_name, exchange in self.exchanges.items():
            try:
            # Convert symbol format if needed
            exchange_symbol = symbol
            if exchange_name == 'bybit' and '/' in symbol:
                exchange_symbol = symbol.replace('/', '')
                    
                # Fetch OHLCV data
                ohlcv = await exchange.fetch_ohlcv(
                    exchange_symbol, 
                    '1h', 
                    limit=1000
                )
                
                if ohlcv:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df['symbol'] = symbol
                    df['source'] = exchange_name
                    
                    return df
                    
            except Exception as e:
                logger.warning(f"Failed to fetch historical data from {exchange_name} for {symbol}: {e}")
                continue
                
        # Fallback to Yahoo Finance
        try:
            yf_symbol = symbol.replace('/', '-')
            ticker = yf.Ticker(yf_symbol)
            data = ticker.history(period=f"{self.config['historical_days']}d", interval='1h')
            
            if not data.empty:
                df = data.reset_index()
                df['symbol'] = symbol
                df['source'] = 'yfinance'
                df = df.rename(columns={'Datetime': 'timestamp'})
                
                return df
                
        except Exception as e:
            logger.warning(f"Yahoo Finance fallback failed for {symbol}: {e}")
            
        return None
        
    async def _realtime_data_loop(self):
        """Main loop for collecting real-time data"""
        while self.running:
            try:
                for symbol in self.config['symbols']:
                    await self._update_realtime_data(symbol)
                    
                # Wait before next update
                await asyncio.sleep(self.config['update_interval'])
                
            except Exception as e:
                logger.error(f"Error in realtime data loop: {e}")
                await asyncio.sleep(self.config['update_interval'])
                
    async def _update_realtime_data(self, symbol: str):
        """Update real-time data for a symbol"""
        try:
            # Try exchanges first
            for exchange_name, exchange in self.exchanges.items():
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    
                    if ticker:
                        # Create market data
                        market_data = MarketData(
                            symbol=symbol,
                            timestamp=datetime.now(),
                            open=ticker['open'],
                            high=ticker['high'],
                            low=ticker['low'],
                            close=ticker['close'],
                            volume=ticker['baseVolume'],
                            source=exchange_name
                        )
                        
                        # Convert to DataFrame row
                        data_row = pd.DataFrame([{
                            'timestamp': market_data.timestamp,
                            'open': market_data.open,
                            'high': market_data.high,
                            'low': market_data.low,
                            'close': market_data.close,
                            'volume': market_data.volume,
                            'symbol': market_data.symbol,
                            'source': market_data.source
                        }])
                        
                        # Update realtime data
                        if symbol in self.realtime_data:
                            self.realtime_data[symbol] = pd.concat([
                                self.realtime_data[symbol], data_row
                            ], ignore_index=True)
                            
                            # Keep only last 1000 records
                            if len(self.realtime_data[symbol]) > 1000:
                                self.realtime_data[symbol] = self.realtime_data[symbol].tail(1000)
                                
                        # Update historical data
                        if symbol in self.historical_data:
                            self.historical_data[symbol] = pd.concat([
                                self.historical_data[symbol], data_row
                            ], ignore_index=True)
                            
                            # Keep only last 5000 records
                            if len(self.historical_data[symbol]) > 5000:
                                self.historical_data[symbol] = self.historical_data[symbol].tail(5000)
                                
                        # Save to database
                        await self.database.save_market_data(market_data)
                        
                        self.last_update[symbol] = datetime.now()
                        
                        logger.debug(f"📊 Updated realtime data for {symbol}")
                        break
                        
                except Exception as e:
                    logger.debug(f"Failed to update {symbol} from {exchange_name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error updating realtime data for {symbol}: {e}")
            
    async def _websocket_data_loop(self):
        """WebSocket data collection loop"""
        while self.running:
            try:
                # Initialize WebSocket connections if not already done
                if not self.websocket_connections:
                    await self._initialize_websockets()
                    
                # Keep connections alive
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in websocket loop: {e}")
                await asyncio.sleep(30)
                
    async def _initialize_websockets(self):
        """Initialize WebSocket connections for real-time data"""
        try:
            # Bybit WebSocket
            if 'bybit' in self.exchanges:
                await self._connect_bybit_websocket()
                
        except Exception as e:
            logger.error(f"Error initializing websockets: {e}")
            
    async def _connect_bybit_websocket(self):
        """Connect to Bybit WebSocket"""
        try:
            # Create WebSocket URL for Bybit
            # Bybit uses different WebSocket endpoints
            ws_url = "wss://stream.bybit.com/v5/public/spot"
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    stream_data = data.get('data', {})
                    
                    if 's' in stream_data:  # Symbol
                        symbol = f"{stream_data['s'][:-4]}/{stream_data['s'][-4:]}"
                        
                        market_data = MarketData(
                            symbol=symbol,
                            timestamp=datetime.now(),
                            open=float(stream_data.get('o', 0)),
                            high=float(stream_data.get('h', 0)),
                            low=float(stream_data.get('l', 0)),
                            close=float(stream_data.get('c', 0)),
                            volume=float(stream_data.get('v', 0)),
                            source='binance_ws'
                        )
                        
                        # Process WebSocket data
                        asyncio.create_task(self._process_websocket_data(market_data))
                        
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")
                    
            def on_error(ws, error):
                logger.error(f"WebSocket error: {error}")
                
            def on_close(ws, close_status_code, close_msg):
                logger.warning("WebSocket connection closed")
                
            def on_open(ws):
                logger.info("✅ Bybit WebSocket connected")
                
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            self.websocket_connections['bybit'] = ws
            
            # Start WebSocket in background
            asyncio.create_task(self._run_websocket(ws))
            
        except Exception as e:
            logger.error(f"Error connecting to Bybit WebSocket: {e}")
            
    async def _run_websocket(self, ws):
        """Run WebSocket connection"""
        try:
            ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket run error: {e}")
            
    async def _process_websocket_data(self, market_data: MarketData):
        """Process data received from WebSocket"""
        try:
            symbol = market_data.symbol
            
            # Convert to DataFrame row
            data_row = pd.DataFrame([{
                'timestamp': market_data.timestamp,
                'open': market_data.open,
                'high': market_data.high,
                'low': market_data.low,
                'close': market_data.close,
                'volume': market_data.volume,
                'symbol': market_data.symbol,
                'source': market_data.source
            }])
            
            # Update realtime data
            if symbol in self.realtime_data:
                self.realtime_data[symbol] = pd.concat([
                    self.realtime_data[symbol], data_row
                ], ignore_index=True)
                
                # Keep only last 1000 records
                if len(self.realtime_data[symbol]) > 1000:
                    self.realtime_data[symbol] = self.realtime_data[symbol].tail(1000)
                    
            # Save to database
            await self.database.save_market_data(market_data)
            
            logger.debug(f"📡 WebSocket data processed for {symbol}")
            
        except Exception as e:
            logger.error(f"Error processing WebSocket data: {e}")
            
    async def _historical_data_update_loop(self):
        """Background loop for updating historical data"""
        while self.running:
            try:
                # Update historical data every hour
                await asyncio.sleep(3600)
                
                for symbol in self.config['symbols']:
                    try:
                        # Fetch latest historical data
                        new_data = await self._fetch_historical_data(symbol)
                        
                        if new_data is not None and len(new_data) > 0:
                            # Update historical data
                            if symbol in self.historical_data:
                                self.historical_data[symbol] = pd.concat([
                                    self.historical_data[symbol], new_data
                                ], ignore_index=True).drop_duplicates(subset=['timestamp']).sort_values('timestamp')
                                
                                # Keep only last 5000 records
                                if len(self.historical_data[symbol]) > 5000:
                                    self.historical_data[symbol] = self.historical_data[symbol].tail(5000)
                            else:
                                self.historical_data[symbol] = new_data
                                
                            # Save to database
                            await self.database.save_historical_data(symbol, new_data)
                            
                            logger.info(f"📈 Updated historical data for {symbol}")
                            
                    except Exception as e:
                        logger.error(f"Error updating historical data for {symbol}: {e}")
                        
            except Exception as e:
                logger.error(f"Error in historical data update loop: {e}")
                
    async def get_latest_data(self) -> Dict[str, pd.DataFrame]:
        """Get latest market data for all symbols"""
        return self.historical_data.copy()
        
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        try:
            if symbol in self.realtime_data and len(self.realtime_data[symbol]) > 0:
                return float(self.realtime_data[symbol]['close'].iloc[-1])
            elif symbol in self.historical_data and len(self.historical_data[symbol]) > 0:
                return float(self.historical_data[symbol]['close'].iloc[-1])
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return None
            
    async def get_historical_data(self, symbol: str, timeframe: str = '1h', limit: int = 1000) -> Optional[pd.DataFrame]:
        """Get historical data for a symbol"""
        try:
            if symbol in self.historical_data:
                data = self.historical_data[symbol].copy()
                
                # Apply timeframe filtering if needed
                if timeframe != '1h':
                    # Resample data to requested timeframe
                    data = data.set_index('timestamp').resample(timeframe).agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    }).dropna().reset_index()
                    
                return data.tail(limit) if limit else data
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return None
            
    async def get_market_summary(self) -> Dict:
        """Get market summary for all symbols"""
        summary = {}
        
        try:
            for symbol in self.config['symbols']:
                current_price = await self.get_current_price(symbol)
                
                if current_price:
                    # Calculate 24h change
                    historical_data = await self.get_historical_data(symbol, limit=24)
                    
                    if historical_data is not None and len(historical_data) > 1:
                        price_24h_ago = float(historical_data['close'].iloc[0])
                        change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
                        
                        summary[symbol] = {
                            'price': current_price,
                            'change_24h': change_24h,
                            'volume_24h': float(historical_data['volume'].sum()) if 'volume' in historical_data.columns else 0,
                            'last_update': self.last_update.get(symbol)
                        }
                    else:
                        summary[symbol] = {
                            'price': current_price,
                            'change_24h': 0,
                            'volume_24h': 0,
                            'last_update': self.last_update.get(symbol)
                        }
                        
        except Exception as e:
            logger.error(f"Error getting market summary: {e}")
            
        return summary
        
    async def is_healthy(self) -> bool:
        """Check if data collector is healthy"""
        try:
            # Check if we have recent data for at least one symbol
            recent_data_count = 0
            
            for symbol in self.config['symbols']:
                if symbol in self.last_update:
                    time_since_update = (datetime.now() - self.last_update[symbol]).total_seconds()
                    if time_since_update < 300:  # 5 minutes
                        recent_data_count += 1
                        
            return recent_data_count > 0
            
        except Exception:
            return False