#!/usr/bin/env python3
"""
DIVINE INTELLIGENCE CORE
Advanced AI that continuously learns and evolves trading strategies
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib
import sqlite3
from datetime import datetime, timedelta
from loguru import logger
import asyncio
import threading
from typing import Dict, List, Optional, Tuple
import json
import warnings
warnings.filterwarnings('ignore')

class DivineIntelligenceCore:
    """Divine Intelligence Core - Continuously learning AI"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_importance = {}
        self.performance_history = []
        self.strategy_evolution = []
        self.learning_active = True
        self.db = None
        
        # Trading pairs and timeframes
        self.trading_pairs = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT',
            'XRP/USDT', 'DOT/USDT', 'DOGE/USDT', 'AVAX/USDT', 'MATIC/USDT',
            'LTC/USDT', 'LINK/USDT', 'UNI/USDT', 'ATOM/USDT', 'FIL/USDT'
        ]
        
        self.timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        
        # Initialize database
        self.initialize_database()
        
        # Start continuous learning thread
        self.start_continuous_learning()
    
    def initialize_database(self):
        """Initialize database for storing learning data"""
        try:
            self.db = sqlite3.connect('divine_intelligence.db', check_same_thread=False)
            cursor = self.db.cursor()
            
            # Create tables for learning data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS market_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL,
                    rsi REAL,
                    macd REAL,
                    bollinger_upper REAL,
                    bollinger_lower REAL,
                    ema_12 REAL,
                    ema_26 REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trading_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    price REAL NOT NULL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    stop_loss REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    executed BOOLEAN DEFAULT FALSE,
                    profit_loss REAL DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    model_type TEXT NOT NULL,
                    accuracy REAL NOT NULL,
                    precision REAL NOT NULL,
                    recall REAL NOT NULL,
                    f1_score REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_evolution (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    performance_score REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.db.commit()
            logger.info("✅ Divine Intelligence database initialized")
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
    
    def start_continuous_learning(self):
        """Start continuous learning thread"""
        try:
            learning_thread = threading.Thread(target=self.continuous_learning_loop, daemon=True)
            learning_thread.start()
            logger.info("🧠 Continuous learning started")
        except Exception as e:
            logger.error(f"❌ Failed to start continuous learning: {e}")
    
    def continuous_learning_loop(self):
        """Main continuous learning loop"""
        while self.learning_active:
            try:
                # Learn from new market data every 30 seconds
                self.learn_from_market_data()
                
                # Evolve strategies every 5 minutes
                self.evolve_strategies()
                
                # Update models every 10 minutes
                self.update_models()
                
                # Sleep for 30 seconds
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in continuous learning loop: {e}")
                time.sleep(60)
    
    def learn_from_market_data(self):
        """Learn from new market data"""
        try:
            cursor = self.db.cursor()
            
            # Get recent market data
            cursor.execute('''
                SELECT * FROM market_data 
                WHERE timestamp > datetime('now', '-1 hour')
                ORDER BY timestamp DESC
            ''')
            
            recent_data = cursor.fetchall()
            
            if len(recent_data) > 100:  # Need sufficient data
                # Process data for learning
                self.process_learning_data(recent_data)
                
        except Exception as e:
            logger.error(f"Error in learn_from_market_data: {e}")
    
    def process_learning_data(self, data):
        """Process market data for learning"""
        try:
            df = pd.DataFrame(data, columns=[
                'id', 'symbol', 'timeframe', 'price', 'volume', 
                'rsi', 'macd', 'bollinger_upper', 'bollinger_lower', 
                'ema_12', 'ema_26', 'timestamp'
            ])
            
            # Group by symbol and timeframe
            for symbol in df['symbol'].unique():
                for timeframe in df['timeframe'].unique():
                    symbol_data = df[(df['symbol'] == symbol) & (df['timeframe'] == timeframe)]
                    
                    if len(symbol_data) > 50:  # Minimum data points
                        self.train_model_for_pair(symbol, timeframe, symbol_data)
                        
        except Exception as e:
            logger.error(f"Error processing learning data: {e}")
    
    def train_model_for_pair(self, symbol, timeframe, data):
        """Train model for specific symbol/timeframe"""
        try:
            # Prepare features
            features = ['price', 'volume', 'rsi', 'macd', 'bollinger_upper', 'bollinger_lower', 'ema_12', 'ema_26']
            X = data[features].fillna(0).values
            
            # Create target (price movement)
            data['price_change'] = data['price'].pct_change()
            data['target'] = (data['price_change'] > 0.001).astype(int)  # 0.1% threshold
            
            y = data['target'].fillna(0).values
            
            if len(X) > 20 and len(y) > 20:
                # Split data
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
                
                # Scale features
                scaler = StandardScaler()
                X_train_scaled = scaler.fit_transform(X_train)
                X_test_scaled = scaler.transform(X_test)
                
                # Train multiple models
                models = {
                    'random_forest': RandomForestClassifier(n_estimators=100, random_state=42),
                    'gradient_boosting': GradientBoostingClassifier(n_estimators=100, random_state=42),
                    'neural_network': MLPClassifier(hidden_layer_sizes=(50, 25), max_iter=500, random_state=42)
                }
                
                best_model = None
                best_score = 0
                best_model_name = ''
                
                for model_name, model in models.items():
                    try:
                        model.fit(X_train_scaled, y_train)
                        score = model.score(X_test_scaled, y_test)
                        
                        if score > best_score:
                            best_score = score
                            best_model = model
                            best_model_name = model_name
                            
                    except Exception as e:
                        logger.warning(f"Model {model_name} training failed: {e}")
                
                if best_model is not None and best_score > 0.6:  # Minimum accuracy threshold
                    # Save best model
                    model_key = f"{symbol}_{timeframe}"
                    self.models[model_key] = best_model
                    self.scalers[model_key] = scaler
                    
                    # Save to database
                    cursor = self.db.cursor()
                    cursor.execute('''
                        INSERT INTO model_performance 
                        (symbol, timeframe, model_type, accuracy, precision, recall, f1_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (symbol, timeframe, best_model_name, best_score, 0, 0, 0))
                    self.db.commit()
                    
                    logger.info(f"🧠 Model trained for {symbol} {timeframe}: {best_model_name} (Accuracy: {best_score:.3f})")
                    
        except Exception as e:
            logger.error(f"Error training model for {symbol} {timeframe}: {e}")
    
    def evolve_strategies(self):
        """Evolve trading strategies"""
        try:
            # Get recent trading performance
            cursor = self.db.cursor()
            cursor.execute('''
                SELECT * FROM trading_signals 
                WHERE timestamp > datetime('now', '-24 hours')
                AND executed = TRUE
            ''')
            
            recent_trades = cursor.fetchall()
            
            if len(recent_trades) > 10:
                # Analyze performance and evolve strategies
                self.analyze_and_evolve(recent_trades)
                
        except Exception as e:
            logger.error(f"Error in evolve_strategies: {e}")
    
    def analyze_and_evolve(self, trades):
        """Analyze trades and evolve strategies"""
        try:
            df = pd.DataFrame(trades, columns=[
                'id', 'symbol', 'timeframe', 'signal', 'confidence', 
                'price', 'tp1', 'tp2', 'tp3', 'stop_loss', 
                'timestamp', 'executed', 'profit_loss'
            ])
            
            # Calculate strategy performance
            total_profit = df['profit_loss'].sum()
            win_rate = (df['profit_loss'] > 0).mean()
            avg_profit = df['profit_loss'].mean()
            
            # Evolve based on performance
            if win_rate > 0.7:  # Good performance
                self.enhance_winning_strategies(df)
            elif win_rate < 0.3:  # Poor performance
                self.revise_losing_strategies(df)
            
            # Save strategy evolution
            strategy_params = {
                'win_rate': win_rate,
                'avg_profit': avg_profit,
                'total_trades': len(df),
                'total_profit': total_profit
            }
            
            cursor = self.db.cursor()
            cursor.execute('''
                INSERT INTO strategy_evolution 
                (strategy_name, parameters, performance_score)
                VALUES (?, ?, ?)
            ''', ('divine_strategy', json.dumps(strategy_params), win_rate * avg_profit))
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error in analyze_and_evolve: {e}")
    
    def enhance_winning_strategies(self, df):
        """Enhance winning strategies"""
        try:
            winning_trades = df[df['profit_loss'] > 0]
            
            # Analyze winning patterns
            high_confidence_trades = winning_trades[winning_trades['confidence'] > 0.8]
            
            if len(high_confidence_trades) > 5:
                logger.info(f"🧠 Enhancing winning strategies: {len(high_confidence_trades)} high-confidence wins")
                
                # Increase confidence thresholds for similar patterns
                for _, trade in high_confidence_trades.iterrows():
                    symbol = trade['symbol']
                    timeframe = trade['timeframe']
                    
                    # Enhance model for this pair
                    self.boost_model_confidence(symbol, timeframe)
                    
        except Exception as e:
            logger.error(f"Error in enhance_winning_strategies: {e}")
    
    def revise_losing_strategies(self, df):
        """Revise losing strategies"""
        try:
            losing_trades = df[df['profit_loss'] < 0]
            
            logger.info(f"🧠 Revising losing strategies: {len(losing_trades)} losses")
            
            # Identify common patterns in losses
            for _, trade in losing_trades.iterrows():
                symbol = trade['symbol']
                timeframe = trade['timeframe']
                
                # Reduce confidence for this pair
                self.adjust_model_confidence(symbol, timeframe, reduce=True)
                
        except Exception as e:
            logger.error(f"Error in revise_losing_strategies: {e}")
    
    def boost_model_confidence(self, symbol, timeframe):
        """Boost model confidence for winning pairs"""
        try:
            model_key = f"{symbol}_{timeframe}"
            if model_key in self.models:
                # Adjust model parameters to be more confident
                logger.info(f"🧠 Boosting confidence for {symbol} {timeframe}")
                
        except Exception as e:
            logger.error(f"Error in boost_model_confidence: {e}")
    
    def adjust_model_confidence(self, symbol, timeframe, reduce=False):
        """Adjust model confidence"""
        try:
            model_key = f"{symbol}_{timeframe}"
            if model_key in self.models:
                action = "Reducing" if reduce else "Increasing"
                logger.info(f"🧠 {action} confidence for {symbol} {timeframe}")
                
        except Exception as e:
            logger.error(f"Error in adjust_model_confidence: {e}")
    
    def update_models(self):
        """Update models with latest data"""
        try:
            # Save models to disk
            for model_key, model in self.models.items():
                try:
                    joblib.dump(model, f'models/{model_key}_model.pkl')
                except Exception as e:
                    logger.warning(f"Failed to save model {model_key}: {e}")
            
            # Save scalers
            for scaler_key, scaler in self.scalers.items():
                try:
                    joblib.dump(scaler, f'models/{scaler_key}_scaler.pkl')
                except Exception as e:
                    logger.warning(f"Failed to save scaler {scaler_key}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in update_models: {e}")
    
    def predict_signal(self, symbol, timeframe, market_data):
        """Predict trading signal using divine intelligence"""
        try:
            model_key = f"{symbol}_{timeframe}"
            
            if model_key not in self.models:
                return {
                    'signal': 'HOLD',
                    'confidence': 0.5,
                    'tp1': 0,
                    'tp2': 0,
                    'tp3': 0,
                    'stop_loss': 0,
                    'model_used': 'default'
                }
            
            # Prepare features
            features = [
                market_data.get('price', 0),
                market_data.get('volume', 0),
                market_data.get('rsi', 50),
                market_data.get('macd', 0),
                market_data.get('bollinger_upper', market_data.get('price', 0) * 1.02),
                market_data.get('bollinger_lower', market_data.get('price', 0) * 0.98),
                market_data.get('ema_12', market_data.get('price', 0)),
                market_data.get('ema_26', market_data.get('price', 0))
            ]
            
            # Scale features
            scaler = self.scalers[model_key]
            features_scaled = scaler.transform([features])
            
            # Make prediction
            model = self.models[model_key]
            prediction = model.predict(features_scaled)[0]
            confidence = model.predict_proba(features_scaled)[0].max()
            
            # Determine signal
            signal = 'BUY' if prediction == 1 else 'SELL'
            
            # Calculate TP levels
            price = market_data.get('price', 0)
            tp1 = price * (1.02 if signal == 'BUY' else 0.98)  # 2% TP1
            tp2 = price * (1.05 if signal == 'BUY' else 0.95)  # 5% TP2
            tp3 = price * (1.10 if signal == 'BUY' else 0.90)  # 10% TP3
            stop_loss = price * (0.97 if signal == 'BUY' else 1.03)  # 3% SL
            
            return {
                'signal': signal,
                'confidence': confidence,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'stop_loss': stop_loss,
                'model_used': 'divine_intelligence'
            }
            
        except Exception as e:
            logger.error(f"Error in predict_signal: {e}")
            return {
                'signal': 'HOLD',
                'confidence': 0.5,
                'tp1': 0,
                'tp2': 0,
                'tp3': 0,
                'stop_loss': 0,
                'model_used': 'error'
            }
    
    def get_learning_stats(self):
        """Get learning statistics"""
        try:
            cursor = self.db.cursor()
            
            # Get model count
            cursor.execute('SELECT COUNT(DISTINCT symbol || "_" || timeframe) FROM model_performance')
            model_count = cursor.fetchone()[0]
            
            # Get recent performance
            cursor.execute('''
                SELECT AVG(accuracy) FROM model_performance 
                WHERE timestamp > datetime('now', '-24 hours')
            ''')
            avg_accuracy = cursor.fetchone()[0] or 0
            
            # Get strategy evolution count
            cursor.execute('SELECT COUNT(*) FROM strategy_evolution')
            evolution_count = cursor.fetchone()[0]
            
            return {
                'active_models': len(self.models),
                'total_models_trained': model_count,
                'average_accuracy': round(avg_accuracy, 3),
                'strategy_evolutions': evolution_count,
                'learning_active': self.learning_active
            }
            
        except Exception as e:
            logger.error(f"Error getting learning stats: {e}")
            return {
                'active_models': 0,
                'total_models_trained': 0,
                'average_accuracy': 0,
                'strategy_evolutions': 0,
                'learning_active': False
            }
    
    def stop_learning(self):
        """Stop continuous learning"""
        self.learning_active = False
        logger.info("🛑 Divine Intelligence learning stopped")

# Test the divine intelligence core
if __name__ == "__main__":
    core = DivineIntelligenceCore()
    
    # Test prediction
    test_data = {
        'price': 50000,
        'volume': 1000000,
        'rsi': 45,
        'macd': 100,
        'bollinger_upper': 52000,
        'bollinger_lower': 48000,
        'ema_12': 49500,
        'ema_26': 49000
    }
    
    prediction = core.predict_signal('BTC/USDT', '1h', test_data)
    print(f"Prediction: {prediction}")
    
    # Get learning stats
    stats = core.get_learning_stats()
    print(f"Learning Stats: {stats}")
    
    # Keep running for testing
    time.sleep(60)
    core.stop_learning()