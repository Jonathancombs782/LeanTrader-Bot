from __future__ import annotations
import os, time
from typing import List, Optional, Dict, Any
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

import ccxt  # type: ignore
from order_utils import place_market, safe_create_order

def _mk_exchange(name: str, testnet: bool) -> Any:
    api_key = os.getenv("CRYPTO_API_KEY") or ""
    secret  = os.getenv("CRYPTO_API_SECRET") or ""
    password = os.getenv("CRYPTO_API_PASSWORD") or None

    klass = getattr(ccxt, name)
    ex = klass({
        "apiKey": api_key,
        "secret": secret,
        "password": password,
        "enableRateLimit": True,
        "options": {},
    })
    # testnet routing for binance-like exchanges
    if name == "binance":
        ex.set_sandbox_mode(testnet)
    return ex

def ohlcv_df(exchange: str, symbol: str, timeframe: str, lookback_days: int, testnet: bool) -> pd.DataFrame:
    ex = _mk_exchange(exchange, testnet)
    # ccxt timeframes like '5m','1m','1h'
    limit = min(5000, lookback_days * (24*60 // max(1, int(timeframe[:-1]))))
    # prefer safe wrapper if available, otherwise guarded direct fetch
    rows = []
    try:
        if hasattr(ex, 'safe_fetch_ohlcv'):
            try:
                rows = ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            except Exception as e:
                print(f"[traders_core.connectors.crypto_ccxt] safe_fetch_ohlcv failed: {e}")
                rows = []
        else:
            try:
                rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            except Exception as e:
                print(f"[traders_core.connectors.crypto_ccxt] fetch_ohlcv failed: {e}")
                rows = []
    except Exception as e:
        print(f"[traders_core.connectors.crypto_ccxt] unexpected error: {e}")
        rows = []
    df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.set_index("time")

def ticker_price(exchange: str, symbol: str, testnet: bool) -> float:
    ex = _mk_exchange(exchange, testnet)
    try:
        # prefer safe wrapper but guard it
        if hasattr(ex, 'safe_fetch_ticker'):
            try:
                t = ex.safe_fetch_ticker(symbol)
            except Exception as e:
                print(f"[traders_core.connectors.crypto_ccxt] safe_fetch_ticker failed: {e}")
                t = {}
        else:
            try:
                t = ex.fetch_ticker(symbol)
            except Exception as e:
                print(f"[traders_core.connectors.crypto_ccxt] fetch_ticker failed: {e}")
                t = {}
        try:
            return float((t.get("last") if isinstance(t, dict) else None) or (t.get("close") if isinstance(t, dict) else None) or 0)
        except Exception:
            return 0.0
    except Exception:
        return 0.0

def market_buy(exchange: str, symbol: str, amount: float, testnet: bool) -> Dict[str,Any]:
    ex = _mk_exchange(exchange, testnet)
    try:
        if hasattr(ex, 'safe_place_order'):
            return ex.safe_place_order(symbol, "buy", amount)
        if hasattr(ex, 'create_market_buy_order'):
            try:
                return ex.create_market_buy_order(symbol, amount)
            except Exception:
                pass
        if hasattr(ex, 'create_order'):
            try:
                return safe_create_order(ex, 'market', symbol, 'buy', amount)
            except Exception as e:
                print(f"[traders_core.connectors.crypto_ccxt] safe_create_order buy failed: {e}")
        return place_market(ex, symbol, 'buy', amount)
    except Exception as e:
        return {"ok": False, "error": str(e)}

def market_sell(exchange: str, symbol: str, amount: float, testnet: bool) -> Dict[str,Any]:
    ex = _mk_exchange(exchange, testnet)
    try:
        if hasattr(ex, 'safe_place_order'):
            return ex.safe_place_order(symbol, "sell", amount)
        if hasattr(ex, 'create_market_sell_order'):
            try:
                return ex.create_market_sell_order(symbol, amount)
            except Exception:
                pass
        if hasattr(ex, 'create_order'):
            try:
                return safe_create_order(ex, 'market', symbol, 'sell', amount)
            except Exception as e:
                print(f"[traders_core.connectors.crypto_ccxt] safe_create_order sell failed: {e}")
        return place_market(ex, symbol, 'sell', amount)
    except Exception as e:
        return {"ok": False, "error": str(e)}

def market_info(exchange: str, symbol: str, testnet: bool) -> Dict[str,Any]:
    ex = _mk_exchange(exchange, testnet)
    try:
        if hasattr(ex, 'load_markets'):
            ex.load_markets()
    except Exception:
        pass
    m = getattr(ex, 'markets', {}).get(symbol) or {}
    return {
        "min_cost": float(m.get("limits",{}).get("cost",{}).get("min", 5.0)),     # e.g., ~10 USDT on Binance
        "min_qty":  float(m.get("limits",{}).get("amount",{}).get("min", 0.0001)),
        "step_qty": float(m.get("precision",{}).get("amount", 6)),  # we’ll round with precision decimals
        "price_prec": int(m.get("precision",{}).get("price", 2)),
        "amount_prec": int(m.get("precision",{}).get("amount", 6)),
        "taker": float(m.get("taker", 0.001)),
        "maker": float(m.get("maker", 0.001)),
    }
