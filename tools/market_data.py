
"""Ultra Advanced Market Data Management System.

This module provides a unified interface for OHLCV data management with
advanced caching, streaming, and multi-timeframe analysis capabilities.
"""

from __future__ import annotations

import json
import time
import pickle
import hashlib
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import queue

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class MarketDataManager:
    """Ultra-advanced market data management with caching and streaming."""
    
    def __init__(self, cache_dir: str = "runtime/market_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.redis_client = None
        
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)
                self.redis_client.ping()
            except:
                self.redis_client = None
    
    def get_cache_key(self, symbol: str, timeframe: str, limit: int) -> str:
        """Generate unique cache key."""
        return f"{symbol}_{timeframe}_{limit}_{int(time.time() // self.cache_ttl)}"
    
    def fetch_ohlcv(self, symbol: str, timeframe: str = '5m', limit: int = 500, 
                    exchange: Optional[str] = None) -> pd.DataFrame:
        """Fetch OHLCV data with intelligent caching."""
        cache_key = self.get_cache_key(symbol, timeframe, limit)
        
        # Check memory cache first
        if cache_key in self.memory_cache:
            return self.memory_cache[cache_key]
        
        # Check Redis cache
        if self.redis_client:
            try:
                cached = self.redis_client.get(cache_key)
                if cached:
                    df = pickle.loads(cached)
                    self.memory_cache[cache_key] = df
                    return df
            except:
                pass
        
        # Fetch fresh data
        df = self._fetch_fresh_ohlcv(symbol, timeframe, limit, exchange)
        
        # Cache the data
        self.memory_cache[cache_key] = df
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, self.cache_ttl, pickle.dumps(df))
            except:
                pass
        
        return df
    
    def _fetch_fresh_ohlcv(self, symbol: str, timeframe: str, limit: int,
                          exchange: Optional[str] = None) -> pd.DataFrame:
        """Fetch fresh OHLCV data from exchange."""
        try:
            from router import ExchangeRouter
            router = ExchangeRouter()
            rows = router.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            
            if not rows:
                # Return empty DataFrame with correct structure
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
            # Save to CSV for backup
            csv_path = self.cache_dir / f"{symbol.replace('/', '_')}_{timeframe}.csv"
            df.to_csv(csv_path, index=False)
            
            return df
            
        except Exception as e:
            print(f"[MarketData] Error fetching {symbol}: {e}")
            # Try to load from backup CSV
            csv_path = self.cache_dir / f"{symbol.replace('/', '_')}_{timeframe}.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    def get_multi_timeframe(self, symbol: str, timeframes: List[str] = None) -> Dict[str, pd.DataFrame]:
        """Fetch data for multiple timeframes."""
        if timeframes is None:
            timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        
        result = {}
        for tf in timeframes:
            limit = self._get_limit_for_timeframe(tf)
            result[tf] = self.fetch_ohlcv(symbol, tf, limit)
        
        return result
    
    def _get_limit_for_timeframe(self, timeframe: str) -> int:
        """Get appropriate limit for timeframe."""
        limits = {
            '1m': 1440,   # 1 day
            '5m': 576,    # 2 days
            '15m': 672,   # 1 week
            '1h': 720,    # 1 month
            '4h': 360,    # 2 months
            '1d': 365     # 1 year
        }
        return limits.get(timeframe, 500)
    
    def resample_ohlcv(self, df: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
        """Resample OHLCV data to different timeframe."""
        df = df.set_index('timestamp')
        
        # Map timeframe to pandas frequency
        freq_map = {
            '1m': '1T', '5m': '5T', '15m': '15T', '30m': '30T',
            '1h': '1H', '4h': '4H', '1d': '1D', '1w': '1W'
        }
        
        freq = freq_map.get(target_timeframe, '5T')
        
        resampled = df.resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return resampled.reset_index()
    
    def save_for_training(self, symbol: str, timeframe: str = '5m', days: int = 30) -> str:
        """Save OHLCV data in format suitable for trainer.py."""
        df = self.fetch_ohlcv(symbol, timeframe, days * 288)  # 288 5-min candles per day
        
        if df.empty:
            raise ValueError(f"No data available for {symbol}")
        
        # Convert to trainer format
        output_path = Path("runtime") / "training_data" / f"{symbol.replace('/', '_')}_{timeframe}.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save with columns expected by trainer
        df.to_csv(output_path, index=False)
        
        return str(output_path)


class StreamingDataManager:
    """Real-time streaming data manager for live trading."""
    
    def __init__(self):
        self.streams = {}
        self.callbacks = defaultdict(list)
        self.running = False
        self.data_queue = queue.Queue()
        
    def subscribe(self, symbol: str, callback: callable):
        """Subscribe to real-time updates for a symbol."""
        self.callbacks[symbol].append(callback)
        
        if symbol not in self.streams:
            self._start_stream(symbol)
    
    def _start_stream(self, symbol: str):
        """Start streaming for a symbol."""
        # This would connect to WebSocket in production
        # For now, simulate with periodic updates
        def stream_worker():
            while self.running:
                try:
                    # Simulate new candle every 5 seconds for testing
                    time.sleep(5)
                    
                    # Generate synthetic tick
                    tick = {
                        'symbol': symbol,
                        'timestamp': datetime.utcnow(),
                        'price': np.random.uniform(40000, 42000),  # Example for BTC
                        'volume': np.random.uniform(0.1, 2.0)
                    }
                    
                    # Notify callbacks
                    for callback in self.callbacks[symbol]:
                        callback(tick)
                        
                except Exception as e:
                    print(f"[Streaming] Error in stream for {symbol}: {e}")
        
        thread = threading.Thread(target=stream_worker, daemon=True)
        thread.start()
        self.streams[symbol] = thread
    
    def start(self):
        """Start all streams."""
        self.running = True
    
    def stop(self):
        """Stop all streams."""
        self.running = False


class MultiExchangeAggregator:
    """Aggregate data from multiple exchanges for better price discovery."""
    
    def __init__(self, exchanges: List[str] = None):
        if exchanges is None:
            exchanges = ['binance', 'coinbase', 'kraken']
        self.exchanges = exchanges
        self.weights = self._calculate_weights()
    
    def _calculate_weights(self) -> Dict[str, float]:
        """Calculate weights based on exchange volume/reliability."""
        # In production, fetch actual volumes
        default_weights = {
            'binance': 0.5,
            'coinbase': 0.3,
            'kraken': 0.2
        }
        return {ex: default_weights.get(ex, 0.1) for ex in self.exchanges}
    
    def get_aggregated_price(self, symbol: str) -> Dict[str, float]:
        """Get volume-weighted average price from multiple exchanges."""
        prices = []
        volumes = []
        
        for exchange in self.exchanges:
            try:
                # Fetch latest price from each exchange
                # This is simplified - in production use actual exchange APIs
                price = np.random.uniform(40000, 42000)  # Simulated
                volume = np.random.uniform(100, 1000)
                
                prices.append(price)
                volumes.append(volume)
            except:
                continue
        
        if not prices:
            return {'price': 0, 'volume': 0, 'confidence': 0}
        
        # Volume-weighted average
        total_volume = sum(volumes)
        vwap = sum(p * v for p, v in zip(prices, volumes)) / total_volume
        
        # Calculate confidence based on price spread
        spread = (max(prices) - min(prices)) / vwap
        confidence = max(0, 1 - spread * 10)  # Lower confidence with higher spread
        
        return {
            'price': vwap,
            'volume': total_volume,
            'confidence': confidence,
            'spread': spread,
            'exchanges': len(prices)
        }


# Singleton instances
_market_data_manager = None
_streaming_manager = None
_aggregator = None


def get_market_data_manager() -> MarketDataManager:
    """Get singleton market data manager."""
    global _market_data_manager
    if _market_data_manager is None:
        _market_data_manager = MarketDataManager()
    return _market_data_manager


def get_streaming_manager() -> StreamingDataManager:
    """Get singleton streaming manager."""
    global _streaming_manager
    if _streaming_manager is None:
        _streaming_manager = StreamingDataManager()
    return _streaming_manager


def get_aggregator() -> MultiExchangeAggregator:
    """Get singleton aggregator."""
    global _aggregator
    if _aggregator is None:
        _aggregator = MultiExchangeAggregator()
    return _aggregator


# Convenience functions for backward compatibility
def fetch_ohlcv(symbol: str, timeframe: str = '5m', limit: int = 500) -> pd.DataFrame:
    """Fetch OHLCV data."""
    return get_market_data_manager().fetch_ohlcv(symbol, timeframe, limit)


def save_training_data(symbol: str, timeframe: str = '5m', days: int = 30) -> str:
    """Save data for training."""
    return get_market_data_manager().save_for_training(symbol, timeframe, days)
"""Simple market data fetcher using ccxt.

This module provides safe, opt-in helpers to fetch historical OHLCV and
persist to CSV under `runtime/data/`. It is intentionally conservative and
does not perform any live trading.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# A small mapping of common friendly names to ccxt exchange ids. Users can
# pass either the key or the ccxt id. This keeps things flexible and "universal".
EXCHANGE_ALIASES = {
    "binance": "binance",
    "bybit": "bybit",
    "gateio": "gateio",
    "kucoin": "kucoin",
    "coinbase": "coinbasepro",
    "coinbasepro": "coinbasepro",
    "okx": "okx",
    "okex": "okx",
}


def _ensure_runtime_dir() -> Path:
    p = Path("runtime") / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1m",
    since: Optional[int] = None,
    limit: int = 1000,
    timeout_ms: int = 30_000,
) -> List[List[float]]:
    """Fetch OHLCV via ccxt. Returns list of rows [ts, o, h, l, c, v].

    This function requires `ccxt` to be installed. It is safe to call in a
    non-live environment; it only reads market data.
    """
    try:
        import ccxt  # type: ignore
    except Exception as e:
        raise RuntimeError("ccxt is required for market data fetching") from e

    # resolve alias
    exch_key = EXCHANGE_ALIASES.get(exchange_id.lower(), exchange_id.lower())

    ex_cls = getattr(ccxt, exch_key, None)
    if ex_cls is None:
        # some environments expose ccxt.exchange classes under different names
        # fall back to ccxt.Exchange and instantiate by id using ccxt's factory
        try:
            ex = ccxt.__dict__.get(exch_key)
        except Exception:
            ex = None
        if ex is None:
            raise RuntimeError(f"unknown exchange id or alias: {exchange_id}")
    else:
        opts = {"enableRateLimit": True, "timeout": int(timeout_ms)}
        ex = ex_cls(opts)

    # Try several common symbol variants to increase compatibility across
    # exchanges (some use different separators or market ids).
    def _symbol_variants(s: str) -> List[str]:
        s = s.strip()
        variants = [s]
        if "/" in s:
            base, quote = s.split("/", 1)
            variants.extend(
                [
                    f"{base}{quote}",  # BTCUSDT
                    f"{base}-{quote}",  # BTC-USDT
                    f"{base}_{quote}",  # BTC_USDT
                    f"{base}/{quote}:USDT" if quote.upper() == "USDT" else f"{base}/{quote}",
                ]
            )
        else:
            # if user passed BTCUSDT, try BTC/USDT
            if len(s) >= 6:
                variants.append(s[:3] + "/" + s[3:])
        # de-duplicate while preserving order
        out_vars: List[str] = []
        for v in variants:
            if v not in out_vars:
                out_vars.append(v)
        return out_vars

    params: Dict[str, Any] = {}
    if since is not None:
        params["since"] = since

    out: List[List[float]] = []
    attempt = 0
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        for try_sym in _symbol_variants(symbol):
            try:
                out = ex.fetch_ohlcv(try_sym, timeframe=timeframe, limit=limit, params=params)  # type: ignore
                # on success, persist using the original safe_sym naming
                attempt = 0
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                # try next variant
                time.sleep(0.1)
                continue
        if out:
            break
        # small backoff before full retry cycle
        time.sleep(0.5 * attempt)
    if not out and last_exc is not None:
        raise last_exc

    # persist to CSV for later use
    runtime = _ensure_runtime_dir()
    safe_sym = symbol.replace("/", "_")
    fname = runtime / f"{exchange_id}_{safe_sym}_{timeframe}.csv"
    try:
        with fname.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "open", "high", "low", "close", "vol"])
            for row in out:
                writer.writerow(row)
    except Exception:
        # ignore persistence errors
        pass
    return out


def fetch_ohlcv_multi(
    exchange_ids: List[str],
    symbol: str,
    timeframe: str = "1m",
    since: Optional[int] = None,
    limit: int = 1000,
    timeout_ms: int = 30_000,
) -> Tuple[str, List[List[float]]]:
    """Try multiple exchanges in order, return (exchange_used, rows).

    Useful when you want a universal fallback across exchanges that list the
    same market under slightly different ids.
    """
    last_exc: Optional[Exception] = None
    for ex in exchange_ids:
        try:
            rows = fetch_ohlcv(ex, symbol, timeframe=timeframe, since=since, limit=limit, timeout_ms=timeout_ms)
            return ex, rows
        except Exception as e:
            last_exc = e
            continue
    # if none succeeded, raise the last exception
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("no exchanges provided")


def load_csv(exchange_id: str, symbol: str, timeframe: str = "1m") -> List[List[float]]:
    runtime = Path("runtime") / "data"
    safe_sym = symbol.replace("/", "_")
    fname = runtime / f"{exchange_id}_{safe_sym}_{timeframe}.csv"
    if not fname.exists():
        return []
    out: List[List[float]] = []
    with fname.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            try:
                out.append([int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
            except Exception:
                continue
    return out
