#!/usr/bin/env python3
"""
Professional Bybit Trading Bot
"""

import asyncio
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import os
import json
from loguru import logger

class BybitTradingBot:
    def __init__(self):
        self.exchange = None
        self.running = False
        self.api_key = "***REDACTED***"
        self.secret_key = "***REDACTED***"
        self.sandbox = True
        
    async def initialize(self):
        logger.info("🚀 Initializing Bybit Trading Bot...")
        try:
            self.exchange = ccxt.bybit({
                'apiKey': self.api_key,
                'secret': self.secret_key,
                'sandbox': self.sandbox,
                'enableRateLimit': True,
            })
            markets = await self.exchange.load_markets()
            logger.info(f"✅ Connected to Bybit Testnet - {len(markets)} markets available")
            return True
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    async def get_market_data(self, symbol='BTC/USDT'):
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"Error getting {symbol}: {e}")
            return None
    
    async def analyze_market(self, ticker):
        try:
            price = ticker['last']
            change_24h = ticker['change']
            volume = ticker['baseVolume']
            
            # Simple analysis
            if change_24h < -500:  # Significant drop
                return 'BUY', 0.8, f"Strong buy signal - Price dropped {change_24h}"
            elif change_24h > 500:  # Significant rise
                return 'SELL', 0.8, f"Strong sell signal - Price rose {change_24h}"
            else:
                return 'HOLD', 0.5, f"Neutral - Change: {change_24h}"
        except Exception as e:
            return 'HOLD', 0.0, f"Analysis error: {e}"
    
    async def trading_loop(self):
        logger.info("🎯 Starting trading loop...")
        symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT']
        
        while self.running:
            try:
                logger.info(f"📊 Market Analysis - {datetime.now().strftime('%H:%M:%S')}")
                
                for symbol in symbols:
                    ticker = await self.get_market_data(symbol)
                    if ticker:
                        action, confidence, reasoning = await self.analyze_market(ticker)
                        logger.info(f"📈 {symbol}: ${ticker['last']:.2f} | {action} ({confidence:.0%}) | {reasoning}")
                        
                        if confidence > 0.7 and action != 'HOLD':
                            logger.info(f"🎮 SIMULATION: Would {action} {symbol} at ${ticker['last']:.2f}")
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                await asyncio.sleep(10)
    
    async def start(self):
        logger.info("🚀 Starting Professional Bybit Trading Bot...")
        logger.info(f"🔑 API: {self.api_key[:10]}...")
        logger.info(f"🌐 Mode: {'Testnet' if self.sandbox else 'Live'}")
        
        if await self.initialize():
            self.running = True
            await self.trading_loop()
        else:
            logger.error("❌ Failed to initialize bot")
    
    async def stop(self):
        logger.info("🛑 Stopping bot...")
        self.running = False

async def main():
    bot = BybitTradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    logger.info("🤖 Professional Bybit Trading Bot")
    logger.info("=" * 40)
    logger.info("Starting in 3 seconds...")
    time.sleep(3)
    asyncio.run(main())
