"""
Strategy Engine
Core strategy execution and signal generation
"""

from __future__ import annotations
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone

import pandas as pd
import numpy as np


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


class SignalStrength(Enum):
    WEAK = 1
    MEDIUM = 2
    STRONG = 3
    VERY_STRONG = 4


@dataclass
class Signal:
    """Trading signal"""
    symbol: str
    signal_type: SignalType
    strength: SignalStrength
    confidence: float  # 0.0 to 1.0
    price: float
    timestamp: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class MarketData:
    """Market data container"""
    symbol: str
    timeframe: str
    ohlcv: pd.DataFrame
    timestamp: datetime
    
    @property
    def latest_price(self) -> float:
        return float(self.ohlcv['close'].iloc[-1])
    
    @property
    def latest_volume(self) -> float:
        return float(self.ohlcv['volume'].iloc[-1])


class Strategy(ABC):
    """Base strategy class"""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"strategy.{name}")
        self.enabled = True
        
    @abstractmethod
    async def generate_signal(self, market_data: MarketData) -> Optional[Signal]:
        """Generate trading signal based on market data"""
        pass
    
    @abstractmethod
    def get_required_indicators(self) -> List[str]:
        """Get list of required technical indicators"""
        pass
    
    def validate_signal(self, signal: Signal) -> bool:
        """Validate signal before execution"""
        if not signal:
            return False
        
        if signal.confidence < 0.0 or signal.confidence > 1.0:
            self.logger.warning(f"Invalid confidence level: {signal.confidence}")
            return False
        
        if signal.price <= 0:
            self.logger.warning(f"Invalid price: {signal.price}")
            return False
        
        return True


class TechnicalStrategy(Strategy):
    """Strategy based on technical indicators"""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(name, config)
        self.lookback_period = self.config.get("lookback_period", 20)
        self.min_confidence = self.config.get("min_confidence", 0.6)
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """Calculate MACD indicator"""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram
        }
    
    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: float = 2) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return {
            "upper": upper_band,
            "middle": sma,
            "lower": lower_band
        }
    
    def calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr


class RSIStrategy(TechnicalStrategy):
    """RSI-based strategy"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("RSI", config)
        self.oversold_level = self.config.get("oversold_level", 30)
        self.overbought_level = self.config.get("overbought_level", 70)
        self.rsi_period = self.config.get("rsi_period", 14)
    
    def get_required_indicators(self) -> List[str]:
        return ["rsi"]
    
    async def generate_signal(self, market_data: MarketData) -> Optional[Signal]:
        if len(market_data.ohlcv) < self.rsi_period + 1:
            return None
        
        prices = market_data.ohlcv['close']
        rsi = self.calculate_rsi(prices, self.rsi_period)
        current_rsi = rsi.iloc[-1]
        
        if pd.isna(current_rsi):
            return None
        
        signal_type = None
        confidence = 0.0
        strength = SignalStrength.WEAK
        
        if current_rsi < self.oversold_level:
            signal_type = SignalType.BUY
            confidence = (self.oversold_level - current_rsi) / self.oversold_level
            if confidence > 0.7:
                strength = SignalStrength.STRONG
            elif confidence > 0.5:
                strength = SignalStrength.MEDIUM
        
        elif current_rsi > self.overbought_level:
            signal_type = SignalType.SELL
            confidence = (current_rsi - self.overbought_level) / (100 - self.overbought_level)
            if confidence > 0.7:
                strength = SignalStrength.STRONG
            elif confidence > 0.5:
                strength = SignalStrength.MEDIUM
        
        if signal_type and confidence >= self.min_confidence:
            return Signal(
                symbol=market_data.symbol,
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                price=market_data.latest_price,
                timestamp=market_data.timestamp,
                metadata={"rsi": current_rsi}
            )
        
        return None


class MACDStrategy(TechnicalStrategy):
    """MACD-based strategy"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("MACD", config)
        self.fast_period = self.config.get("fast_period", 12)
        self.slow_period = self.config.get("slow_period", 26)
        self.signal_period = self.config.get("signal_period", 9)
    
    def get_required_indicators(self) -> List[str]:
        return ["macd"]
    
    async def generate_signal(self, market_data: MarketData) -> Optional[Signal]:
        if len(market_data.ohlcv) < self.slow_period + self.signal_period:
            return None
        
        prices = market_data.ohlcv['close']
        macd_data = self.calculate_macd(prices, self.fast_period, self.slow_period, self.signal_period)
        
        macd_line = macd_data["macd"]
        signal_line = macd_data["signal"]
        histogram = macd_data["histogram"]
        
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        current_histogram = histogram.iloc[-1]
        prev_histogram = histogram.iloc[-2] if len(histogram) > 1 else 0
        
        if pd.isna(current_macd) or pd.isna(current_signal):
            return None
        
        signal_type = None
        confidence = 0.0
        strength = SignalStrength.WEAK
        
        # MACD line crosses above signal line
        if current_macd > current_signal and macd_line.iloc[-2] <= signal_line.iloc[-2]:
            signal_type = SignalType.BUY
            confidence = min(abs(current_histogram) / abs(current_macd), 1.0) if current_macd != 0 else 0.5
            if confidence > 0.7:
                strength = SignalStrength.STRONG
            elif confidence > 0.5:
                strength = SignalStrength.MEDIUM
        
        # MACD line crosses below signal line
        elif current_macd < current_signal and macd_line.iloc[-2] >= signal_line.iloc[-2]:
            signal_type = SignalType.SELL
            confidence = min(abs(current_histogram) / abs(current_macd), 1.0) if current_macd != 0 else 0.5
            if confidence > 0.7:
                strength = SignalStrength.STRONG
            elif confidence > 0.5:
                strength = SignalStrength.MEDIUM
        
        # Histogram momentum
        elif current_histogram > prev_histogram and current_histogram > 0:
            signal_type = SignalType.BUY
            confidence = 0.3
            strength = SignalStrength.WEAK
        
        elif current_histogram < prev_histogram and current_histogram < 0:
            signal_type = SignalType.SELL
            confidence = 0.3
            strength = SignalStrength.WEAK
        
        if signal_type and confidence >= self.min_confidence:
            return Signal(
                symbol=market_data.symbol,
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                price=market_data.latest_price,
                timestamp=market_data.timestamp,
                metadata={
                    "macd": current_macd,
                    "signal": current_signal,
                    "histogram": current_histogram
                }
            )
        
        return None


