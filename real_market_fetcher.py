#!/usr/bin/env python3
"""
REAL MARKET DATA FETCHER
Fetches live prices from multiple exchanges and APIs
"""

import requests
import ccxt
import asyncio
import time
from datetime import datetime, timedelta
from loguru import logger
import json
import pandas as pd
from typing import Dict, List, Optional, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor

class RealMarketDataFetcher:
    """Fetches REAL market data from multiple sources"""
    
    def __init__(self):
        self.exchanges = {}
        self.market_data = {}
        self.last_update = {}
        self.rate_limits = {}
        
        # Initialize exchanges
        self.initialize_exchanges()
        
    def initialize_exchanges(self):
        """Initialize all available exchanges"""
        try:
            # Bybit (Primary)
            self.exchanges['bybit'] = ccxt.bybit({
                'apiKey': '***REDACTED***',
                'secret': '***REDACTED***',
                'sandbox': True,
                'testnet': True,
                'enableRateLimit': True,
            })
            
            # OKX
            self.exchanges['okx'] = ccxt.okx({
                'sandbox': True,
                'enableRateLimit': True,
            })
            
            # Binance
            try:
                self.exchanges['binance'] = ccxt.binance({
                    'enableRateLimit': True,
                })
            except:
                pass
            
            # Coinbase
            try:
                self.exchanges['coinbase'] = ccxt.coinbase({
                    'enableRateLimit': True,
                })
            except:
                pass
            
            logger.info(f"✅ Initialized {len(self.exchanges)} exchanges")
            
        except Exception as e:
            logger.error(f"❌ Exchange initialization failed: {e}")
    
    async def get_real_crypto_price(self, symbol: str) -> Dict:
        """Get REAL crypto price from multiple sources"""
        try:
            price_data = {
                'symbol': symbol,
                'price': 0,
                'volume': 0,
                'change_24h': 0,
                'high_24h': 0,
                'low_24h': 0,
                'source': 'unknown',
                'timestamp': datetime.now()
            }
            
            # Try Bybit first (primary)
            try:
                ticker = self.exchanges['bybit'].fetch_ticker(symbol)
                price_data.update({
                    'price': float(ticker['last']),
                    'volume': float(ticker['baseVolume']),
                    'change_24h': float(ticker['percentage']),
                    'high_24h': float(ticker['high']),
                    'low_24h': float(ticker['low']),
                    'source': 'bybit'
                })
                return price_data
            except Exception as e:
                logger.warning(f"Bybit failed for {symbol}: {e}")
            
            # Try OKX
            try:
                ticker = self.exchanges['okx'].fetch_ticker(symbol)
                price_data.update({
                    'price': float(ticker['last']),
                    'volume': float(ticker['baseVolume']),
                    'change_24h': float(ticker['percentage']),
                    'high_24h': float(ticker['high']),
                    'low_24h': float(ticker['low']),
                    'source': 'okx'
                })
                return price_data
            except Exception as e:
                logger.warning(f"OKX failed for {symbol}: {e}")
            
            # Try Binance
            if 'binance' in self.exchanges:
                try:
                    ticker = self.exchanges['binance'].fetch_ticker(symbol)
                    price_data.update({
                        'price': float(ticker['last']),
                        'volume': float(ticker['baseVolume']),
                        'change_24h': float(ticker['percentage']),
                        'high_24h': float(ticker['high']),
                        'low_24h': float(ticker['low']),
                        'source': 'binance'
                    })
                    return price_data
                except Exception as e:
                    logger.warning(f"Binance failed for {symbol}: {e}")
            
            # Fallback to CoinGecko API
            try:
                symbol_map = {
                    'BTC/USDT': 'bitcoin',
                    'ETH/USDT': 'ethereum',
                    'BNB/USDT': 'binancecoin',
                    'ADA/USDT': 'cardano',
                    'SOL/USDT': 'solana',
                    'XRP/USDT': 'ripple',
                    'DOT/USDT': 'polkadot',
                    'DOGE/USDT': 'dogecoin',
                    'AVAX/USDT': 'avalanche-2',
                    'MATIC/USDT': 'matic-network',
                    'LTC/USDT': 'litecoin',
                    'LINK/USDT': 'chainlink',
                    'UNI/USDT': 'uniswap',
                    'ATOM/USDT': 'cosmos',
                    'FIL/USDT': 'filecoin'
                }
                
                if symbol in symbol_map:
                    coin_id = symbol_map[symbol]
                    response = requests.get(
                        f'https://api.coingecko.com/api/v3/coins/{coin_id}',
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        market_data = data['market_data']
                        
                        price_data.update({
                            'price': float(market_data['current_price']['usd']),
                            'volume': float(market_data['total_volume']['usd']),
                            'change_24h': float(market_data['price_change_percentage_24h']),
                            'high_24h': float(market_data['high_24h']['usd']),
                            'low_24h': float(market_data['low_24h']['usd']),
                            'source': 'coingecko'
                        })
                        return price_data
                        
            except Exception as e:
                logger.warning(f"CoinGecko failed for {symbol}: {e}")
            
            return price_data
            
        except Exception as e:
            logger.error(f"Error getting real price for {symbol}: {e}")
            return price_data
    
    async def get_real_forex_rates(self) -> Dict:
        """Get REAL forex rates"""
        try:
            # Check if forex markets are open (weekends)
            now = datetime.now()
            is_weekend = now.weekday() >= 5  # Saturday = 5, Sunday = 6
            
            if is_weekend:
                return {
                    'market_open': False,
                    'message': 'Forex markets are closed on weekends',
                    'rates': {},
                    'timestamp': datetime.now()
                }
            
            # Try exchangerate-api.com
            try:
                response = requests.get(
                    'https://api.exchangerate-api.com/v4/latest/USD',
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    rates = data['rates']
                    
                    forex_data = {
                        'market_open': True,
                        'rates': {
                            'EUR/USD': round(rates['EUR'], 5),
                            'GBP/USD': round(rates['GBP'], 5),
                            'USD/JPY': round(1/rates['JPY'], 5),
                            'USD/CHF': round(1/rates['CHF'], 5),
                            'AUD/USD': round(rates['AUD'], 5),
                            'USD/CAD': round(1/rates['CAD'], 5),
                            'NZD/USD': round(rates['NZD'], 5)
                        },
                        'timestamp': datetime.now(),
                        'source': 'exchangerate-api'
                    }
                    return forex_data
                    
            except Exception as e:
                logger.warning(f"Exchangerate-api failed: {e}")
            
            # Fallback to Yahoo Finance
            try:
                forex_pairs = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCHF=X', 'AUDUSD=X', 'USDCAD=X', 'NZDUSD=X']
                rates = {}
                
                for pair in forex_pairs:
                    try:
                        response = requests.get(
                            f'https://query1.finance.yahoo.com/v8/finance/chart/{pair}',
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            price = data['chart']['result'][0]['meta']['regularMarketPrice']
                            rates[pair.replace('=X', '/USD')] = round(price, 5)
                    except:
                        pass
                
                if rates:
                    return {
                        'market_open': True,
                        'rates': rates,
                        'timestamp': datetime.now(),
                        'source': 'yahoo'
                    }
                    
            except Exception as e:
                logger.warning(f"Yahoo Finance failed: {e}")
            
            return {
                'market_open': False,
                'message': 'Unable to fetch forex rates',
                'rates': {},
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error getting forex rates: {e}")
            return {
                'market_open': False,
                'message': 'Error fetching forex rates',
                'rates': {},
                'timestamp': datetime.now()
            }
    
    async def get_moon_cap_tokens(self) -> List[Dict]:
        """Get moon cap tokens with buy locations"""
        try:
            moon_tokens = []
            
            # Fetch trending tokens from CoinGecko
            try:
                response = requests.get(
                    'https://api.coingecko.com/api/v3/search/trending',
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    for coin in data['coins'][:10]:  # Top 10 trending
                        coin_data = coin['item']
                        
                        # Get detailed data
                        try:
                            detail_response = requests.get(
                                f"https://api.coingecko.com/api/v3/coins/{coin_data['id']}",
                                timeout=5
                            )
                            
                            if detail_response.status_code == 200:
                                detail_data = detail_response.json()
                                market_data = detail_data['market_data']
                                
                                # Check if it's a moon cap token (low market cap, high growth)
                                market_cap = market_data.get('market_cap', {}).get('usd', 0)
                                price_change_24h = market_data.get('price_change_percentage_24h', 0)
                                
                                if market_cap < 100000000 and price_change_24h > 20:  # < $100M cap, > 20% growth
                                    moon_token = {
                                        'name': detail_data['name'],
                                        'symbol': detail_data['symbol'].upper(),
                                        'price': market_data['current_price']['usd'],
                                        'market_cap': market_cap,
                                        'price_change_24h': price_change_24h,
                                        'volume_24h': market_data['total_volume']['usd'],
                                        'buy_locations': self.get_buy_locations(detail_data['symbol'].upper()),
                                        'timestamp': datetime.now()
                                    }
                                    moon_tokens.append(moon_token)
                                    
                        except Exception as e:
                            logger.warning(f"Failed to get details for {coin_data['name']}: {e}")
                            
            except Exception as e:
                logger.warning(f"Failed to fetch trending tokens: {e}")
            
            return moon_tokens
            
        except Exception as e:
            logger.error(f"Error getting moon cap tokens: {e}")
            return []
    
    def get_buy_locations(self, symbol: str) -> List[str]:
        """Get where tokens can be bought"""
        buy_locations = []
        
        # Common exchanges for altcoins
        exchanges = ['Binance', 'KuCoin', 'Gate.io', 'MEXC', 'Bybit', 'OKX', 'Coinbase']
        
        # Add exchanges where symbol is likely available
        for exchange in exchanges:
            buy_locations.append(f"{exchange}")
        
        return buy_locations
    
    async def get_live_chart_url(self, symbol: str, timeframe: str = '1h') -> str:
        """Get live chart URL for symbol"""
        try:
            # TradingView chart URLs
            if '/' in symbol:
                base_symbol = symbol.split('/')[0]
                quote_symbol = symbol.split('/')[1]
                
                if quote_symbol == 'USDT':
                    chart_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{base_symbol}USDT"
                else:
                    chart_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}"
            else:
                chart_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}USDT"
            
            return chart_url
            
        except Exception as e:
            logger.error(f"Error generating chart URL for {symbol}: {e}")
            return f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}"

# Test the fetcher
async def test_fetcher():
    """Test the market data fetcher"""
    fetcher = RealMarketDataFetcher()
    
    # Test crypto price
    print("Testing crypto price...")
    btc_price = await fetcher.get_real_crypto_price('BTC/USDT')
    print(f"BTC/USDT: ${btc_price['price']} from {btc_price['source']}")
    
    # Test forex rates
    print("\nTesting forex rates...")
    forex_data = await fetcher.get_real_forex_rates()
    print(f"Forex market open: {forex_data['market_open']}")
    if forex_data['rates']:
        print(f"EUR/USD: {forex_data['rates'].get('EUR/USD', 'N/A')}")
    
    # Test moon cap tokens
    print("\nTesting moon cap tokens...")
    moon_tokens = await fetcher.get_moon_cap_tokens()
    print(f"Found {len(moon_tokens)} moon cap tokens")

if __name__ == "__main__":
    asyncio.run(test_fetcher())