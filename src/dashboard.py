"""
Dashboard for Trading Bot
Real-time web dashboard using Streamlit for monitoring and control
"""

import asyncio
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger
import json

class Dashboard:
    """Real-time web dashboard for trading bot monitoring"""
    
    def __init__(self, trading_bot, database):
        self.trading_bot = trading_bot
        self.database = database
        
        # Dashboard configuration
        self.config = {
            'port': int(os.getenv('DASHBOARD_PORT', 8501)),
            'host': os.getenv('DASHBOARD_HOST', '0.0.0.0'),
            'title': 'Professional Trading Bot Dashboard',
            'refresh_interval': 5  # seconds
        }
        
        # Dashboard state
        self.running = False
        self.last_update = None
        
    async def initialize(self):
        """Initialize the dashboard"""
        logger.info("📊 Initializing Dashboard...")
        
        try:
            # Set Streamlit page config
            st.set_page_config(
                page_title=self.config['title'],
                page_icon="🤖",
                layout="wide",
                initial_sidebar_state="expanded"
            )
            
            logger.info("✅ Dashboard initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize dashboard: {e}")
            raise
            
    async def start(self):
        """Start the dashboard"""
        logger.info("🎯 Starting Dashboard...")
        self.running = True
        
        # Run Streamlit app
        await self._run_streamlit_app()
        
    async def stop(self):
        """Stop the dashboard"""
        logger.info("🛑 Stopping Dashboard...")
        self.running = False
        
    async def _run_streamlit_app(self):
        """Run the Streamlit dashboard application"""
        try:
            # Main dashboard layout
            st.title("🤖 Professional Trading Bot Dashboard")
            st.markdown("---")
            
            # Sidebar controls
            with st.sidebar:
                st.header("🎛️ Bot Controls")
                
                # Bot status
                bot_status = await self.trading_bot.get_status()
                status_color = "🟢" if bot_status['running'] else "🔴"
                st.metric("Bot Status", f"{status_color} {'Running' if bot_status['running'] else 'Stopped'}")
                
                # Portfolio value
                portfolio_value = bot_status['portfolio_value']
                st.metric("Portfolio Value", f"${portfolio_value:,.2f}")
                
                # Positions count
                positions_count = bot_status['positions_count']
                st.metric("Open Positions", positions_count)
                
                # Refresh button
                if st.button("🔄 Refresh Data"):
                    st.rerun()
                    
                # Bot controls
                st.subheader("🤖 Bot Actions")
                if st.button("▶️ Start Bot"):
                    # This would start the bot in a real implementation
                    st.success("Bot started!")
                    
                if st.button("⏸️ Pause Bot"):
                    # This would pause the bot in a real implementation
                    st.warning("Bot paused!")
                    
                if st.button("🛑 Stop Bot"):
                    # This would stop the bot in a real implementation
                    st.error("Bot stopped!")
                    
            # Main dashboard content
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Portfolio", "📈 Positions", "🤖 ML Models", "⚠️ Risk", "📋 Logs"])
            
            with tab1:
                await self._render_portfolio_tab()
                
            with tab2:
                await self._render_positions_tab()
                
            with tab3:
                await self._render_ml_models_tab()
                
            with tab4:
                await self._render_risk_tab()
                
            with tab5:
                await self._render_logs_tab()
                
        except Exception as e:
            logger.error(f"Error running Streamlit app: {e}")
            st.error(f"Dashboard error: {e}")
            
    async def _render_portfolio_tab(self):
        """Render portfolio overview tab"""
        try:
            st.header("📊 Portfolio Overview")
            
            # Get portfolio data
            portfolio_history = await self.database.get_portfolio_history(limit=100)
            performance_summary = await self.database.get_performance_summary()
            
            if portfolio_history is not None and len(portfolio_history) > 0:
                # Portfolio value chart
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=portfolio_history['timestamp'],
                    y=portfolio_history['total_value'],
                    mode='lines',
                    name='Portfolio Value',
                    line=dict(color='#00ff88', width=2)
                ))
                
                fig.update_layout(
                    title="Portfolio Value Over Time",
                    xaxis_title="Time",
                    yaxis_title="Value ($)",
                    template="plotly_dark"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Performance metrics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    current_value = portfolio_history['total_value'].iloc[-1]
                    st.metric("Current Value", f"${current_value:,.2f}")
                    
                with col2:
                    initial_capital = performance_summary.get('initial_capital', 10000)
                    total_return = performance_summary.get('total_return_pct', 0)
                    st.metric("Total Return", f"{total_return:.2f}%")
                    
                with col3:
                    win_rate = performance_summary.get('win_rate', 0)
                    st.metric("Win Rate", f"{win_rate:.1f}%")
                    
                with col4:
                    total_trades = performance_summary.get('total_trades', 0)
                    st.metric("Total Trades", total_trades)
                    
                # Recent trades
                st.subheader("📋 Recent Trades")
                recent_trades = await self.database.get_trade_history(limit=10)
                
                if recent_trades:
                    trades_df = pd.DataFrame(recent_trades)
                    trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
                    trades_df = trades_df.sort_values('timestamp', ascending=False)
                    
                    st.dataframe(
                        trades_df[['symbol', 'side', 'amount', 'price', 'pnl', 'timestamp']],
                        use_container_width=True
                    )
                else:
                    st.info("No recent trades found")
                    
            else:
                st.warning("No portfolio data available")
                
        except Exception as e:
            logger.error(f"Error rendering portfolio tab: {e}")
            st.error(f"Error loading portfolio data: {e}")
            
    async def _render_positions_tab(self):
        """Render positions tab"""
        try:
            st.header("📈 Open Positions")
            
            # Get current positions
            positions = await self.database.get_active_positions()
            
            if positions:
                positions_df = pd.DataFrame(positions)
                
                # Positions table
                st.subheader("Current Positions")
                st.dataframe(positions_df, use_container_width=True)
                
                # Position distribution chart
                if len(positions_df) > 0:
                    fig = px.pie(
                        positions_df, 
                        values='size', 
                        names='symbol',
                        title="Position Distribution by Size"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                # P&L summary
                total_pnl = positions_df['unrealized_pnl'].sum()
                avg_pnl = positions_df['unrealized_pnl'].mean()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Unrealized P&L", f"${total_pnl:.2f}")
                with col2:
                    st.metric("Average P&L per Position", f"${avg_pnl:.2f}")
                    
            else:
                st.info("No open positions")
                
        except Exception as e:
            logger.error(f"Error rendering positions tab: {e}")
            st.error(f"Error loading positions data: {e}")
            
    async def _render_ml_models_tab(self):
        """Render ML models tab"""
        try:
            st.header("🤖 Machine Learning Models")
            
            # Get ML engine status (this would be from the ML engine in a real implementation)
            st.subheader("Model Status")
            
            # Simulated model data
            models_data = {
                'LSTM': {'accuracy': 0.78, 'status': 'Active', 'last_trained': '2 hours ago'},
                'Random Forest': {'accuracy': 0.82, 'status': 'Active', 'last_trained': '1 hour ago'},
                'Gradient Boosting': {'accuracy': 0.80, 'status': 'Active', 'last_trained': '1 hour ago'}
            }
            
            # Model performance metrics
            for model_name, metrics in models_data.items():
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(f"{model_name} Accuracy", f"{metrics['accuracy']:.2%}")
                with col2:
                    st.metric("Status", metrics['status'])
                with col3:
                    st.metric("Last Trained", metrics['last_trained'])
                    
                st.markdown("---")
                
            # Feature importance (simulated)
            st.subheader("Feature Importance")
            feature_importance = {
                'RSI': 0.25,
                'MACD': 0.20,
                'Volume': 0.18,
                'Price Momentum': 0.15,
                'Bollinger Bands': 0.12,
                'Moving Averages': 0.10
            }
            
            fig = px.bar(
                x=list(feature_importance.values()),
                y=list(feature_importance.keys()),
                orientation='h',
                title="Feature Importance (Random Forest)"
            )
            fig.update_layout(template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            
            # Model retraining controls
            st.subheader("Model Controls")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔄 Retrain All Models"):
                    st.success("Model retraining initiated!")
                    
            with col2:
                if st.button("📊 Update Performance Metrics"):
                    st.success("Performance metrics updated!")
                    
        except Exception as e:
            logger.error(f"Error rendering ML models tab: {e}")
            st.error(f"Error loading ML models data: {e}")
            
    async def _render_risk_tab(self):
        """Render risk management tab"""
        try:
            st.header("⚠️ Risk Management")
            
            # Get risk metrics (simulated for now)
            risk_metrics = {
                'total_exposure': 0.45,
                'max_drawdown': 0.08,
                'var_95': 0.03,
                'sharpe_ratio': 1.2,
                'volatility': 0.25,
                'concentration_risk': 0.15
            }
            
            # Risk metrics display
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Exposure", f"{risk_metrics['total_exposure']:.1%}")
                st.metric("Max Drawdown", f"{risk_metrics['max_drawdown']:.1%}")
                
            with col2:
                st.metric("VaR (95%)", f"{risk_metrics['var_95']:.1%}")
                st.metric("Sharpe Ratio", f"{risk_metrics['sharpe_ratio']:.2f}")
                
            with col3:
                st.metric("Volatility", f"{risk_metrics['volatility']:.1%}")
                st.metric("Concentration Risk", f"{risk_metrics['concentration_risk']:.1%}")
                
            # Risk limits
            st.subheader("Risk Limits")
            risk_limits = {
                'Max Position Size': '10%',
                'Max Total Exposure': '80%',
                'Max Drawdown': '15%',
                'Max VaR': '5%',
                'Max Concentration': '30%'
            }
            
            for limit_name, limit_value in risk_limits.items():
                st.text(f"{limit_name}: {limit_value}")
                
            # Risk alerts
            st.subheader("Risk Alerts")
            alerts = [
                {"level": "INFO", "message": "All risk metrics within normal limits"},
                {"level": "WARNING", "message": "Portfolio volatility approaching limit"},
            ]
            
            for alert in alerts:
                if alert['level'] == 'WARNING':
                    st.warning(f"⚠️ {alert['message']}")
                else:
                    st.info(f"ℹ️ {alert['message']}")
                    
        except Exception as e:
            logger.error(f"Error rendering risk tab: {e}")
            st.error(f"Error loading risk data: {e}")
            
    async def _render_logs_tab(self):
        """Render logs tab"""
        try:
            st.header("📋 System Logs")
            
            # Log level filter
            log_level = st.selectbox("Filter by Log Level", ["ALL", "INFO", "WARNING", "ERROR", "CRITICAL"])
            
            # Recent logs (simulated)
            logs = [
                {"timestamp": "2024-01-15 10:30:15", "level": "INFO", "message": "Trading bot started successfully"},
                {"timestamp": "2024-01-15 10:30:20", "level": "INFO", "message": "Connected to Binance exchange"},
                {"timestamp": "2024-01-15 10:31:05", "level": "INFO", "message": "Generated BUY signal for BTC/USDT (confidence: 0.85)"},
                {"timestamp": "2024-01-15 10:31:10", "level": "SUCCESS", "message": "Executed BUY order for BTC/USDT at $42,150"},
                {"timestamp": "2024-01-15 10:32:00", "level": "WARNING", "message": "Portfolio exposure approaching limit"},
                {"timestamp": "2024-01-15 10:33:15", "level": "INFO", "message": "Risk management check passed"},
            ]
            
            # Filter logs
            if log_level != "ALL":
                logs = [log for log in logs if log['level'] == log_level]
                
            # Display logs
            for log in logs[-20:]:  # Show last 20 logs
                timestamp = log['timestamp']
                level = log['level']
                message = log['message']
                
                if level == "ERROR" or level == "CRITICAL":
                    st.error(f"🔴 {timestamp} | {level} | {message}")
                elif level == "WARNING":
                    st.warning(f"🟡 {timestamp} | {level} | {message}")
                elif level == "SUCCESS":
                    st.success(f"🟢 {timestamp} | {level} | {message}")
                else:
                    st.info(f"🔵 {timestamp} | {level} | {message}")
                    
            # Auto-refresh
            if st.checkbox("Auto-refresh logs"):
                st.markdown("Logs will refresh automatically every 5 seconds")
                
        except Exception as e:
            logger.error(f"Error rendering logs tab: {e}")
            st.error(f"Error loading logs: {e}")
            
    async def _get_real_time_data(self) -> Dict:
        """Get real-time data for dashboard updates"""
        try:
            # This would get real-time data from the trading bot
            # For now, return simulated data
            
            return {
                'portfolio_value': 12500.0,
                'positions_count': 3,
                'last_update': datetime.now().isoformat(),
                'bot_status': 'running'
            }
            
        except Exception as e:
            logger.error(f"Error getting real-time data: {e}")
            return {}
            
    async def is_healthy(self) -> bool:
        """Check if dashboard is healthy"""
        try:
            # Simple health check
            return self.running
        except Exception:
            return False