#!/usr/bin/env python3
"""
ULTRA LAUNCHER - The Ultimate Self-Evolving Trading System

This is the main entry point for running the most brilliant algorithmic
trading system ever created. It evolves, learns, and adapts in real-time.
"""

import os
import sys
import asyncio
import argparse
import json
import signal
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add paths for imports
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent / "tools"))

# Import our ultra components
from ultra_ml_pipeline import get_ultra_pipeline, UltraMLPipeline
from tools.ultra_trainer import train_ultra_model, get_ultra_prediction
from tools.market_data import get_market_data_manager

# ASCII Art Banner
BANNER = """
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║   ██╗   ██╗██╗  ████████╗██████╗  █████╗     ████████╗██████╗  █████╗    ║
║   ██║   ██║██║  ╚══██╔══╝██╔══██╗██╔══██╗    ╚══██╔══╝██╔══██╗██╔══██╗   ║
║   ██║   ██║██║     ██║   ██████╔╝███████║       ██║   ██████╔╝███████║   ║
║   ██║   ██║██║     ██║   ██╔══██╗██╔══██║       ██║   ██╔══██╗██╔══██║   ║
║   ╚██████╔╝███████╗██║   ██║  ██║██║  ██║       ██║   ██║  ██║██║  ██║   ║
║    ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝       ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝   ║
║                                                                            ║
║         THE MOST BRILLIANT SELF-EVOLVING TRADER EVER DESIGNED            ║
║                                                                            ║
║                    🧠 AI-Powered 🚀 Self-Evolving 💎 Ultra-Smart         ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
"""

