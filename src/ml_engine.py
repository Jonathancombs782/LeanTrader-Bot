"""
Machine Learning Engine for Trading Bot
Advanced ML models for price prediction and signal generation
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from loguru import logger
import joblib
from pathlib import Path

# ML Libraries
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.metrics import classification_report, accuracy_score
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Conv1D, MaxPooling1D
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint

# Technical Analysis
import talib

class MLEngine:
    """Advanced Machine Learning Engine for trading predictions"""
    
    def __init__(self, database, risk_manager):
        self.database = database
        self.risk_manager = risk_manager
        
        # Models
        self.models = {
            'lstm': None,
            'random_forest': None,
            'gradient_boosting': None,
            'ensemble': None
        }
        
        # Scalers
        self.scalers = {
            'price_scaler': StandardScaler(),
            'feature_scaler': RobustScaler()
        }
        
        # Configuration
        self.config = {
            'lookback_period': int(os.getenv('LOOKBACK_PERIOD', 1000)),
            'feature_window': int(os.getenv('FEATURE_WINDOW', 50)),
            'prediction_horizon': int(os.getenv('PREDICTION_HORIZON', 5)),
            'retrain_hours': int(os.getenv('MODEL_RETRAIN_HOURS', 24)),
            'min_confidence': float(os.getenv('MIN_CONFIDENCE', 0.7)),
            'feature_importance_threshold': 0.01
        }
        
        # State
        self.last_retrain = None
        self.model_performance = {}
        self.feature_importance = {}
        self.running = False
        
        # Supported symbols
        self.symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT']
        
    async def initialize(self):
        """Initialize the ML engine"""
        logger.info("🧠 Initializing ML Engine...")
        
        try:
            # Create models directory
            models_dir = Path("models/ml")
            models_dir.mkdir(parents=True, exist_ok=True)
            
            # Load or create models
            await self._load_or_create_models()
            
            # Initialize feature engineering
            await self._initialize_feature_engineering()
            
            logger.info("✅ ML Engine initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize ML engine: {e}")
            raise
            
    async def start(self):
        """Start the ML engine"""
        logger.info("🎯 Starting ML Engine...")
        self.running = True
        
        # Start background tasks
        await asyncio.gather(
            self._model_retrain_loop(),
            self._performance_monitoring_loop()
        )
        
    async def stop(self):
        """Stop the ML engine"""
        logger.info("🛑 Stopping ML Engine...")
        self.running = False
        
    async def _load_or_create_models(self):
        """Load existing models or create new ones"""
        models_dir = Path("models/ml")
        
        # Try to load existing models
        for model_name in self.models.keys():
            model_path = models_dir / f"{model_name}_model.joblib"
            
            if model_path.exists():
                try:
                    if model_name == 'lstm':
                        self.models[model_name] = tf.keras.models.load_model(model_path)
                    else:
                        self.models[model_name] = joblib.load(model_path)
                    logger.info(f"✅ Loaded {model_name} model")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load {model_name} model: {e}")
                    self.models[model_name] = None
            else:
                self.models[model_name] = None
                
        # Create models if they don't exist
        if not any(self.models.values()):
            logger.info("🔧 No existing models found, creating new ones...")
            await self._create_initial_models()
            
    async def _create_initial_models(self):
        """Create initial ML models"""
        logger.info("🏗️ Creating initial ML models...")
        
        # Get training data
        training_data = await self._prepare_training_data()
        
        if training_data is None or len(training_data) < 100:
            logger.warning("⚠️ Insufficient training data, creating dummy models")
            await self._create_dummy_models()
            return
            
        # Create LSTM model
        await self._create_lstm_model(training_data)
        
        # Create ensemble models
        await self._create_ensemble_models(training_data)
        
        # Save models
        await self._save_models()
        
    async def _prepare_training_data(self) -> Optional[pd.DataFrame]:
        """Prepare training data for ML models"""
        try:
            # Get historical data for all symbols
            all_data = []
            
            for symbol in self.symbols:
                data = await self.database.get_historical_data(
                    symbol, 
                    limit=self.config['lookback_period']
                )
                if data is not None and len(data) > 0:
                    data['symbol'] = symbol
                    all_data.append(data)
                    
            if not all_data:
                logger.warning("⚠️ No historical data available")
                return None
                
            # Combine all data
            combined_data = pd.concat(all_data, ignore_index=True)
            
            # Feature engineering
            combined_data = await self._engineer_features(combined_data)
            
            # Create targets
            combined_data = await self._create_targets(combined_data)
            
            # Remove rows with NaN values
            combined_data = combined_data.dropna()
            
            logger.info(f"📊 Prepared training data: {len(combined_data)} samples")
            return combined_data
            
        except Exception as e:
            logger.error(f"Error preparing training data: {e}")
            return None
            
    async def _engineer_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Engineer technical features for ML models"""
        try:
            # Price-based features
            data['returns'] = data['close'].pct_change()
            data['log_returns'] = np.log(data['close'] / data['close'].shift(1))
            data['volatility'] = data['returns'].rolling(window=20).std()
            
            # Technical indicators
            data['rsi'] = talib.RSI(data['close'].values, timeperiod=14)
            data['macd'], data['macd_signal'], data['macd_hist'] = talib.MACD(data['close'].values)
            data['bb_upper'], data['bb_middle'], data['bb_lower'] = talib.BBANDS(data['close'].values)
            data['sma_20'] = talib.SMA(data['close'].values, timeperiod=20)
            data['sma_50'] = talib.SMA(data['close'].values, timeperiod=50)
            data['ema_12'] = talib.EMA(data['close'].values, timeperiod=12)
            data['ema_26'] = talib.EMA(data['close'].values, timeperiod=26)
            
            # Volume features
            data['volume_sma'] = talib.SMA(data['volume'].values, timeperiod=20)
            data['volume_ratio'] = data['volume'] / data['volume_sma']
            
            # Price position features
            data['price_vs_sma20'] = data['close'] / data['sma_20'] - 1
            data['price_vs_sma50'] = data['close'] / data['sma_50'] - 1
            data['bb_position'] = (data['close'] - data['bb_lower']) / (data['bb_upper'] - data['bb_lower'])
            
            # Lagged features
            for lag in [1, 2, 3, 5, 10]:
                data[f'returns_lag_{lag}'] = data['returns'].shift(lag)
                data[f'volume_lag_{lag}'] = data['volume'].shift(lag)
                
            # Rolling features
            for window in [5, 10, 20]:
                data[f'returns_mean_{window}'] = data['returns'].rolling(window=window).mean()
                data[f'returns_std_{window}'] = data['returns'].rolling(window=window).std()
                data[f'volume_mean_{window}'] = data['volume'].rolling(window=window).mean()
                
            # Market regime features
            data['trend'] = np.where(data['sma_20'] > data['sma_50'], 1, 0)
            data['momentum'] = np.where(data['rsi'] > 70, 1, np.where(data['rsi'] < 30, -1, 0))
            
            return data
            
        except Exception as e:
            logger.error(f"Error engineering features: {e}")
            return data
            
    async def _create_targets(self, data: pd.DataFrame) -> pd.DataFrame:
        """Create target variables for ML models"""
        try:
            # Future returns
            data['future_return'] = data['close'].shift(-self.config['prediction_horizon']) / data['close'] - 1
            
            # Classification targets
            data['target'] = np.where(data['future_return'] > 0.02, 1,  # Strong buy
                                    np.where(data['future_return'] < -0.02, -1, 0))  # Strong sell, else hold
                                    
            # Multi-class targets
            data['target_class'] = np.where(data['future_return'] > 0.01, 2,  # Buy
                                          np.where(data['future_return'] > -0.01, 1, 0))  # Hold, Sell
                                          
            return data
            
        except Exception as e:
            logger.error(f"Error creating targets: {e}")
            return data
            
    async def _create_lstm_model(self, data: pd.DataFrame):
        """Create LSTM model for sequence prediction"""
        try:
            # Prepare features for LSTM
            feature_columns = [col for col in data.columns if col not in ['symbol', 'timestamp', 'target', 'target_class', 'future_return']]
            
            # Group by symbol and create sequences
            sequences = []
            targets = []
            
            for symbol in data['symbol'].unique():
                symbol_data = data[data['symbol'] == symbol].sort_values('timestamp')
                
                for i in range(self.config['feature_window'], len(symbol_data)):
                    sequence = symbol_data.iloc[i-self.config['feature_window']:i][feature_columns].values
                    target = symbol_data.iloc[i]['target_class']
                    
                    sequences.append(sequence)
                    targets.append(target)
                    
            if len(sequences) == 0:
                logger.warning("⚠️ No sequences created for LSTM")
                return
                
            X = np.array(sequences)
            y = np.array(targets)
            
            # Scale features
            X_scaled = self.scalers['feature_scaler'].fit_transform(
                X.reshape(-1, X.shape[-1])
            ).reshape(X.shape)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42, stratify=y
            )
            
            # Create LSTM model
            model = Sequential([
                Conv1D(filters=64, kernel_size=3, activation='relu', input_shape=(X.shape[1], X.shape[2])),
                MaxPooling1D(pool_size=2),
                LSTM(50, return_sequences=True, dropout=0.2),
                LSTM(50, dropout=0.2),
                Dense(25, activation='relu'),
                Dropout(0.2),
                Dense(3, activation='softmax')  # 3 classes: Sell, Hold, Buy
            ])
            
            model.compile(
                optimizer=Adam(learning_rate=0.001),
                loss='sparse_categorical_crossentropy',
                metrics=['accuracy']
            )
            
            # Train model
            callbacks = [
                EarlyStopping(patience=10, restore_best_weights=True),
                ModelCheckpoint('models/ml/lstm_best_model.h5', save_best_only=True)
            ]
            
            history = model.fit(
                X_train, y_train,
                validation_data=(X_test, y_test),
                epochs=100,
                batch_size=32,
                callbacks=callbacks,
                verbose=0
            )
            
            # Evaluate model
            test_loss, test_accuracy = model.evaluate(X_test, y_test, verbose=0)
            logger.info(f"✅ LSTM model trained - Accuracy: {test_accuracy:.4f}")
            
            self.models['lstm'] = model
            self.model_performance['lstm'] = {
                'accuracy': test_accuracy,
                'loss': test_loss,
                'last_trained': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error creating LSTM model: {e}")
            
    async def _create_ensemble_models(self, data: pd.DataFrame):
        """Create ensemble models (Random Forest, Gradient Boosting)"""
        try:
            # Prepare features
            feature_columns = [col for col in data.columns if col not in ['symbol', 'timestamp', 'target', 'target_class', 'future_return']]
            
            # Create lagged features for ensemble models
            ensemble_data = data.copy()
            
            # Add more lagged features for ensemble models
            for col in ['returns', 'volume', 'rsi', 'macd']:
                if col in feature_columns:
                    for lag in range(1, 11):
                        ensemble_data[f'{col}_lag_{lag}'] = ensemble_data[col].shift(lag)
                        
            # Update feature columns
            feature_columns = [col for col in ensemble_data.columns if col not in ['symbol', 'timestamp', 'target', 'target_class', 'future_return']]
            
            X = ensemble_data[feature_columns].fillna(0)
            y = ensemble_data['target_class'].fillna(1)  # Default to hold
            
            # Remove rows with all zeros
            valid_rows = (X != 0).any(axis=1)
            X = X[valid_rows]
            y = y[valid_rows]
            
            if len(X) == 0:
                logger.warning("⚠️ No valid data for ensemble models")
                return
                
            # Scale features
            X_scaled = self.scalers['feature_scaler'].fit_transform(X)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42, stratify=y
            )
            
            # Random Forest
            rf_model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            rf_model.fit(X_train, y_train)
            
            rf_accuracy = accuracy_score(y_test, rf_model.predict(X_test))
            logger.info(f"✅ Random Forest trained - Accuracy: {rf_accuracy:.4f}")
            
            self.models['random_forest'] = rf_model
            self.model_performance['random_forest'] = {
                'accuracy': rf_accuracy,
                'last_trained': datetime.now()
            }
            
            # Feature importance
            self.feature_importance['random_forest'] = dict(zip(
                feature_columns,
                rf_model.feature_importances_
            ))
            
            # Gradient Boosting
            gb_model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=6,
                random_state=42
            )
            gb_model.fit(X_train, y_train)
            
            gb_accuracy = accuracy_score(y_test, gb_model.predict(X_test))
            logger.info(f"✅ Gradient Boosting trained - Accuracy: {gb_accuracy:.4f}")
            
            self.models['gradient_boosting'] = gb_model
            self.model_performance['gradient_boosting'] = {
                'accuracy': gb_accuracy,
                'last_trained': datetime.now()
            }
            
            # Feature importance
            self.feature_importance['gradient_boosting'] = dict(zip(
                feature_columns,
                gb_model.feature_importances_
            ))
            
        except Exception as e:
            logger.error(f"Error creating ensemble models: {e}")
            
    async def _create_dummy_models(self):
        """Create dummy models when insufficient data is available"""
        logger.info("🎭 Creating dummy models for demonstration...")
        
        # Dummy LSTM model
        dummy_lstm = Sequential([
            Dense(10, activation='relu', input_shape=(10,)),
            Dense(3, activation='softmax')
        ])
        dummy_lstm.compile(optimizer='adam', loss='sparse_categorical_crossentropy')
        self.models['lstm'] = dummy_lstm
        
        # Dummy ensemble models
        self.models['random_forest'] = RandomForestClassifier(n_estimators=10, random_state=42)
        self.models['gradient_boosting'] = GradientBoostingClassifier(n_estimators=10, random_state=42)
        
        logger.info("✅ Dummy models created")
        
    async def _save_models(self):
        """Save trained models"""
        models_dir = Path("models/ml")
        
        for model_name, model in self.models.items():
            if model is not None:
                try:
                    model_path = models_dir / f"{model_name}_model.joblib"
                    
                    if model_name == 'lstm':
                        model.save(model_path)
                    else:
                        joblib.dump(model, model_path)
                        
                    logger.info(f"💾 Saved {model_name} model")
                    
                except Exception as e:
                    logger.error(f"Error saving {model_name} model: {e}")
                    
    async def generate_signals(self, market_data: Dict) -> List[TradeSignal]:
        """Generate trading signals using ML models"""
        signals = []
        
        try:
            for symbol, data in market_data.items():
                if symbol not in self.symbols:
                    continue
                    
                # Prepare features for prediction
                features = await self._prepare_prediction_features(data)
                
                if features is None:
                    continue
                    
                # Get predictions from all models
                predictions = {}
                confidences = {}
                
                # LSTM prediction
                if self.models['lstm'] is not None:
                    lstm_pred, lstm_conf = await self._predict_lstm(features)
                    predictions['lstm'] = lstm_pred
                    confidences['lstm'] = lstm_conf
                    
                # Ensemble predictions
                if self.models['random_forest'] is not None:
                    rf_pred, rf_conf = await self._predict_ensemble(features, 'random_forest')
                    predictions['random_forest'] = rf_pred
                    confidences['random_forest'] = rf_conf
                    
                if self.models['gradient_boosting'] is not None:
                    gb_pred, gb_conf = await self._predict_ensemble(features, 'gradient_boosting')
                    predictions['gradient_boosting'] = gb_pred
                    confidences['gradient_boosting'] = gb_conf
                    
                # Ensemble prediction
                if len(predictions) > 1:
                    final_prediction, final_confidence = await self._ensemble_predict(predictions, confidences)
                else:
                    final_prediction = list(predictions.values())[0] if predictions else 1
                    final_confidence = list(confidences.values())[0] if confidences else 0.5
                    
                # Convert prediction to signal
                signal = await self._prediction_to_signal(
                    symbol, final_prediction, final_confidence, data
                )
                
                if signal:
                    signals.append(signal)
                    
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            
        return signals
        
    async def _prepare_prediction_features(self, data: pd.DataFrame) -> Optional[np.ndarray]:
        """Prepare features for prediction"""
        try:
            if len(data) < self.config['feature_window']:
                return None
                
            # Get latest data
            latest_data = data.tail(self.config['feature_window']).copy()
            
            # Engineer features
            latest_data = await self._engineer_features(latest_data)
            
            # Select feature columns
            feature_columns = [col for col in latest_data.columns if col not in ['symbol', 'timestamp', 'target', 'target_class', 'future_return']]
            
            # Fill NaN values
            features = latest_data[feature_columns].fillna(0).values
            
            # Scale features
            if hasattr(self.scalers['feature_scaler'], 'scale_'):
                features_scaled = self.scalers['feature_scaler'].transform(features)
            else:
                features_scaled = features
                
            return features_scaled
            
        except Exception as e:
            logger.error(f"Error preparing prediction features: {e}")
            return None
            
    async def _predict_lstm(self, features: np.ndarray) -> Tuple[int, float]:
        """Make prediction using LSTM model"""
        try:
            if self.models['lstm'] is None:
                return 1, 0.5  # Default to hold
                
            # Reshape for LSTM
            if len(features.shape) == 2:
                features = features.reshape(1, features.shape[0], features.shape[1])
                
            # Make prediction
            prediction = self.models['lstm'].predict(features, verbose=0)
            
            # Get class and confidence
            predicted_class = np.argmax(prediction[0])
            confidence = float(np.max(prediction[0]))
            
            return predicted_class, confidence
            
        except Exception as e:
            logger.error(f"Error in LSTM prediction: {e}")
            return 1, 0.5
            
    async def _predict_ensemble(self, features: np.ndarray, model_name: str) -> Tuple[int, float]:
        """Make prediction using ensemble model"""
        try:
            model = self.models[model_name]
            if model is None:
                return 1, 0.5  # Default to hold
                
            # Flatten features for ensemble models
            if len(features.shape) == 3:
                features = features.reshape(features.shape[0], -1)
            elif len(features.shape) == 2:
                features = features.reshape(1, -1)
                
            # Make prediction
            prediction = model.predict(features)
            probabilities = model.predict_proba(features)
            
            predicted_class = int(prediction[0])
            confidence = float(np.max(probabilities[0]))
            
            return predicted_class, confidence
            
        except Exception as e:
            logger.error(f"Error in {model_name} prediction: {e}")
            return 1, 0.5
            
    async def _ensemble_predict(self, predictions: Dict, confidences: Dict) -> Tuple[int, float]:
        """Combine predictions from multiple models"""
        try:
            # Weight models by their performance
            weights = {}
            total_weight = 0
            
            for model_name in predictions.keys():
                if model_name in self.model_performance:
                    weight = self.model_performance[model_name].get('accuracy', 0.5)
                    weights[model_name] = weight
                    total_weight += weight
                else:
                    weights[model_name] = 1.0
                    total_weight += 1.0
                    
            # Normalize weights
            for model_name in weights:
                weights[model_name] /= total_weight
                
            # Weighted voting
            weighted_votes = {0: 0, 1: 0, 2: 0}  # Sell, Hold, Buy
            
            for model_name, prediction in predictions.items():
                weight = weights[model_name]
                weighted_votes[prediction] += weight
                
            # Get final prediction
            final_prediction = max(weighted_votes, key=weighted_votes.get)
            
            # Calculate ensemble confidence
            ensemble_confidence = weighted_votes[final_prediction]
            
            return final_prediction, ensemble_confidence
            
        except Exception as e:
            logger.error(f"Error in ensemble prediction: {e}")
            return 1, 0.5
            
    async def _prediction_to_signal(self, symbol: str, prediction: int, confidence: float, data: pd.DataFrame) -> Optional[TradeSignal]:
        """Convert ML prediction to trading signal"""
        try:
            if confidence < self.config['min_confidence']:
                return None
                
            current_price = float(data['close'].iloc[-1])
            current_volume = float(data['volume'].iloc[-1])
            
            # Calculate position size based on confidence and risk
            base_size = float(os.getenv('INITIAL_CAPITAL', 10000)) * float(os.getenv('POSITION_SIZE_PCT', 0.1))
            position_size = base_size * confidence
            
            # Calculate quantity
            quantity = position_size / current_price
            
            # Determine action
            if prediction == 2:  # Buy
                action = 'BUY'
                reasoning = f"ML Buy signal (confidence: {confidence:.2f})"
            elif prediction == 0:  # Sell
                action = 'SELL'
                reasoning = f"ML Sell signal (confidence: {confidence:.2f})"
            else:  # Hold
                return None
                
            # Calculate stop loss and take profit
            stop_loss = None
            take_profit = None
            
            if action == 'BUY':
                stop_loss = current_price * (1 - float(os.getenv('STOP_LOSS_PCT', 0.05)))
                take_profit = current_price * (1 + float(os.getenv('TAKE_PROFIT_PCT', 0.1)))
                
            signal = TradeSignal(
                symbol=symbol,
                action=action,
                confidence=confidence,
                price=current_price,
                quantity=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=reasoning,
                timestamp=datetime.now()
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Error converting prediction to signal: {e}")
            return None
            
    async def _model_retrain_loop(self):
        """Background loop for model retraining"""
        while self.running:
            try:
                # Check if retraining is needed
                if self.last_retrain is None or \
                   (datetime.now() - self.last_retrain).total_seconds() > self.config['retrain_hours'] * 3600:
                    
                    logger.info("🔄 Starting model retraining...")
                    await self._retrain_models()
                    self.last_retrain = datetime.now()
                    
                # Wait before next check
                await asyncio.sleep(3600)  # Check every hour
                
            except Exception as e:
                logger.error(f"Error in retrain loop: {e}")
                await asyncio.sleep(3600)
                
    async def _retrain_models(self):
        """Retrain all models with latest data"""
        try:
            # Get fresh training data
            training_data = await self._prepare_training_data()
            
            if training_data is None or len(training_data) < 100:
                logger.warning("⚠️ Insufficient data for retraining")
                return
                
            # Retrain models
            await self._create_lstm_model(training_data)
            await self._create_ensemble_models(training_data)
            
            # Save updated models
            await self._save_models()
            
            logger.info("✅ Models retrained successfully")
            
        except Exception as e:
            logger.error(f"Error retraining models: {e}")
            
    async def _performance_monitoring_loop(self):
        """Monitor model performance"""
        while self.running:
            try:
                # Log performance metrics
                for model_name, performance in self.model_performance.items():
                    logger.info(f"📊 {model_name} performance: {performance}")
                    
                # Wait before next check
                await asyncio.sleep(3600)  # Check every hour
                
            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")
                await asyncio.sleep(3600)
                
    async def _initialize_feature_engineering(self):
        """Initialize feature engineering components"""
        # This could include feature selection, dimensionality reduction, etc.
        pass
        
    async def get_model_status(self) -> dict:
        """Get current model status"""
        return {
            'models_loaded': {name: model is not None for name, model in self.models.items()},
            'model_performance': self.model_performance,
            'feature_importance': self.feature_importance,
            'last_retrain': self.last_retrain.isoformat() if self.last_retrain else None,
            'config': self.config
        }
        
    async def is_healthy(self) -> bool:
        """Check if ML engine is healthy"""
        try:
            # Check if at least one model is loaded
            if not any(self.models.values()):
                return False
                
            # Check if models are responding
            dummy_features = np.random.random((1, 10))
            
            for model_name, model in self.models.items():
                if model is not None:
                    try:
                        if model_name == 'lstm':
                            model.predict(dummy_features.reshape(1, 1, -1), verbose=0)
                        else:
                            model.predict(dummy_features)
                    except Exception:
                        return False
                        
            return True
            
        except Exception:
            return False