#!/usr/bin/env python3
"""
API Connection Test Script
Tests all exchange API connections and functionality
"""

import asyncio
import sys
import os
import time
from typing import Dict, List, Any

# Add workspace to path
sys.path.append('/workspace')

from exchange_manager import exchange_manager

class APITester:
    """Test API connections and functionality"""
    
    def __init__(self):
        self.exchange_manager = exchange_manager
        self.test_results = {}
        self.symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
    
    async def test_exchange_connection(self, exchange_name: str) -> Dict[str, Any]:
        """Test connection to a specific exchange"""
        result = {
            'exchange': exchange_name,
            'connected': False,
            'markets_loaded': False,
            'ticker_fetched': False,
            'orderbook_fetched': False,
            'balance_fetched': False,
            'errors': []
        }
        
        try:
            print(f"🔍 Testing {exchange_name}...")
            
            # Test basic connection
            if exchange_name in self.exchange_manager.async_exchanges:
                result['connected'] = True
                print(f"  ✅ Connected to {exchange_name}")
            else:
                result['errors'].append("Exchange not initialized")
                print(f"  ❌ {exchange_name} not initialized")
                return result
            
            # Test market loading
            try:
                markets = self.exchange_manager.exchanges[exchange_name].load_markets()
                if markets:
                    result['markets_loaded'] = True
                    print(f"  ✅ Markets loaded: {len(markets)} symbols")
                else:
                    result['errors'].append("No markets loaded")
                    print(f"  ⚠️ No markets loaded")
            except Exception as e:
                result['errors'].append(f"Market loading error: {str(e)}")
                print(f"  ⚠️ Market loading failed: {e}")
            
            # Test ticker fetching
            try:
                for symbol in self.symbols:
                    ticker = await self.exchange_manager.fetch_ticker(symbol, exchange_name)
                    if ticker and 'price' in ticker:
                        result['ticker_fetched'] = True
                        print(f"  ✅ Ticker fetched for {symbol}: ${ticker['price']:.2f}")
                        break
            except Exception as e:
                result['errors'].append(f"Ticker fetching error: {str(e)}")
                print(f"  ⚠️ Ticker fetching failed: {e}")
            
            # Test orderbook fetching
            try:
                orderbook = await self.exchange_manager.fetch_orderbook(self.symbols[0], exchange_name)
                if orderbook and 'bids' in orderbook and 'asks' in orderbook:
                    result['orderbook_fetched'] = True
                    print(f"  ✅ Orderbook fetched: {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks")
            except Exception as e:
                result['errors'].append(f"Orderbook fetching error: {str(e)}")
                print(f"  ⚠️ Orderbook fetching failed: {e}")
            
            # Test balance fetching (if API keys are configured)
            try:
                balance = await self.exchange_manager.fetch_balance(exchange_name)
                if balance:
                    result['balance_fetched'] = True
                    print(f"  ✅ Balance fetched: {len(balance)} currencies")
                else:
                    print(f"  ⚠️ No balance data (API keys may not be configured)")
            except Exception as e:
                result['errors'].append(f"Balance fetching error: {str(e)}")
                print(f"  ⚠️ Balance fetching failed: {e}")
            
        except Exception as e:
            result['errors'].append(f"General error: {str(e)}")
            print(f"  ❌ {exchange_name} test failed: {e}")
        
        return result
    
    async def test_arbitrage_opportunities(self) -> List[Dict[str, Any]]:
        """Test arbitrage opportunity detection"""
        print("\n🔍 Testing arbitrage opportunities...")
        
        opportunities = []
        for symbol in self.symbols:
            try:
                symbol_opportunities = await self.exchange_manager.get_arbitrage_opportunities(symbol, min_profit=0.001)
                opportunities.extend(symbol_opportunities)
                
                if symbol_opportunities:
                    print(f"  ✅ Found {len(symbol_opportunities)} arbitrage opportunities for {symbol}")
                    for opp in symbol_opportunities:
                        print(f"    💰 {opp['buy_exchange']} → {opp['sell_exchange']}: {opp['profit_percentage']:.4f}% profit")
                else:
                    print(f"  ⚠️ No arbitrage opportunities found for {symbol}")
            except Exception as e:
                print(f"  ❌ Arbitrage test failed for {symbol}: {e}")
        
        return opportunities
    
    async def test_multi_platform_scanning(self) -> Dict[str, Any]:
        """Test multi-platform scanning functionality"""
        print("\n🔍 Testing multi-platform scanning...")
        
        scan_results = {
            'exchanges_tested': 0,
            'successful_scans': 0,
            'total_opportunities': 0,
            'errors': []
        }
        
        try:
            # Test each exchange
            for exchange_name in self.exchange_manager.get_available_exchanges():
                scan_results['exchanges_tested'] += 1
                
                try:
                    # Test ticker fetching
                    ticker = await self.exchange_manager.fetch_ticker(self.symbols[0], exchange_name)
                    if ticker:
                        scan_results['successful_scans'] += 1
                        print(f"  ✅ {exchange_name}: Price ${ticker['price']:.2f}")
                    else:
                        print(f"  ⚠️ {exchange_name}: No ticker data")
                except Exception as e:
                    scan_results['errors'].append(f"{exchange_name}: {str(e)}")
                    print(f"  ❌ {exchange_name}: {e}")
            
            # Test arbitrage opportunities
            opportunities = await self.test_arbitrage_opportunities()
            scan_results['total_opportunities'] = len(opportunities)
            
        except Exception as e:
            scan_results['errors'].append(f"Multi-platform scan error: {str(e)}")
            print(f"  ❌ Multi-platform scan failed: {e}")
        
        return scan_results
    
    async def run_all_tests(self):
        """Run all API tests"""
        print("🚀 ULTRA TRADING BOT - API CONNECTION TEST")
        print("=" * 50)
        
        # Test individual exchanges
        print("\n📊 Testing Exchange Connections:")
        print("-" * 30)
        
        for exchange_name in self.exchange_manager.get_available_exchanges():
            result = await self.test_exchange_connection(exchange_name)
            self.test_results[exchange_name] = result
        
        # Test arbitrage opportunities
        print("\n💰 Testing Arbitrage Detection:")
        print("-" * 30)
        arbitrage_opportunities = await self.test_arbitrage_opportunities()
        
        # Test multi-platform scanning
        print("\n🔍 Testing Multi-Platform Scanning:")
        print("-" * 30)
        scan_results = await self.test_multi_platform_scanning()
        
        # Print summary
        self.print_summary(arbitrage_opportunities, scan_results)
    
    def print_summary(self, arbitrage_opportunities: List[Dict], scan_results: Dict):
        """Print test summary"""
        print("\n📋 TEST SUMMARY")
        print("=" * 50)
        
        # Exchange status
        print("\n🏦 Exchange Status:")
        for exchange_name, result in self.test_results.items():
            status = "✅ READY" if result['connected'] and result['ticker_fetched'] else "❌ NOT READY"
            print(f"  {exchange_name}: {status}")
            if result['errors']:
                for error in result['errors']:
                    print(f"    ⚠️ {error}")
        
        # Arbitrage opportunities
        print(f"\n💰 Arbitrage Opportunities: {len(arbitrage_opportunities)}")
        if arbitrage_opportunities:
            for opp in arbitrage_opportunities[:3]:  # Show first 3
                print(f"  {opp['symbol']}: {opp['buy_exchange']} → {opp['sell_exchange']} ({opp['profit_percentage']:.4f}%)")
        
        # Multi-platform scanning
        print(f"\n🔍 Multi-Platform Scanning:")
        print(f"  Exchanges tested: {scan_results['exchanges_tested']}")
        print(f"  Successful scans: {scan_results['successful_scans']}")
        print(f"  Total opportunities: {scan_results['total_opportunities']}")
        
        if scan_results['errors']:
            print(f"  Errors: {len(scan_results['errors'])}")
            for error in scan_results['errors'][:3]:  # Show first 3
                print(f"    ⚠️ {error}")
        
        # Overall status
        print(f"\n🎯 Overall Status:")
        ready_exchanges = sum(1 for result in self.test_results.values() if result['connected'] and result['ticker_fetched'])
        total_exchanges = len(self.test_results)
        
        if ready_exchanges > 0:
            print(f"  ✅ {ready_exchanges}/{total_exchanges} exchanges ready")
            print(f"  ✅ System ready for trading")
            print(f"  ✅ Multi-platform scanning operational")
        else:
            print(f"  ❌ No exchanges ready")
            print(f"  ⚠️ System running in simulation mode")
            print(f"  💡 Configure API keys to enable real trading")
        
        print(f"\n🚀 Next Steps:")
        if ready_exchanges == 0:
            print(f"  1. Set up exchange accounts")
            print(f"  2. Configure API keys in api_config.json")
            print(f"  3. Run this test again")
            print(f"  4. Start paper trading")
        else:
            print(f"  1. Start paper trading: ./start_bot.sh")
            print(f"  2. Monitor performance: ./monitor_bot.sh")
            print(f"  3. Enable live trading when ready")

async def main():
    """Main test function"""
    tester = APITester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())