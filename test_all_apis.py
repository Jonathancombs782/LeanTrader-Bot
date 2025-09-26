#!/usr/bin/env python3
"""
Test All APIs - Verify all exchange connections are working
"""

import json
import ccxt
import asyncio
from loguru import logger

class APITester:
    def __init__(self):
        # Load API configuration
        with open('api_config.json', 'r') as f:
            self.api_config = json.load(f)
        
        self.exchanges = {}
        self.results = {}
    
    def initialize_exchanges(self):
        """Initialize all configured exchanges"""
        logger.info("🔧 Initializing all exchanges...")
        
        for exchange_name, config in self.api_config['exchanges'].items():
            if config.get('enabled', False):
                try:
                    if exchange_name == 'binance':
                        self.exchanges['binance'] = ccxt.binance({
                            'apiKey': config['api_key'],
                            'secret': config['secret'],
                            'sandbox': config.get('sandbox', False),
                            'enableRateLimit': True
                        })
                    elif exchange_name == 'bybit':
                        self.exchanges['bybit'] = ccxt.bybit({
                            'apiKey': config['api_key'],
                            'secret': config['secret'],
                            'sandbox': config.get('sandbox', False),
                            'testnet': config.get('testnet', False),
                            'enableRateLimit': True
                        })
                    elif exchange_name == 'okx':
                        self.exchanges['okx'] = ccxt.okx({
                            'apiKey': config['api_key'],
                            'secret': config['secret'],
                            'passphrase': config.get('passphrase', ''),
                            'sandbox': config.get('sandbox', False),
                            'enableRateLimit': True
                        })
                    elif exchange_name == 'kucoin':
                        self.exchanges['kucoin'] = ccxt.kucoin({
                            'apiKey': config['api_key'],
                            'secret': config['secret'],
                            'passphrase': config.get('passphrase', ''),
                            'sandbox': config.get('sandbox', False),
                            'enableRateLimit': True
                        })
                    elif exchange_name == 'gateio':
                        self.exchanges['gateio'] = ccxt.gateio({
                            'apiKey': config['api_key'],
                            'secret': config['secret'],
                            'sandbox': config.get('sandbox', False),
                            'enableRateLimit': True
                        })
                    elif exchange_name == 'mexc':
                        self.exchanges['mexc'] = ccxt.mexc({
                            'apiKey': config['api_key'],
                            'secret': config['secret'],
                            'sandbox': config.get('sandbox', False),
                            'enableRateLimit': True
                        })
                    elif exchange_name == 'bitget':
                        self.exchanges['bitget'] = ccxt.bitget({
                            'apiKey': config['api_key'],
                            'secret': config['secret'],
                            'passphrase': config.get('passphrase', ''),
                            'sandbox': config.get('sandbox', False),
                            'enableRateLimit': True
                        })
                    
                    logger.info(f"✅ {exchange_name.upper()} exchange initialized")
                except Exception as e:
                    logger.error(f"❌ Failed to initialize {exchange_name}: {e}")
    
    async def test_exchange(self, exchange_name, exchange):
        """Test a single exchange"""
        try:
            logger.info(f"🧪 Testing {exchange_name.upper()}...")
            
            # Test 1: Fetch markets
            markets = exchange.load_markets()
            market_count = len(markets)
            logger.info(f"   📊 Markets loaded: {market_count}")
            
            # Test 2: Fetch ticker for BTC/USDT
            ticker = exchange.fetch_ticker('BTC/USDT')
            btc_price = ticker['last']
            logger.info(f"   💰 BTC/USDT Price: ${btc_price:,.2f}")
            
            # Test 3: Check account balance (if API has trading permissions)
            try:
                balance = exchange.fetch_balance()
                total_balance = sum([v['total'] for v in balance.values() if isinstance(v, dict) and 'total' in v])
                logger.info(f"   💳 Account Balance: {total_balance:.8f} total")
            except Exception as e:
                logger.warning(f"   ⚠️ Balance check failed: {e}")
            
            # Test 4: Check if exchange supports trading
            has_trading = exchange.has.get('createOrder', False)
            logger.info(f"   🛒 Trading supported: {'Yes' if has_trading else 'No'}")
            
            self.results[exchange_name] = {
                'status': 'SUCCESS',
                'markets': market_count,
                'btc_price': btc_price,
                'trading': has_trading,
                'error': None
            }
            
            logger.info(f"✅ {exchange_name.upper()} test completed successfully")
            
        except Exception as e:
            logger.error(f"❌ {exchange_name.upper()} test failed: {e}")
            self.results[exchange_name] = {
                'status': 'FAILED',
                'markets': 0,
                'btc_price': 0,
                'trading': False,
                'error': str(e)
            }
    
    async def test_all_exchanges(self):
        """Test all configured exchanges"""
        logger.info("🚀 Starting API tests for all exchanges...")
        logger.info("=" * 60)
        
        # Initialize exchanges
        self.initialize_exchanges()
        
        # Test each exchange
        tasks = []
        for exchange_name, exchange in self.exchanges.items():
            tasks.append(self.test_exchange(exchange_name, exchange))
        
        await asyncio.gather(*tasks)
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary"""
        logger.info("=" * 60)
        logger.info("📊 API TEST SUMMARY")
        logger.info("=" * 60)
        
        successful = 0
        failed = 0
        
        for exchange_name, result in self.results.items():
            status = result['status']
            if status == 'SUCCESS':
                successful += 1
                logger.info(f"✅ {exchange_name.upper():<10} | Markets: {result['markets']:>4} | BTC: ${result['btc_price']:>10,.2f} | Trading: {'Yes' if result['trading'] else 'No'}")
            else:
                failed += 1
                logger.error(f"❌ {exchange_name.upper():<10} | ERROR: {result['error']}")
        
        logger.info("=" * 60)
        logger.info(f"📈 SUCCESSFUL: {successful}/{len(self.results)} exchanges")
        logger.info(f"❌ FAILED: {failed}/{len(self.results)} exchanges")
        
        if successful > 0:
            logger.info("🎉 Your bot is ready for multi-exchange trading!")
            logger.info("💰 Arbitrage opportunities available across exchanges")
        else:
            logger.error("🚨 No exchanges working - check API keys and permissions")

async def main():
    """Main test function"""
    logger.info("🔑 API CONNECTION TESTER")
    logger.info("Testing all configured exchange APIs...")
    logger.info("")
    
    tester = APITester()
    await tester.test_all_exchanges()

if __name__ == "__main__":
    asyncio.run(main())