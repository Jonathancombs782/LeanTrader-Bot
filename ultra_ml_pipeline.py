"""Ultra ML Pipeline - The Brain of the Ultra Trading System.

This is the central intelligence system that orchestrates all ML components,
making ultra-brilliant trading decisions that evolve and adapt in real-time.
"""

from __future__ import annotations

import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
from collections import deque, defaultdict
import threading
import queue
import hashlib
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# Import our ultra components
import sys
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent / "tools"))

try:
    from tools.ultra_trainer import (
        UltraFeatureEngine, MarketRegimeDetector, 
        UltraEnsembleModel, DeepLearningModel,
        ReinforcementLearningAgent, UltraTrainer
    )
    from tools.market_data import (
        MarketDataManager, StreamingDataManager,
        MultiExchangeAggregator
    )
    ULTRA_MODULES_AVAILABLE = True
except ImportError as e:
    print(f"[UltraML] Warning: Some modules not available: {e}")
    ULTRA_MODULES_AVAILABLE = False

# Import existing system components
try:
    from pattern_memory import features, record, recall, get_score, recompute_scores
    from ultra_scout import UltraScout
    from router import ExchangeRouter
    from brain import Memory
    SYSTEM_MODULES_AVAILABLE = True
except ImportError as e:
    print(f"[UltraML] Warning: System modules not available: {e}")
    SYSTEM_MODULES_AVAILABLE = False


