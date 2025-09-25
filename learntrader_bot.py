#!/usr/bin/env python3
"""
Learntrader Bot - Professional Multi-Asset Trading System
Trades: Crypto, Forex, Web3, Micro Moon Spotter
"""

import asyncio
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
import json
import requests
from typing import Dict, List, Optional, Tuple
import websocket
import threading
import time

class LearntraderBot:
    """Professional multi-asset trading bot with micro moon spotting"""
    
    def __init__(self):
        self.running = False
        
        # Exchange configurations
        self.exchanges = {}
        self.active_exchanges = []
        
        # Trading pairs for different asset classes
        self.crypto_pairs = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT',
            'MATIC/USDT', 'DOT/USDT', 'LINK/USDT', 'UNI/USDT', 'AVAX/USDT'
        ]
        
        self.forex_pairs = [
            'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'AUD/USD',
            'USD/CAD', 'NZD/USD', 'EUR/GBP', 'EUR/JPY', 'GBP/JPY'
        ]
        
        self.web3_tokens = [
            'AAVE/USDT', 'COMP/USDT', 'MKR/USDT', 'SNX/USDT', 'YFI/USDT',
            'CRV/USDT', '1INCH/USDT', 'SUSHI/USDT', 'BAL/USDT', 'LRC/USDT'
        ]
        
        # Micro moon detection
        self.micro_moons = []
        self.new_listings = []
        
        # Market data storage
        self.market_data = {}
        self.price_alerts = {}
        
        # Trading signals
        self.signals = {
            'crypto': {},
            'forex': {},
            'web3': {},
            'micro_moons': {}
        }
        
        # Performance tracking
        self.performance = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0.0,
            'daily_pnl': 0.0
        }
        
    async def initialize(self):
        """Initialize all exchanges and connections"""
        logger.info("🚀 Initializing Learntrader Bot...")
        
        try:
            # Initialize Bybit (Crypto)
            self.exchanges['bybit'] = ccxt.bybit({
                'apiKey': '***REDACTED***',
                'secret': '***REDACTED***',
                'sandbox': True,
                'enableRateLimit': True,
            })
            
            # Initialize Binance (More crypto pairs)
            self.exchanges['binance'] = ccxt.binance({
                'apiKey': '',  # Add if you have
                'secret': '',
                'sandbox': True,
                'enableRateLimit': True,
            })
            
            # Initialize OKX (Web3 tokens)
            self.exchanges['okx'] = ccxt.okx({
                'apiKey': '',  # Add if you have
                'secret': '',
                'sandbox': True,
                'enableRateLimit': True,
            })
            
            # Test connections
            for name, exchange in self.exchanges.items():
                try:
                    markets = exchange.load_markets()
                    logger.info(f"✅ {name.upper()} connected - {len(markets)} markets")
                    self.active_exchanges.append(name)
                except Exception as e:
                    logger.warning(f"⚠️ {name.upper()} connection failed: {e}")
            
            # Initialize micro moon spotter
            await self.initialize_micro_moon_spotter()
            
            logger.info("✅ Learntrader Bot initialized successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False
    
    async def initialize_micro_moon_spotter(self):
        """Initialize micro moon token spotter"""
        logger.info("🔍 Initializing Micro Moon Spotter...")
        
        # CoinGecko API for new listings
        self.coingecko_url = "https://api.coingecko.com/api/v3"
        
        # CoinMarketCap API for trending tokens
        self.cmc_url = "https://pro-api.coinmarketcap.com/v1"
        
        logger.info("✅ Micro Moon Spotter ready!")
    
    async def fetch_market_data(self, asset_type: str, symbols: List[str]) -> Dict:
        """Fetch market data for specific asset type"""
        market_data = {}
        
        for exchange_name in self.active_exchanges:
            exchange = self.exchanges[exchange_name]
            
            for symbol in symbols:
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    if symbol not in market_data:
                        market_data[symbol] = {}
                    
                    market_data[symbol][exchange_name] = {
                        'price': ticker['last'],
                        'change_24h': ticker['change'],
                        'volume': ticker['baseVolume'],
                        'high': ticker['high'],
                        'low': ticker['low'],
                        'timestamp': datetime.now()
                    }
                    
                except Exception as e:
                    logger.debug(f"Error fetching {symbol} from {exchange_name}: {e}")
        
        return market_data
    
    async def analyze_crypto_signals(self, market_data: Dict) -> Dict:
        """Analyze crypto trading signals"""
        signals = {}
        
        for symbol, exchanges in market_data.items():
            try:
                # Get average price across exchanges
                prices = [data['price'] for data in exchanges.values()]
                avg_price = sum(prices) / len(prices)
                
                # Get average 24h change
                changes = [data['change_24h'] for data in exchanges.values()]
                avg_change = sum(changes) / len(changes)
                
                # Simple signal logic
                signal_strength = 0
                action = 'HOLD'
                reasoning = []
                
                # Price momentum analysis
                if avg_change > 500:
                    signal_strength += 0.3
                    action = 'SELL'
                    reasoning.append(f"Strong uptrend: +{avg_change:.2f}")
                elif avg_change < -500:
                    signal_strength += 0.3
                    action = 'BUY'
                    reasoning.append(f"Strong downtrend: {avg_change:.2f}")
                
                # Volume analysis
                volumes = [data['volume'] for data in exchanges.values()]
                avg_volume = sum(volumes) / len(volumes)
                
                if avg_volume > 1000000:  # High volume
                    signal_strength += 0.2
                    reasoning.append("High volume detected")
                
                # RSI-like calculation
                highs = [data['high'] for data in exchanges.values()]
                lows = [data['low'] for data in exchanges.values()]
                
                if highs and lows:
                    avg_high = sum(highs) / len(highs)
                    avg_low = sum(lows) / len(lows)
                    
                    if avg_price > (avg_high + avg_low) / 2:
                        signal_strength += 0.1
                        reasoning.append("Price above average")
                
                signals[symbol] = {
                    'action': action,
                    'strength': min(signal_strength, 1.0),
                    'price': avg_price,
                    'change_24h': avg_change,
                    'volume': avg_volume,
                    'reasoning': '; '.join(reasoning),
                    'timestamp': datetime.now()
                }
                
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
        
        return signals
    
    async def analyze_forex_signals(self, market_data: Dict) -> Dict:
        """Analyze forex trading signals"""
        signals = {}
        
        for symbol, exchanges in market_data.items():
            try:
                # Forex-specific analysis
                if not exchanges:
                    continue
                
                exchange_data = list(exchanges.values())[0]  # Forex usually on one exchange
                price = exchange_data['price']
                change = exchange_data['change_24h']
                
                # Forex signal logic
                signal_strength = 0
                action = 'HOLD'
                reasoning = []
                
                # Trend analysis
                if abs(change) > 50:  # Significant move in forex
                    if change > 0:
                        action = 'SELL'  # Sell the base currency
                        signal_strength = 0.7
                        reasoning.append(f"Strong uptrend: +{change:.2f} pips")
                    else:
                        action = 'BUY'  # Buy the base currency
                        signal_strength = 0.7
                        reasoning.append(f"Strong downtrend: {change:.2f} pips")
                
                # Volatility analysis
                if abs(change) > 100:
                    signal_strength += 0.2
                    reasoning.append("High volatility detected")
                
                signals[symbol] = {
                    'action': action,
                    'strength': signal_strength,
                    'price': price,
                    'change_24h': change,
                    'reasoning': '; '.join(reasoning),
                    'timestamp': datetime.now()
                }
                
            except Exception as e:
                logger.error(f"Error analyzing forex {symbol}: {e}")
        
        return signals
    
    async def spot_micro_moons(self) -> List[Dict]:
        """Spot potential micro moon tokens"""
        micro_moons = []
        
        try:
            # Check for new listings on CoinGecko
            response = requests.get(f"{self.coingecko_url}/coins/markets", params={
                'vs_currency': 'usd',
                'order': 'market_cap_asc',
                'per_page': 100,
                'page': 1
            })
            
            if response.status_code == 200:
                data = response.json()
                
                for coin in data:
                    market_cap = coin.get('market_cap', 0)
                    price_change = coin.get('price_change_percentage_24h', 0)
                    volume = coin.get('total_volume', 0)
                    
                    # Micro moon criteria
                    if (market_cap < 10000000 and  # Under $10M market cap
                        price_change > 20 and      # 20%+ price increase
                        volume > 100000):          # Decent volume
                        
                        micro_moon = {
                            'symbol': coin['symbol'].upper(),
                            'name': coin['name'],
                            'price': coin['current_price'],
                            'market_cap': market_cap,
                            'change_24h': price_change,
                            'volume': volume,
                            'rank': coin.get('market_cap_rank'),
                            'timestamp': datetime.now(),
                            'potential': 'HIGH' if price_change > 50 else 'MEDIUM'
                        }
                        
                        micro_moons.append(micro_moon)
                        logger.info(f"🌙 Micro Moon Spotted: {micro_moon['name']} ({micro_moon['symbol']}) - {micro_moon['change_24h']:.1f}%")
            
        except Exception as e:
            logger.error(f"Error spotting micro moons: {e}")
        
        return micro_moons
    
    async def trading_loop(self):
        """Main trading loop"""
        logger.info("🎯 Starting Learntrader trading loop...")
        
        while self.running:
            try:
                current_time = datetime.now().strftime('%H:%M:%S')
                logger.info(f"📊 Learntrader Analysis - {current_time}")
                
                # 1. Analyze Crypto Markets
                logger.info("🪙 Analyzing Crypto Markets...")
                crypto_data = await self.fetch_market_data('crypto', self.crypto_pairs[:5])  # Top 5 for demo
                crypto_signals = await self.analyze_crypto_signals(crypto_data)
                
                for symbol, signal in crypto_signals.items():
                    if signal['strength'] > 0.6:
                        logger.info(f"📈 CRYPTO: {symbol} | {signal['action']} | Strength: {signal['strength']:.1%} | Price: ${signal['price']:.2f}")
                        logger.info(f"   💡 Reasoning: {signal['reasoning']}")
                
                # 2. Analyze Forex Markets
                logger.info("💱 Analyzing Forex Markets...")
                forex_data = await self.fetch_market_data('forex', self.forex_pairs[:3])  # Top 3 for demo
                forex_signals = await self.analyze_forex_signals(forex_data)
                
                for symbol, signal in forex_signals.items():
                    if signal['strength'] > 0.5:
                        logger.info(f"💱 FOREX: {symbol} | {signal['action']} | Strength: {signal['strength']:.1%} | Price: {signal['price']:.4f}")
                        logger.info(f"   💡 Reasoning: {signal['reasoning']}")
                
                # 3. Spot Micro Moons
                logger.info("🔍 Scanning for Micro Moons...")
                micro_moons = await self.spot_micro_moons()
                
                if micro_moons:
                    logger.info(f"🌙 Found {len(micro_moons)} potential micro moons!")
                    for moon in micro_moons[:3]:  # Show top 3
                        logger.info(f"   🚀 {moon['name']} ({moon['symbol']}) - {moon['change_24h']:.1f}% | MC: ${moon['market_cap']:,.0f}")
                
                # 4. Web3 Token Analysis
                logger.info("🌐 Analyzing Web3 Tokens...")
                web3_data = await self.fetch_market_data('web3', self.web3_tokens[:3])
                web3_signals = await self.analyze_crypto_signals(web3_data)
                
                for symbol, signal in web3_signals.items():
                    if signal['strength'] > 0.6:
                        logger.info(f"🌐 WEB3: {symbol} | {signal['action']} | Strength: {signal['strength']:.1%} | Price: ${signal['price']:.2f}")
                
                # Wait before next analysis
                await asyncio.sleep(60)  # Analyze every minute
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(30)
    
    async def start(self):
        """Start the Learntrader Bot"""
        logger.info("🚀 Starting Learntrader Bot...")
        logger.info("🎯 Multi-Asset Trading System")
        logger.info("📊 Assets: Crypto, Forex, Web3, Micro Moons")
        logger.info("=" * 50)
        
        if await self.initialize():
            self.running = True
            await self.trading_loop()
        else:
            logger.error("❌ Failed to initialize Learntrader Bot")
    
    async def stop(self):
        """Stop the bot"""
        logger.info("🛑 Stopping Learntrader Bot...")
        self.running = False

async def main():
    """Main entry point"""
    bot = LearntraderBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("👋 Learntrader Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    logger.info("🤖 Learntrader Bot - Professional Multi-Asset Trading System")
    logger.info("=" * 60)
    logger.info("🪙 Crypto Trading")
    logger.info("💱 Forex Trading") 
    logger.info("🌐 Web3 Token Analysis")
    logger.info("🔍 Micro Moon Spotter")
    logger.info("=" * 60)
    logger.info("Starting in 3 seconds...")
    time.sleep(3)
    
    asyncio.run(main())