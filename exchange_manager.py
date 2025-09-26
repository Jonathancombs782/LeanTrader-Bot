"""
Exchange Manager
Manages multiple exchange connections and provides unified interface
"""

from __future__ import annotations
import asyncio
import json
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import ccxt
import ccxt.async_support as ccxt_async

@dataclass
class ExchangeConfig:
    """Exchange configuration"""
    name: str
    enabled: bool
    api_key: str
    secret: str
    passphrase: str = ""
    sandbox: bool = True
    testnet: bool = False
    rate_limit: int = 60
    timeout: int = 10000
    markets: List[str] = None

class ExchangeManager:
    """Manages multiple exchange connections"""
    
    def __init__(self, config_file: str = "api_config.json"):
        self.config_file = config_file
        self.logger = logging.getLogger("exchange_manager")
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.async_exchanges: Dict[str, ccxt_async.Exchange] = {}
        self.configs: Dict[str, ExchangeConfig] = {}
        self.market_data: Dict[str, Dict[str, Any]] = {}
        self.last_update = {}
        
        self._load_config()
        self._initialize_exchanges()
    
    def _load_config(self):
        """Load exchange configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            for exchange_name, exchange_config in config.get('exchanges', {}).items():
                if exchange_config.get('enabled', False):
                    self.configs[exchange_name] = ExchangeConfig(
                        name=exchange_name,
                        enabled=exchange_config.get('enabled', False),
                        api_key=exchange_config.get('api_key', ''),
                        secret=exchange_config.get('secret', ''),
                        passphrase=exchange_config.get('passphrase', ''),
                        sandbox=exchange_config.get('sandbox', True),
                        testnet=exchange_config.get('testnet', False),
                        rate_limit=exchange_config.get('rate_limit', 60),
                        timeout=exchange_config.get('timeout', 10000),
                        markets=exchange_config.get('markets', [])
                    )
            
            self.logger.info(f"Loaded {len(self.configs)} exchange configurations")
            
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            # Use default configuration
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default configuration for paper trading"""
        self.configs = {
            'binance': ExchangeConfig(
                name='binance',
                enabled=True,
                api_key='',
                secret='',
                sandbox=True,
                markets=['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
            ),
            'coinbase': ExchangeConfig(
                name='coinbase',
                enabled=True,
                api_key='',
                secret='',
                passphrase='',
                sandbox=True,
                markets=['BTC/USDT', 'ETH/USDT', 'ADA/USDT']
            )
        }
    
    def _initialize_exchanges(self):
        """Initialize exchange connections"""
        for exchange_name, config in self.configs.items():
            try:
                # Initialize synchronous exchange
                exchange_class = getattr(ccxt, exchange_name)
                exchange_params = {
                    'apiKey': config.api_key,
                    'secret': config.secret,
                    'timeout': config.timeout,
                    'rateLimit': config.rate_limit,
                    'enableRateLimit': True,
                }
                
                if config.passphrase:
                    exchange_params['passphrase'] = config.passphrase
                
                if config.sandbox:
                    exchange_params['sandbox'] = True
                
                if config.testnet:
                    exchange_params['testnet'] = True
                
                self.exchanges[exchange_name] = exchange_class(exchange_params)
                
                # Initialize asynchronous exchange
                async_exchange_class = getattr(ccxt_async, exchange_name)
                self.async_exchanges[exchange_name] = async_exchange_class(exchange_params)
                
                self.logger.info(f"Initialized {exchange_name} exchange")
                
            except Exception as e:
                self.logger.error(f"Error initializing {exchange_name}: {e}")
    
    async def fetch_ticker(self, symbol: str, exchange_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetch ticker data for a symbol"""
        if exchange_name:
            exchanges_to_try = [exchange_name]
        else:
            exchanges_to_try = list(self.async_exchanges.keys())
        
        for ex_name in exchanges_to_try:
            try:
                if ex_name in self.async_exchanges:
                    exchange = self.async_exchanges[ex_name]
                    ticker = await exchange.fetch_ticker(symbol)
                    
                    return {
                        'exchange': ex_name,
                        'symbol': symbol,
                        'price': ticker['last'],
                        'bid': ticker['bid'],
                        'ask': ticker['ask'],
                        'volume': ticker['baseVolume'],
                        'timestamp': ticker['timestamp'],
                        'datetime': ticker['datetime']
                    }
            except Exception as e:
                self.logger.warning(f"Error fetching ticker from {ex_name}: {e}")
                continue
        
        # Return mock data if all exchanges fail
        return self._get_mock_ticker(symbol)
    
    async def fetch_orderbook(self, symbol: str, exchange_name: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """Fetch order book for a symbol"""
        if exchange_name:
            exchanges_to_try = [exchange_name]
        else:
            exchanges_to_try = list(self.async_exchanges.keys())
        
        for ex_name in exchanges_to_try:
            try:
                if ex_name in self.async_exchanges:
                    exchange = self.async_exchanges[ex_name]
                    orderbook = await exchange.fetch_order_book(symbol, limit)
                    
                    return {
                        'exchange': ex_name,
                        'symbol': symbol,
                        'bids': orderbook['bids'],
                        'asks': orderbook['asks'],
                        'timestamp': orderbook['timestamp'],
                        'datetime': orderbook['datetime']
                    }
            except Exception as e:
                self.logger.warning(f"Error fetching orderbook from {ex_name}: {e}")
                continue
        
        # Return mock data if all exchanges fail
        return self._get_mock_orderbook(symbol)
    
    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100, exchange_name: Optional[str] = None) -> List[List]:
        """Fetch OHLCV data for a symbol"""
        if exchange_name:
            exchanges_to_try = [exchange_name]
        else:
            exchanges_to_try = list(self.async_exchanges.keys())
        
        for ex_name in exchanges_to_try:
            try:
                if ex_name in self.async_exchanges:
                    exchange = self.async_exchanges[ex_name]
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                    
                    return ohlcv
            except Exception as e:
                self.logger.warning(f"Error fetching OHLCV from {ex_name}: {e}")
                continue
        
        # Return mock data if all exchanges fail
        return self._get_mock_ohlcv(symbol, timeframe, limit)
    
    async def fetch_balance(self, exchange_name: str) -> Dict[str, Any]:
        """Fetch account balance"""
        try:
            if exchange_name in self.async_exchanges:
                exchange = self.async_exchanges[exchange_name]
                balance = await exchange.fetch_balance()
                return balance
        except Exception as e:
            self.logger.error(f"Error fetching balance from {exchange_name}: {e}")
        
        return {}
    
    async def create_order(self, symbol: str, order_type: str, side: str, amount: float, price: Optional[float] = None, exchange_name: str = 'binance') -> Dict[str, Any]:
        """Create an order (paper trading only)"""
        try:
            if exchange_name in self.async_exchanges:
                exchange = self.async_exchanges[exchange_name]
                
                # For paper trading, we'll simulate the order
                order = {
                    'id': f"paper_{int(time.time() * 1000)}",
                    'symbol': symbol,
                    'type': order_type,
                    'side': side,
                    'amount': amount,
                    'price': price,
                    'status': 'open',
                    'timestamp': int(time.time() * 1000),
                    'datetime': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'filled': 0,
                    'remaining': amount,
                    'cost': amount * (price or 0),
                    'exchange': exchange_name
                }
                
                self.logger.info(f"Paper order created: {order}")
                return order
        except Exception as e:
            self.logger.error(f"Error creating order: {e}")
        
        return {}
    
    def _get_mock_ticker(self, symbol: str) -> Dict[str, Any]:
        """Generate mock ticker data for testing"""
        import random
        base_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 500
        price = base_price * (1 + random.uniform(-0.05, 0.05))
        
        return {
            'exchange': 'mock',
            'symbol': symbol,
            'price': price,
            'bid': price * 0.999,
            'ask': price * 1.001,
            'volume': random.uniform(1000, 10000),
            'timestamp': int(time.time() * 1000),
            'datetime': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _get_mock_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Generate mock order book data for testing"""
        import random
        base_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 500
        price = base_price * (1 + random.uniform(-0.05, 0.05))
        
        bids = []
        asks = []
        
        for i in range(10):
            bid_price = price * (1 - (i + 1) * 0.001)
            ask_price = price * (1 + (i + 1) * 0.001)
            bid_amount = random.uniform(0.1, 1.0)
            ask_amount = random.uniform(0.1, 1.0)
            
            bids.append([bid_price, bid_amount])
            asks.append([ask_price, ask_amount])
        
        return {
            'exchange': 'mock',
            'symbol': symbol,
            'bids': bids,
            'asks': asks,
            'timestamp': int(time.time() * 1000),
            'datetime': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _get_mock_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[List]:
        """Generate mock OHLCV data for testing"""
        import random
        import numpy as np
        
        base_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 500
        ohlcv = []
        
        current_time = int(time.time() * 1000)
        timeframe_ms = 3600000 if timeframe == '1h' else 300000 if timeframe == '5m' else 60000
        
        for i in range(limit):
            timestamp = current_time - (limit - i) * timeframe_ms
            price = base_price * (1 + random.uniform(-0.1, 0.1))
            
            open_price = price
            high_price = price * (1 + random.uniform(0, 0.02))
            low_price = price * (1 - random.uniform(0, 0.02))
            close_price = price * (1 + random.uniform(-0.01, 0.01))
            volume = random.uniform(100, 1000)
            
            ohlcv.append([timestamp, open_price, high_price, low_price, close_price, volume])
        
        return ohlcv
    
    async def get_arbitrage_opportunities(self, symbol: str, min_profit: float = 0.001) -> List[Dict[str, Any]]:
        """Find arbitrage opportunities between exchanges"""
        opportunities = []
        
        try:
            # Get tickers from all exchanges
            tickers = {}
            for exchange_name in self.async_exchanges.keys():
                ticker = await self.fetch_ticker(symbol, exchange_name)
                if ticker:
                    tickers[exchange_name] = ticker
            
            # Find price differences
            if len(tickers) >= 2:
                prices = [(name, ticker['price']) for name, ticker in tickers.items()]
                prices.sort(key=lambda x: x[1])
                
                lowest_price = prices[0]
                highest_price = prices[-1]
                
                profit_potential = highest_price[1] - lowest_price[1]
                profit_percentage = profit_potential / lowest_price[1]
                
                if profit_percentage >= min_profit:
                    opportunities.append({
                        'symbol': symbol,
                        'buy_exchange': lowest_price[0],
                        'sell_exchange': highest_price[0],
                        'buy_price': lowest_price[1],
                        'sell_price': highest_price[1],
                        'profit_potential': profit_potential,
                        'profit_percentage': profit_percentage,
                        'timestamp': int(time.time() * 1000)
                    })
        
        except Exception as e:
            self.logger.error(f"Error finding arbitrage opportunities: {e}")
        
        return opportunities
    
    def get_available_exchanges(self) -> List[str]:
        """Get list of available exchanges"""
        return list(self.exchanges.keys())
    
    def get_exchange_config(self, exchange_name: str) -> Optional[ExchangeConfig]:
        """Get configuration for a specific exchange"""
        return self.configs.get(exchange_name)
    
    async def close_all_connections(self):
        """Close all exchange connections"""
        for exchange in self.async_exchanges.values():
            try:
                await exchange.close()
            except Exception as e:
                self.logger.warning(f"Error closing exchange connection: {e}")

# Global exchange manager instance
exchange_manager = ExchangeManager()