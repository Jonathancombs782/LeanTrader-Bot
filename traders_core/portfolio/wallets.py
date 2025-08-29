from __future__ import annotations
import os
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv()

from traders_core.connectors.crypto_ccxt import _mk_exchange
from traders_core.mt5_adapter import account_info

def crypto_wallet_usd(exchange_name: str, testnet: bool = True) -> float:
    ex = _mk_exchange(exchange_name, testnet)
    try:
        if hasattr(ex, 'safe_fetch_balance'):
            bal = ex.safe_fetch_balance()
        else:
            try:
                bal = ex.fetch_balance()
            except Exception:
                bal = {}
    except Exception:
        bal = {}
    # prefer USDT; fallback to total USD estimated if supported
    usdt = bal.get("USDT", {})
    free = float(usdt.get("free", 0.0) or 0.0)
    if free == 0.0 and "total" in bal:
        try:
            return float(bal["total"].get("USD", 0.0))
        except Exception:
            pass
    return free

def mt5_equity_usd() -> float:
    try:
        ai = account_info()
        return float(getattr(ai, "equity", 0.0) or getattr(ai, "balance", 0.0) or 0.0)
    except Exception:
        return 0.0
