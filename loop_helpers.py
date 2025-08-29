# loop_helpers.py
from __future__ import annotations
import os, time
from typing import Optional, Dict, Any, List

from notifier import TelegramNotifier

# We use your existing portfolio helpers (file renamed to acct_portfolio)
from acct_portfolio import ccxt_summary, mt5_summary

def _has_api_keys() -> bool:
    return bool((os.getenv("API_KEY") or "").strip()) and bool((os.getenv("API_SECRET") or "").strip())

def maybe_post_balance(notif: TelegramNotifier,
                       exchange_or_kind: Any,
                       seconds_every: int = 3600,
                       state: Optional[Dict[str, Any]] = None,
                       prefer: str = "auto"):
    """
    Throttled portfolio snapshot to Telegram.
    - If `exchange_or_kind` is a ccxt exchange instance => crypto summary
    - If `exchange_or_kind` == 'mt5' or 'fx'            => MT5 summary
    - Skips crypto summary if API keys are missing (to avoid spam like "requires apiKey")
    """
    state = state or {}
    now = time.time()
    last = float(state.get("last_balance_ts", 0))
    if seconds_every <= 0 or now - last < seconds_every:
        return state  # too soon / disabled

    try:
        lines: List[str] = []
        if prefer == "mt5" or str(exchange_or_kind).lower() in ("mt5", "fx"):
            lines = mt5_summary()
        else:
            # crypto path
            if _has_api_keys():
                lines = ccxt_summary(exchange=exchange_or_kind)
            else:
                notif.note("portfolio unavailable: set API_KEY/API_SECRET to enable balance.")
                state["last_balance_ts"] = now
                return state

        if lines:
            notif.balance_snapshot(lines)
    except Exception as e:
        notif.note(f"portfolio snapshot error: {e}")

    state["last_balance_ts"] = now
    return state