class UltraLauncher:
    """Main launcher for the Ultra Trading System."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the launcher."""
        self.config = self._load_config(config_path)
        self.pipeline = None
        self.running = False
        self.start_time = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        default_config = {
            'mode': 'live',  # 'live', 'paper', 'backtest'
            'symbols': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
            'timeframes': ['1m', '5m', '15m', '1h'],
            'exchange': 'binance',
            'max_positions': 5,
            'risk_per_trade': 0.02,
            'confidence_threshold': 0.65,
            'evolution_enabled': True,
            'online_learning': True,
            'multi_exchange': False,
            'use_news_sentiment': True,
            'use_onchain_data': True,
            'model_update_interval': 86400,  # Daily
            'rebalance_interval': 3600,  # Hourly
            'initial_capital': 10000,
            'stop_loss_pct': 0.05,
            'take_profit_pct': 0.10,
            'max_drawdown_pct': 0.20,
            'telegram_notifications': False,
            'discord_webhook': None,
            'log_level': 'INFO'
        }
        
        if config_path and Path(config_path).exists():
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                print(f"✅ Loaded config from {config_path}")
            except Exception as e:
                print(f"⚠️ Failed to load config: {e}, using defaults")
        
        return default_config
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print("\n🛑 Shutdown signal received, stopping gracefully...")
        self.stop()
        sys.exit(0)
    
    async def train_models(self):
        """Train initial models for all configured symbols."""
        print("\n🎯 Training Ultra Models...")
        print("=" * 60)
        
        results = {}
        for symbol in self.config['symbols']:
            print(f"\n📊 Training model for {symbol}...")
            try:
                result = train_ultra_model(
                    symbol=symbol,
                    timeframe=self.config['timeframes'][1],  # Use 5m as default
                    days=30
                )
                
                if 'error' not in result:
                    print(f"✅ {symbol}: Accuracy={result.get('accuracy', 'N/A'):.2%}")
                    results[symbol] = result
                else:
                    print(f"❌ {symbol}: {result['error']}")
                    
            except Exception as e:
                print(f"❌ Failed to train {symbol}: {e}")
        
        print("\n" + "=" * 60)
        print(f"✅ Training complete! Trained {len(results)}/{len(self.config['symbols'])} models")
        return results
    
    async def run_backtest(self):
        """Run backtest mode."""
        print("\n📈 Running Backtest Mode...")
        print("=" * 60)
        
        # Train models first
        await self.train_models()
        
        # Run backtest simulation
        from ultra_scout import UltraScout
        scout = UltraScout()
        
        backtest_results = {}
        for symbol in self.config['symbols']:
            print(f"\n🔄 Backtesting {symbol}...")
            
            # Run backtest
            result = scout.run_backtest(
                strategy='trend',
                params={
                    'symbol': symbol,
                    'timeframe': '5m',
                    'risk_per_trade': self.config['risk_per_trade']
                }
            )
            
            backtest_results[symbol] = result
            
            # Display results
            print(f"  Total Return: {result.get('total_return', 0):.2%}")
            print(f"  Sharpe Ratio: {result.get('sharpe_ratio', 0):.2f}")
            print(f"  Max Drawdown: {result.get('max_drawdown', 0):.2%}")
            print(f"  Win Rate: {result.get('win_rate', 0):.2%}")
        
        print("\n" + "=" * 60)
        print("✅ Backtest complete!")
        
        # Save results
        results_path = Path("reports") / f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_path.parent.mkdir(exist_ok=True)
        with open(results_path, 'w') as f:
            json.dump(backtest_results, f, indent=2, default=str)
        print(f"📊 Results saved to {results_path}")
    
    async def run_paper(self):
        """Run paper trading mode."""
        print("\n📝 Running Paper Trading Mode...")
        print("=" * 60)
        print("⚠️ This is a simulated environment - no real trades will be executed")
        
        # Override config for paper trading
        self.config['mode'] = 'paper'
        
        # Initialize pipeline
        self.pipeline = get_ultra_pipeline(self.config)
        
        # Run pipeline
        await self.pipeline.run_forever()
    
    async def run_live(self):
        """Run live trading mode."""
        print("\n💰 Running LIVE Trading Mode...")
        print("=" * 60)
        print("⚠️ WARNING: This will execute REAL trades with REAL money!")
        print("=" * 60)
        
        # Confirmation
        confirm = input("\n⚠️ Are you sure you want to run LIVE trading? (type 'YES' to confirm): ")
        if confirm != 'YES':
            print("❌ Live trading cancelled")
            return
        
        print("\n✅ Live trading confirmed, starting system...")
        
        # Initialize pipeline
        self.pipeline = get_ultra_pipeline(self.config)
        
        # Run pipeline
        await self.pipeline.run_forever()
    
    async def monitor_performance(self):
        """Monitor system performance in real-time."""
        while self.running:
            try:
                if self.pipeline:
                    status = self.pipeline.get_status()
                    
                    # Clear screen (optional)
                    # os.system('cls' if os.name == 'nt' else 'clear')
                    
                    print("\n" + "=" * 60)
                    print(f"📊 ULTRA TRADING SYSTEM STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print("=" * 60)
                    
                    # Display metrics
                    metrics = status.get('metrics', {})
                    print(f"📈 Performance Metrics:")
                    print(f"  • Total Trades: {metrics.get('total_trades', 0)}")
                    print(f"  • Win Rate: {metrics.get('win_rate', 0):.2%}")
                    print(f"  • Total PnL: {metrics.get('total_pnl', 0):.2%}")
                    print(f"  • Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
                    print(f"  • Max Drawdown: {metrics.get('max_drawdown', 0):.2%}")
                    
                    # Display evolution status
                    evolution = status.get('evolution', {})
                    print(f"\n🧬 Evolution Status:")
                    print(f"  • Generation: {evolution.get('generation', 0)}")
                    print(f"  • Fitness: {evolution.get('fitness', 0):.2%}")
                    print(f"  • Mutations: {len(evolution.get('mutations', []))}")
                    
                    # Display positions
                    print(f"\n💼 Active Positions: {status.get('active_positions', 0)}/{self.config['max_positions']}")
                    
                    # Runtime
                    if self.start_time:
                        runtime = datetime.now() - self.start_time
                        print(f"\n⏱️ Runtime: {runtime}")
                
                await asyncio.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                print(f"Monitor error: {e}")
                await asyncio.sleep(60)
    
    async def start(self, mode: str = None):
        """Start the Ultra Trading System."""
        print(BANNER)
        
        self.running = True
        self.start_time = datetime.now()
        
        # Override mode if provided
        if mode:
            self.config['mode'] = mode
        
        print(f"🚀 Starting Ultra Trading System in {self.config['mode'].upper()} mode...")
        print(f"📊 Symbols: {', '.join(self.config['symbols'])}")
        print(f"⏰ Timeframes: {', '.join(self.config['timeframes'])}")
        print(f"💰 Risk per trade: {self.config['risk_per_trade']:.1%}")
        print(f"🧬 Evolution: {'Enabled' if self.config['evolution_enabled'] else 'Disabled'}")
        print(f"📚 Online Learning: {'Enabled' if self.config['online_learning'] else 'Disabled'}")
        
        # Start monitoring task
        monitor_task = asyncio.create_task(self.monitor_performance())
        
        try:
            # Run based on mode
            if self.config['mode'] == 'backtest':
                await self.run_backtest()
            elif self.config['mode'] == 'paper':
                await self.run_paper()
            elif self.config['mode'] == 'live':
                await self.run_live()
            else:
                print(f"❌ Unknown mode: {self.config['mode']}")
        
        finally:
            self.running = False
            monitor_task.cancel()
    
    def stop(self):
        """Stop the system."""
        self.running = False
        if self.pipeline:
            self.pipeline.stop()
        print("✅ System stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Ultra Trading System - The Most Brilliant Self-Evolving Trader'
    )
    
    parser.add_argument(
        '--mode',
        choices=['live', 'paper', 'backtest'],
        default='paper',
        help='Trading mode (default: paper)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file (JSON)'
    )
    
    parser.add_argument(
        '--symbols',
        nargs='+',
        help='Trading symbols (e.g., BTC/USDT ETH/USDT)'
    )
    
    parser.add_argument(
        '--train',
        action='store_true',
        help='Train models before starting'
    )
    
    parser.add_argument(
        '--risk',
        type=float,
        default=0.02,
        help='Risk per trade (default: 0.02 = 2%%)'
    )
    
    parser.add_argument(
        '--evolution',
        action='store_true',
        default=True,
        help='Enable evolution and adaptation'
    )
    
    args = parser.parse_args()
    
    # Create launcher
    launcher = UltraLauncher(args.config)
    
    # Override config with command line args
    if args.symbols:
        launcher.config['symbols'] = args.symbols
    launcher.config['risk_per_trade'] = args.risk
    launcher.config['evolution_enabled'] = args.evolution
    
    # Run async main
    async def async_main():
        try:
            # Train if requested
            if args.train:
                await launcher.train_models()
            
            # Start system
            await launcher.start(args.mode)
            
        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            launcher.stop()
    
    # Run
    asyncio.run(async_main())


if __name__ == "__main__":
    main()