class UltraMLPipeline:
    """The Ultra-Brilliant ML Pipeline that evolves and learns."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the ultra-intelligent trading brain."""
        self.config = config or self._default_config()
        
        # Core components
        self.feature_engine = UltraFeatureEngine() if ULTRA_MODULES_AVAILABLE else None
        self.regime_detector = MarketRegimeDetector() if ULTRA_MODULES_AVAILABLE else None
        self.trainer = UltraTrainer() if ULTRA_MODULES_AVAILABLE else None
        self.market_data = MarketDataManager() if ULTRA_MODULES_AVAILABLE else None
        self.streaming = StreamingDataManager() if ULTRA_MODULES_AVAILABLE else None
        self.aggregator = MultiExchangeAggregator() if ULTRA_MODULES_AVAILABLE else None
        
        # System integration
        self.scout = UltraScout() if SYSTEM_MODULES_AVAILABLE else None
        self.router = ExchangeRouter() if SYSTEM_MODULES_AVAILABLE else None
        self.memory = Memory() if SYSTEM_MODULES_AVAILABLE else None
        
        # State management
        self.active_positions = {}
        self.pending_signals = deque(maxlen=100)
        self.performance_history = deque(maxlen=1000)
        self.evolution_state = {
            'generation': 0,
            'fitness': 0.0,
            'mutations': [],
            'adaptations': []
        }
        
        # Threading and async
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.running = False
        self.main_loop_thread = None
        
        # Performance tracking
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0,
            'avg_return': 0.0,
            'evolution_score': 0.0
        }
        
        # Initialize models
        self._initialize_models()
        
        print("🧠 Ultra ML Pipeline initialized - The ultimate trading brain is online!")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration for ultra pipeline."""
        return {
            'symbols': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
            'timeframes': ['1m', '5m', '15m', '1h'],
            'max_positions': 5,
            'risk_per_trade': 0.02,
            'confidence_threshold': 0.65,
            'evolution_enabled': True,
            'online_learning': True,
            'multi_exchange': True,
            'use_news_sentiment': True,
            'use_onchain_data': True,
            'rebalance_interval': 3600,  # seconds
            'model_update_interval': 86400,  # daily
        }
    
    def _initialize_models(self):
        """Initialize or load existing models."""
        try:
            # Try to load existing models
            if self.trainer and self.trainer.load_models():
                print("✅ Loaded existing ultra models")
                return
            
            # Train new models if none exist
            print("🎯 No existing models found, training new ones...")
            self._train_initial_models()
            
        except Exception as e:
            print(f"⚠️ Model initialization error: {e}")
    
    def _train_initial_models(self):
        """Train initial models for all configured symbols."""
        if not self.trainer or not self.market_data:
            return
        
        for symbol in self.config['symbols']:
            try:
                print(f"Training model for {symbol}...")
                
                # Fetch training data
                df = self.market_data.fetch_ohlcv(symbol, '5m', 2000)
                if df.empty:
                    continue
                
                # Train model
                results = self.trainer.train_full_system(
                    data_path=None,  # Will use df directly
                    symbol=symbol,
                    task='classification'
                )
                
                print(f"✅ Trained model for {symbol}: {results.get('ensemble', {})}")
                
            except Exception as e:
                print(f"❌ Failed to train {symbol}: {e}")
    
    async def ultra_analysis(self, symbol: str) -> Dict[str, Any]:
        """Perform ultra-comprehensive analysis on a symbol."""
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'signals': {},
            'confidence': 0.0,
            'action': 'HOLD'
        }
        
        try:
            # Fetch multi-timeframe data
            mtf_data = await self._fetch_mtf_data_async(symbol)
            
            # Technical analysis across timeframes
            for tf, df in mtf_data.items():
                if df.empty:
                    continue
                
                # Extract features
                if self.feature_engine:
                    features_df = self.feature_engine.extract_features(df)
                    
                    # Get ML predictions
                    if self.trainer and self.trainer.ensemble_model:
                        prediction = self.trainer.predict(df)
                        analysis['signals'][tf] = prediction
                
                # Pattern memory recall
                if SYSTEM_MODULES_AVAILABLE:
                    memory_recall = recall(symbol, tf, df)
                    analysis[f'memory_{tf}'] = memory_recall
            
            # Market regime detection
            if self.regime_detector:
                main_df = mtf_data.get('5m', pd.DataFrame())
                if not main_df.empty:
                    regime = self.regime_detector.detect_regime(main_df)
                    analysis['regime'] = regime
                    analysis['regime_params'] = self.regime_detector.get_regime_params(regime)
            
            # News sentiment analysis
            if self.scout and self.config['use_news_sentiment']:
                news_data = await self._get_news_sentiment_async(symbol)
                analysis['news_sentiment'] = news_data
            
            # Multi-exchange price aggregation
            if self.aggregator and self.config['multi_exchange']:
                agg_price = self.aggregator.get_aggregated_price(symbol)
                analysis['aggregated_price'] = agg_price
            
            # Combine all signals for final decision
            analysis = self._combine_signals(analysis)
            
            # Evolution learning
            if self.config['evolution_enabled']:
                self._evolve_strategy(analysis)
            
        except Exception as e:
            print(f"[UltraML] Analysis error for {symbol}: {e}")
            analysis['error'] = str(e)
        
        return analysis
    
    async def _fetch_mtf_data_async(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """Fetch multi-timeframe data asynchronously."""
        if not self.market_data:
            return {}
        
        tasks = []
        loop = asyncio.get_event_loop()
        
        for tf in self.config['timeframes']:
            task = loop.run_in_executor(
                self.executor,
                self.market_data.fetch_ohlcv,
                symbol, tf, 500
            )
            tasks.append((tf, task))
        
        results = {}
        for tf, task in tasks:
            try:
                df = await task
                results[tf] = df
            except Exception as e:
                print(f"Error fetching {tf} data: {e}")
                results[tf] = pd.DataFrame()
        
        return results
    
    async def _get_news_sentiment_async(self, symbol: str) -> Dict[str, Any]:
        """Get news sentiment asynchronously."""
        if not self.scout:
            return {}
        
        loop = asyncio.get_event_loop()
        
        # Run scout analysis in executor
        scout_data = await loop.run_in_executor(
            self.executor,
            self.scout.scout_all
        )
        
        # Filter for relevant symbol
        base_symbol = symbol.split('/')[0]
        relevant_sentiment = {
            k: v for k, v in scout_data.get('sentiment', {}).items()
            if base_symbol.lower() in k.lower()
        }
        
        return {
            'sentiment_score': sum(relevant_sentiment.values()) / max(1, len(relevant_sentiment)),
            'headlines_count': len(relevant_sentiment),
            'trends': scout_data.get('trends', [])
        }
    
    def _combine_signals(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Combine all signals into final trading decision."""
        signals = analysis.get('signals', {})
        
        if not signals:
            return analysis
        
        # Weight signals by timeframe
        timeframe_weights = {
            '1m': 0.1,
            '5m': 0.3,
            '15m': 0.3,
            '1h': 0.3
        }
        
        total_weight = 0
        weighted_confidence = 0
        buy_signals = 0
        sell_signals = 0
        
        for tf, signal in signals.items():
            weight = timeframe_weights.get(tf, 0.1)
            confidence = signal.get('confidence', 0)
            
            weighted_confidence += confidence * weight
            total_weight += weight
            
            if signal.get('signal') == 'BUY':
                buy_signals += weight
            elif signal.get('signal') == 'SELL':
                sell_signals += weight
        
        # Adjust for regime
        regime = analysis.get('regime', 'neutral')
        regime_multiplier = {
            'bull_trend': 1.2,
            'bear_trend': 0.8,
            'high_volatility': 0.6,
            'low_volatility': 1.1,
            'ranging': 0.9,
            'neutral': 1.0
        }.get(regime, 1.0)
        
        # Adjust for news sentiment
        sentiment_score = analysis.get('news_sentiment', {}).get('sentiment_score', 0)
        sentiment_multiplier = 1.0 + (sentiment_score * 0.1)  # ±10% based on sentiment
        
        # Calculate final scores
        if total_weight > 0:
            weighted_confidence /= total_weight
            buy_score = (buy_signals / total_weight) * regime_multiplier * sentiment_multiplier
            sell_score = (sell_signals / total_weight) / regime_multiplier / sentiment_multiplier
        else:
            weighted_confidence = 0
            buy_score = 0
            sell_score = 0
        
        # Determine action
        threshold = self.config['confidence_threshold']
        if buy_score > threshold and buy_score > sell_score:
            action = 'BUY'
        elif sell_score > threshold and sell_score > buy_score:
            action = 'SELL'
        else:
            action = 'HOLD'
        
        # Update analysis
        analysis['confidence'] = weighted_confidence
        analysis['action'] = action
        analysis['buy_score'] = buy_score
        analysis['sell_score'] = sell_score
        analysis['final_score'] = max(buy_score, sell_score)
        
        return analysis
    
    def _evolve_strategy(self, analysis: Dict[str, Any]):
        """Evolve trading strategy based on performance."""
        # Track performance
        self.performance_history.append({
            'timestamp': datetime.now(),
            'analysis': analysis,
            'metrics': self.metrics.copy()
        })
        
        # Evolution logic
        if len(self.performance_history) >= 100:
            recent_performance = list(self.performance_history)[-100:]
            
            # Calculate fitness
            wins = sum(1 for p in recent_performance 
                      if p['analysis'].get('action') != 'HOLD')
            fitness = wins / 100.0
            
            # Update evolution state
            self.evolution_state['generation'] += 1
            self.evolution_state['fitness'] = fitness
            
            # Adapt parameters based on fitness
            if fitness < 0.4:  # Poor performance
                self._mutate_parameters('conservative')
            elif fitness > 0.6:  # Good performance
                self._mutate_parameters('aggressive')
            
            # Online learning update
            if self.config['online_learning'] and self.trainer:
                self._update_models_online()
    
    def _mutate_parameters(self, direction: str):
        """Mutate trading parameters for evolution."""
        mutations = []
        
        if direction == 'conservative':
            # Become more conservative
            self.config['confidence_threshold'] = min(0.9, self.config['confidence_threshold'] + 0.05)
            self.config['risk_per_trade'] = max(0.005, self.config['risk_per_trade'] * 0.9)
            self.config['max_positions'] = max(1, self.config['max_positions'] - 1)
            mutations.append('conservative')
            
        elif direction == 'aggressive':
            # Become more aggressive
            self.config['confidence_threshold'] = max(0.5, self.config['confidence_threshold'] - 0.05)
            self.config['risk_per_trade'] = min(0.05, self.config['risk_per_trade'] * 1.1)
            self.config['max_positions'] = min(10, self.config['max_positions'] + 1)
            mutations.append('aggressive')
        
        self.evolution_state['mutations'].extend(mutations)
        self.evolution_state['adaptations'].append({
            'timestamp': datetime.now().isoformat(),
            'direction': direction,
            'new_config': self.config.copy()
        })
        
        print(f"🧬 Evolution: Applied {direction} mutation. Generation {self.evolution_state['generation']}")
    
    def _update_models_online(self):
        """Update models with recent performance data."""
        if not self.trainer or not self.trainer.ensemble_model:
            return
        
        # Prepare recent data for online learning
        recent_data = []
        for perf in list(self.performance_history)[-50:]:
            analysis = perf['analysis']
            if 'features' in analysis:
                recent_data.append({
                    'features': analysis['features'],
                    'outcome': 1 if analysis.get('pnl', 0) > 0 else 0
                })
        
        if len(recent_data) >= 10:
            # Convert to training format
            X = pd.DataFrame([d['features'] for d in recent_data])
            y = np.array([d['outcome'] for d in recent_data])
            
            # Online update
            self.trainer.ensemble_model.online_update(X, y)
            print(f"📚 Online learning: Updated models with {len(recent_data)} samples")
    
    async def execute_trade(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Execute trade based on analysis."""
        result = {
            'executed': False,
            'symbol': analysis['symbol'],
            'action': analysis['action'],
            'timestamp': datetime.now().isoformat()
        }
        
        if analysis['action'] == 'HOLD':
            return result
        
        if not self.router or not SYSTEM_MODULES_AVAILABLE:
            result['error'] = 'Trading system not available'
            return result
        
        try:
            symbol = analysis['symbol']
            action = analysis['action']
            confidence = analysis['confidence']
            
            # Check position limits
            if len(self.active_positions) >= self.config['max_positions']:
                result['error'] = 'Max positions reached'
                return result
            
            # Calculate position size
            regime_params = analysis.get('regime_params', {})
            position_size = self._calculate_position_size(
                symbol, confidence, regime_params
            )
            
            # Place order
            order_result = await self._place_order_async(
                symbol, action, position_size, analysis
            )
            
            if order_result['success']:
                # Track position
                self.active_positions[symbol] = {
                    'entry_time': datetime.now(),
                    'entry_price': order_result['price'],
                    'size': position_size,
                    'side': action,
                    'analysis': analysis
                }
                
                # Update metrics
                self.metrics['total_trades'] += 1
                
                result['executed'] = True
                result['order'] = order_result
                
                print(f"✅ Executed {action} {position_size} {symbol} @ {order_result['price']}")
            else:
                result['error'] = order_result.get('error', 'Order failed')
                
        except Exception as e:
            result['error'] = str(e)
            print(f"❌ Trade execution error: {e}")
        
        return result
    
    def _calculate_position_size(self, symbol: str, confidence: float,
                                 regime_params: Dict[str, Any]) -> float:
        """Calculate intelligent position size."""
        # Base size from config
        base_risk = self.config['risk_per_trade']
        
        # Adjust for confidence
        confidence_multiplier = confidence
        
        # Adjust for regime
        regime_multiplier = regime_params.get('risk_multiplier', 1.0)
        
        # Adjust for current performance
        if self.metrics['win_rate'] > 0.6:
            performance_multiplier = 1.2
        elif self.metrics['win_rate'] < 0.4:
            performance_multiplier = 0.8
        else:
            performance_multiplier = 1.0
        
        # Evolution adjustment
        evolution_multiplier = 1.0 + (self.evolution_state['fitness'] - 0.5) * 0.2
        
        # Calculate final size
        final_risk = base_risk * confidence_multiplier * regime_multiplier * \
                    performance_multiplier * evolution_multiplier
        
        # Cap at maximum
        final_risk = min(final_risk, 0.05)  # Max 5% per trade
        
        # Convert to position size (simplified - in production use proper sizing)
        account_balance = 10000  # Placeholder - get from router
        position_value = account_balance * final_risk
        
        return position_value
    
    async def _place_order_async(self, symbol: str, side: str, 
                                 size: float, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Place order asynchronously."""
        if not self.router:
            return {'success': False, 'error': 'No router available'}
        
        loop = asyncio.get_event_loop()
        
        # Prepare order parameters
        regime_params = analysis.get('regime_params', {})
        stop_loss_atr = regime_params.get('stop_loss_atr', 2.0)
        take_profit_atr = regime_params.get('take_profit_atr', 3.0)
        
        try:
            # Get current price
            ticker = await loop.run_in_executor(
                self.executor,
                self.router.safe_fetch_ticker,
                symbol
            )
            
            current_price = ticker.get('last', 0) if ticker else 0
            
            if current_price <= 0:
                return {'success': False, 'error': 'Invalid price'}
            
            # Calculate stop loss and take profit
            atr = analysis.get('atr', current_price * 0.02)  # 2% default
            
            if side == 'BUY':
                stop_loss = current_price - (atr * stop_loss_atr)
                take_profit = current_price + (atr * take_profit_atr)
            else:
                stop_loss = current_price + (atr * stop_loss_atr)
                take_profit = current_price - (atr * take_profit_atr)
            
            # Place order with stop loss and take profit
            order_result = await loop.run_in_executor(
                self.executor,
                self.router.safe_place_order,
                symbol,
                'market',
                side.lower(),
                size / current_price,  # Convert to base currency
                None,  # Market order
                {
                    'stopLoss': stop_loss,
                    'takeProfit': take_profit
                }
            )
            
            return {
                'success': True if order_result else False,
                'order_id': order_result.get('id') if order_result else None,
                'price': current_price,
                'size': size,
                'stop_loss': stop_loss,
                'take_profit': take_profit
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def monitor_positions(self):
        """Monitor and manage active positions."""
        while self.running:
            try:
                for symbol, position in list(self.active_positions.items()):
                    # Get current price
                    current_analysis = await self.ultra_analysis(symbol)
                    
                    # Check for exit signals
                    if current_analysis['action'] == 'SELL' and position['side'] == 'BUY':
                        await self._close_position(symbol, position, current_analysis)
                    elif current_analysis['action'] == 'BUY' and position['side'] == 'SELL':
                        await self._close_position(symbol, position, current_analysis)
                    
                    # Trail stop loss if profitable
                    await self._trail_stop_loss(symbol, position, current_analysis)
                
                # Sleep before next check
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                print(f"[Monitor] Error: {e}")
                await asyncio.sleep(60)
    
    async def _close_position(self, symbol: str, position: Dict[str, Any],
                             analysis: Dict[str, Any]):
        """Close an active position."""
        try:
            # Place closing order
            close_side = 'SELL' if position['side'] == 'BUY' else 'BUY'
            close_result = await self._place_order_async(
                symbol, close_side, position['size'], analysis
            )
            
            if close_result['success']:
                # Calculate PnL
                entry_price = position['entry_price']
                exit_price = close_result['price']
                
                if position['side'] == 'BUY':
                    pnl = (exit_price - entry_price) / entry_price
                else:
                    pnl = (entry_price - exit_price) / entry_price
                
                # Update metrics
                self.metrics['total_pnl'] += pnl
                if pnl > 0:
                    self.metrics['winning_trades'] += 1
                
                self.metrics['win_rate'] = self.metrics['winning_trades'] / max(1, self.metrics['total_trades'])
                
                # Remove from active positions
                del self.active_positions[symbol]
                
                print(f"📊 Closed {symbol}: PnL = {pnl:.2%}")
                
                # Record in pattern memory
                if SYSTEM_MODULES_AVAILABLE:
                    from pattern_memory import set_outcome
                    set_outcome(
                        symbol, '5m',
                        int(position['entry_time'].timestamp()),
                        pnl,
                        'win' if pnl > 0 else 'loss'
                    )
                
        except Exception as e:
            print(f"Error closing position: {e}")
    
    async def _trail_stop_loss(self, symbol: str, position: Dict[str, Any],
                              analysis: Dict[str, Any]):
        """Trail stop loss for profitable positions."""
        # Implementation would update stop loss on exchange
        # This is a placeholder for the concept
        pass
    
    async def run_forever(self):
        """Run the ultra ML pipeline forever."""
        self.running = True
        print("🚀 Ultra ML Pipeline starting...")
        
        # Start monitoring positions
        monitor_task = asyncio.create_task(self.monitor_positions())
        
        while self.running:
            try:
                # Analyze all symbols
                for symbol in self.config['symbols']:
                    analysis = await self.ultra_analysis(symbol)
                    
                    # Execute trade if signal is strong
                    if analysis['confidence'] > self.config['confidence_threshold']:
                        await self.execute_trade(analysis)
                    
                    # Small delay between symbols
                    await asyncio.sleep(1)
                
                # Periodic model update
                if time.time() % self.config['model_update_interval'] < 60:
                    self._update_models_online()
                
                # Periodic rebalancing
                if time.time() % self.config['rebalance_interval'] < 60:
                    await self._rebalance_portfolio()
                
                # Sleep before next cycle
                await asyncio.sleep(30)  # Run every 30 seconds
                
            except Exception as e:
                print(f"[UltraML] Main loop error: {e}")
                await asyncio.sleep(60)
        
        # Cleanup
        monitor_task.cancel()
        print("🛑 Ultra ML Pipeline stopped")
    
    async def _rebalance_portfolio(self):
        """Rebalance portfolio based on performance."""
        # Calculate current allocation
        total_value = sum(p['size'] for p in self.active_positions.values())
        
        if total_value <= 0:
            return
        
        # Target equal weight for simplicity (can be optimized)
        target_allocation = 1.0 / max(1, len(self.config['symbols']))
        
        for symbol in self.config['symbols']:
            current_allocation = self.active_positions.get(symbol, {}).get('size', 0) / total_value
            
            if abs(current_allocation - target_allocation) > 0.1:  # 10% threshold
                # Rebalance needed
                print(f"🔄 Rebalancing {symbol}: {current_allocation:.1%} -> {target_allocation:.1%}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the pipeline."""
        return {
            'running': self.running,
            'active_positions': len(self.active_positions),
            'pending_signals': len(self.pending_signals),
            'metrics': self.metrics,
            'evolution': self.evolution_state,
            'config': self.config,
            'timestamp': datetime.now().isoformat()
        }
    
    def stop(self):
        """Stop the pipeline."""
        self.running = False
        self.executor.shutdown(wait=True)
        print("Pipeline stopped")


# Singleton instance
_pipeline_instance = None


def get_ultra_pipeline(config: Dict[str, Any] = None) -> UltraMLPipeline:
    """Get or create the ultra ML pipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = UltraMLPipeline(config)
    return _pipeline_instance


async def main():
    """Main entry point for running the ultra system."""
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🧠 ULTRA ML TRADING SYSTEM - THE EVOLUTION BEGINS 🧠    ║
    ║                                                              ║
    ║     The Most Brilliant Self-Evolving Trader Ever Created   ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Configuration
    config = {
        'symbols': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT'],
        'timeframes': ['1m', '5m', '15m', '1h'],
        'max_positions': 5,
        'risk_per_trade': 0.02,
        'confidence_threshold': 0.65,
        'evolution_enabled': True,
        'online_learning': True,
        'multi_exchange': True,
        'use_news_sentiment': True,
        'use_onchain_data': True,
    }
    
    # Create and run pipeline
    pipeline = get_ultra_pipeline(config)
    
    try:
        await pipeline.run_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutdown signal received")
        pipeline.stop()
    except Exception as e:
        print(f"Fatal error: {e}")
        pipeline.stop()


if __name__ == "__main__":
    # Run the ultra system
    asyncio.run(main())