class BollingerBandsStrategy(TechnicalStrategy):
    """Bollinger Bands strategy"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("BollingerBands", config)
        self.bb_period = self.config.get("bb_period", 20)
        self.bb_std = self.config.get("bb_std", 2)
    
    def get_required_indicators(self) -> List[str]:
        return ["bollinger_bands"]
    
    async def generate_signal(self, market_data: MarketData) -> Optional[Signal]:
        if len(market_data.ohlcv) < self.bb_period:
            return None
        
        prices = market_data.ohlcv['close']
        bb_data = self.calculate_bollinger_bands(prices, self.bb_period, self.bb_std)
        
        upper_band = bb_data["upper"]
        middle_band = bb_data["middle"]
        lower_band = bb_data["lower"]
        
        current_price = market_data.latest_price
        current_upper = upper_band.iloc[-1]
        current_middle = middle_band.iloc[-1]
        current_lower = lower_band.iloc[-1]
        
        if pd.isna(current_upper) or pd.isna(current_lower):
            return None
        
        signal_type = None
        confidence = 0.0
        strength = SignalStrength.WEAK
        
        # Price touches lower band (oversold)
        if current_price <= current_lower:
            signal_type = SignalType.BUY
            confidence = (current_lower - current_price) / (current_upper - current_lower)
            confidence = min(confidence, 1.0)
            if confidence > 0.7:
                strength = SignalStrength.STRONG
            elif confidence > 0.5:
                strength = SignalStrength.MEDIUM
        
        # Price touches upper band (overbought)
        elif current_price >= current_upper:
            signal_type = SignalType.SELL
            confidence = (current_price - current_upper) / (current_upper - current_lower)
            confidence = min(confidence, 1.0)
            if confidence > 0.7:
                strength = SignalStrength.STRONG
            elif confidence > 0.5:
                strength = SignalStrength.MEDIUM
        
        # Price crosses middle band
        elif current_price > current_middle and prices.iloc[-2] <= middle_band.iloc[-2]:
            signal_type = SignalType.BUY
            confidence = 0.4
            strength = SignalStrength.WEAK
        
        elif current_price < current_middle and prices.iloc[-2] >= middle_band.iloc[-2]:
            signal_type = SignalType.SELL
            confidence = 0.4
            strength = SignalStrength.WEAK
        
        if signal_type and confidence >= self.min_confidence:
            return Signal(
                symbol=market_data.symbol,
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                price=current_price,
                timestamp=market_data.timestamp,
                metadata={
                    "upper_band": current_upper,
                    "middle_band": current_middle,
                    "lower_band": current_lower
                }
            )
        
        return None


class StrategyEngine:
    """Main strategy execution engine"""
    
    def __init__(self, exchange_manager, order_manager, risk_manager):
        self.exchange_manager = exchange_manager
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.logger = logging.getLogger("strategy_engine")
        
        # Strategy management
        self.strategies: Dict[str, Strategy] = {}
        self.symbols: List[str] = []
        self.timeframes: List[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]
        
        # Signal processing
        self.signal_history: List[Signal] = []
        self.on_signal: Optional[Callable[[Signal], None]] = None
        
        # Execution settings
        self.enabled = True
        self.signal_cooldown = 300  # 5 minutes between signals for same symbol
        self.last_signals: Dict[str, datetime] = {}
    
    def add_strategy(self, strategy: Strategy):
        """Add a strategy to the engine"""
        self.strategies[strategy.name] = strategy
        self.logger.info(f"Added strategy: {strategy.name}")
    
    def remove_strategy(self, name: str):
        """Remove a strategy from the engine"""
        if name in self.strategies:
            del self.strategies[name]
            self.logger.info(f"Removed strategy: {name}")
    
    def set_symbols(self, symbols: List[str]):
        """Set symbols to monitor"""
        self.symbols = symbols
        self.logger.info(f"Monitoring symbols: {symbols}")
    
    async def run_strategies(self, symbol: str, timeframe: str = "1m") -> List[Signal]:
        """Run all strategies for a symbol and timeframe"""
        if not self.enabled or not self.symbols:
            return []
        
        # Check cooldown
        cooldown_key = f"{symbol}_{timeframe}"
        if cooldown_key in self.last_signals:
            time_since_last = (datetime.now(timezone.utc) - self.last_signals[cooldown_key]).total_seconds()
            if time_since_last < self.signal_cooldown:
                return []
        
        # Fetch market data
        try:
            ohlcv_data = await self.exchange_manager.fetch_ohlcv(symbol, timeframe, limit=200)
            if not ohlcv_data:
                return []
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            
            market_data = MarketData(
                symbol=symbol,
                timeframe=timeframe,
                ohlcv=df,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            self.logger.error(f"Failed to fetch market data for {symbol}: {e}")
            return []
        
        # Run strategies
        signals = []
        for strategy in self.strategies.values():
            if not strategy.enabled:
                continue
            
            try:
                signal = await strategy.generate_signal(market_data)
                if signal and strategy.validate_signal(signal):
                    signals.append(signal)
                    self.signal_history.append(signal)
                    
                    # Notify callback
                    if self.on_signal:
                        self.on_signal(signal)
            
            except Exception as e:
                self.logger.error(f"Strategy {strategy.name} failed for {symbol}: {e}")
        
        # Update cooldown
        if signals:
            self.last_signals[cooldown_key] = datetime.now(timezone.utc)
        
        return signals
    
    async def run_all_symbols(self):
        """Run strategies for all symbols and timeframes"""
        tasks = []
        
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                task = asyncio.create_task(self.run_strategies(symbol, timeframe))
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_signal_statistics(self) -> Dict[str, Any]:
        """Get signal generation statistics"""
        if not self.signal_history:
            return {"total_signals": 0}
        
        total_signals = len(self.signal_history)
        buy_signals = len([s for s in self.signal_history if s.signal_type == SignalType.BUY])
        sell_signals = len([s for s in self.signal_history if s.signal_type == SignalType.SELL])
        
        avg_confidence = sum(s.confidence for s in self.signal_history) / total_signals
        
        strength_distribution = {}
        for strength in SignalStrength:
            count = len([s for s in self.signal_history if s.strength == strength])
            strength_distribution[strength.value] = count
        
        return {
            "total_signals": total_signals,
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "avg_confidence": avg_confidence,
            "strength_distribution": strength_distribution,
            "active_strategies": len([s for s in self.strategies.values() if s.enabled])
        }
    
    def start(self):
        """Start the strategy engine"""
        self.enabled = True
        self.logger.info("Strategy engine started")
    
    def stop(self):
        """Stop the strategy engine"""
        self.enabled = False
        self.logger.info("Strategy engine stopped")