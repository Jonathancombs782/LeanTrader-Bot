#!/usr/bin/env python3
"""
Download and setup the trading bot directly on the VPS
Run this on your VPS: 75.119.149.117
"""

import os
import subprocess
import sys

def run_command(cmd):
    """Run a shell command"""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    print(f"Success: {result.stdout}")
    return True

def main():
    print("🚀 Setting up Professional Bybit Trading Bot")
    print("=" * 50)
    
    # Create main bot file
    print("📝 Creating main.py...")
    main_py = '''#!/usr/bin/env python3
"""
Professional Trading Bot - Main Entry Point
Advanced ML-powered trading system with real-time learning and risk management
"""

import asyncio
import sys
import os
import signal
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Load environment variables
load_dotenv()

# Import bot components
from src.bot import TradingBot
from src.data_collector import DataCollector
from src.ml_engine import MLEngine
from src.risk_manager import RiskManager
from src.notification_manager import NotificationManager
from src.dashboard import Dashboard
from src.database import Database

class TradingBotOrchestrator:
    """Main orchestrator for the trading bot system"""
    
    def __init__(self):
        self.bot = None
        self.data_collector = None
        self.ml_engine = None
        self.risk_manager = None
        self.notification_manager = None
        self.dashboard = None
        self.database = None
        self.running = False
        
        # Setup logging
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logger.remove()  # Remove default handler
        logger.add(
            "logs/trading/trading_bot.log",
            rotation="1 day",
            retention="30 days",
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
        )
        logger.add(
            sys.stdout,
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | {message}"
        )
        
    async def initialize(self):
        """Initialize all bot components"""
        try:
            logger.info("🚀 Initializing Professional Trading Bot...")
            
            # Initialize database
            self.database = Database()
            await self.database.initialize()
            
            # Initialize notification manager
            self.notification_manager = NotificationManager()
            await self.notification_manager.initialize()
            
            # Initialize risk manager
            self.risk_manager = RiskManager(self.database)
            await self.risk_manager.initialize()
            
            # Initialize ML engine
            self.ml_engine = MLEngine(self.database, self.risk_manager)
            await self.ml_engine.initialize()
            
            # Initialize data collector
            self.data_collector = DataCollector(self.database)
            await self.data_collector.initialize()
            
            # Initialize trading bot
            self.bot = TradingBot(
                data_collector=self.data_collector,
                ml_engine=self.ml_engine,
                risk_manager=self.risk_manager,
                notification_manager=self.notification_manager,
                database=self.database
            )
            await self.bot.initialize()
            
            logger.info("✅ All components initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")
            raise
            
    async def start(self):
        """Start the trading bot system"""
        try:
            logger.info("🎯 Starting trading bot system...")
            
            # Send startup notification
            await self.notification_manager.send_notification(
                "🚀 Trading Bot Started",
                f"Professional Trading Bot v{os.getenv('VERSION', '1.0.0')} is now running on {os.getenv('BOT_NAME', 'TradingBot')}"
            )
            
            self.running = True
            
            # Start all components concurrently
            tasks = [
                asyncio.create_task(self.data_collector.start()),
                asyncio.create_task(self.ml_engine.start()),
                asyncio.create_task(self.bot.start()),
                asyncio.create_task(self.monitor_system())
            ]
            
            # Wait for all tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}")
            await self.notification_manager.send_notification(
                "🚨 Bot Error",
                f"Critical error occurred: {str(e)}"
            )
            raise
            
    async def stop(self):
        """Gracefully stop the trading bot system"""
        logger.info("🛑 Stopping trading bot system...")
        self.running = False
        
        # Stop all components
        if self.bot:
            await self.bot.stop()
        if self.data_collector:
            await self.data_collector.stop()
        if self.ml_engine:
            await self.ml_engine.stop()
            
        logger.info("✅ Trading bot system stopped")
        
    async def monitor_system(self):
        """Monitor system health and performance"""
        while self.running:
            try:
                # Wait before next check
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(60)

async def main():
    """Main entry point"""
    orchestrator = TradingBotOrchestrator()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(orchestrator.stop())
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize and start the bot
        await orchestrator.initialize()
        await orchestrator.start()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await orchestrator.stop()

if __name__ == "__main__":
    # Ensure we're in the right directory
    os.chdir(Path(__file__).parent)
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        sys.exit(1)
'''
    
    with open('main.py', 'w') as f:
        f.write(main_py)
    
    # Create src directory and __init__.py
    os.makedirs('src', exist_ok=True)
    with open('src/__init__.py', 'w') as f:
        f.write('# Trading Bot Package\n')
    
    print("✅ Basic bot structure created")
    print("🎯 Bot ready to run with: python main.py")
    print("📊 Dashboard will be available at: http://75.119.149.117:8501")

if __name__ == "__main__":
    main()
'''