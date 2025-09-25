#!/usr/bin/env python3
"""
Standalone Dashboard Application
Run this to start the trading bot dashboard
"""

import streamlit as st
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from src.dashboard import Dashboard
from src.database import Database

# Mock trading bot for dashboard
class MockTradingBot:
    def __init__(self):
        self.running = True
        
    async def get_status(self):
        return {
            'running': True,
            'portfolio_value': 12500.0,
            'positions_count': 3,
            'available_capital': 5000.0,
            'positions': []
        }

async def main():
    """Main dashboard application"""
    try:
        # Initialize components
        database = Database()
        await database.initialize()
        
        trading_bot = MockTradingBot()
        
        # Initialize dashboard
        dashboard = Dashboard(trading_bot, database)
        await dashboard.initialize()
        
        # Run dashboard
        await dashboard._run_streamlit_app()
        
    except Exception as e:
        st.error(f"Dashboard error: {e}")

if __name__ == "__main__":
    asyncio.run(main())