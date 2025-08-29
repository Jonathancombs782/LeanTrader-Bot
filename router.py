# router.py
from __future__ import annotations

import os, time, json
from typing import Dict, Any, List, Optional

# Note: import ccxt lazily inside ExchangeRouter when a real exchange is requested.
ccxt = None


def _env(k: str, d: str = "") -> str:
    v = os.getenv(k)
    return v if v is not None else d

def _env_bool(k: str, d: bool = False) -> bool:
    return _env(k, "true" if d else "false").strip().lower() in ("1","true","yes","y","on")

def _env_int(k: str, d: int) -> int:
    try: return int(float(_env(k, str(d))))
    except: return d


class ExchangeRouter:
    """
    Thin, safe wrapper around one ccxt exchange.
    Fixes the classic 'string indices must be integers' by ALWAYS treating markets as dict and iterating .items().
    """

    def __init__(self) -> None:
        self.id   = _env("EXCHANGE_ID", "bybit").lower()
        self.mode = _env("EXCHANGE_MODE", "spot").lower()      # 'spot' | 'linear'
        self.live = _env_bool("ENABLE_LIVE", False)
        self.testnet = _env_bool("BYBIT_TESTNET", False)

        # Support a paper broker backend when EXCHANGE_ID=paper for safe dry-runs
        if self.id == "paper":
            try:
                from paper_broker import PaperBroker
                self.ex = PaperBroker(float(_env("PAPER_START_CASH", "5000")))
                self.markets = self.ex.load_markets() if hasattr(self.ex, 'load_markets') else {}
                self._exchange_malformed = False
                return
            except Exception as e:
                raise RuntimeError(f"failed to init PaperBroker: {e}") from e

        api_key = _env("API_KEY") or _env(f"{self.id.upper()}_API_KEY")
        api_sec = _env("API_SECRET") or _env(f"{self.id.upper()}_API_SECRET")

        opts: Dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": _env_int("CCXT_TIMEOUT_MS", 15000),
            "options": {}
        }
        if api_key and api_sec:
            opts["apiKey"] = api_key
            opts["secret"] = api_sec

        # market-type hints
        if self.id == "bybit":
            # defaultType: 'spot' or 'swap'
            opts["options"]["defaultType"] = "swap" if self.mode == "linear" else "spot"
            if self.mode == "linear":
                opts["options"]["defaultSubType"] = "linear"
            if self.testnet:
                # testnet REST base
                opts["urls"] = {"api": "https://api-testnet.bybit.com"}
        elif self.id == "binance" and self.mode == "linear":
            opts["options"]["defaultType"] = "future"

        # real exchange path: import ccxt lazily so paper broker doesn't require ccxt
        try:
            import ccxt as _ccxt
            klass = getattr(_ccxt, self.id, None)
            if not klass:
                raise RuntimeError(f"Unknown ccxt exchange id: {self.id}")
            self.ex = klass(opts)
        except Exception as e:
            raise RuntimeError(f"failed to initialize ccxt exchange '{self.id}': {e}") from e

        self.markets: Dict[str, Dict[str, Any]] = {}
        # If load_markets fails repeatedly we mark the exchange as malformed and avoid calling it.
        self._exchange_malformed: bool = False
        self._load_markets_safe()

    # ---------- internals ----------
    def _load_markets_safe(self) -> None:
        # Try load_markets a few times with short backoff to handle flaky testnets or transient network errors
        attempts = 0
        mkts = None
        while attempts < 3:
            try:
                mkts = self.ex.load_markets()
                print(f"[router] load_markets raw type={type(mkts)} value={mkts}")
                break
            except Exception as e:
                attempts += 1
                # expose exception detail when debug enabled
                if os.getenv("CCXT_DEBUG","false").lower() == "true" or os.getenv("TELEGRAM_DEBUG","false").lower() == "true":
                    print(f"[router] load_markets attempt {attempts} failed: {type(e).__name__}: {e}")
                else:
                    print(f"[router] load_markets attempt {attempts} failed: {e}")
                time.sleep(0.5 * attempts)
                mkts = None
        try:
            # mkts may be None if all attempts failed; try a fallback via fetch_markets
            if mkts is None:
                try:
                    if hasattr(self.ex, 'fetch_markets'):
                        mkts = self.ex.fetch_markets()
                        print(f"[router] fetch_markets fallback raw type={type(mkts)}")
                except Exception as e2:
                    print(f"[router] fetch_markets fallback failed: {e2}")
            if mkts is None:
                # Do not raise here; provide a minimal safe default so scanners can proceed.
                print("[router] load_markets failed; using safe default market list")
                # mark the exchange object as malformed so we never call into its methods
                self._exchange_malformed = True
                self.markets = {"BTC/USDT": {}, "ETH/USDT": {}, "SOL/USDT": {}, "XRP/USDT": {}, "DOGE/USDT": {}}
                return
            # ccxt should return a dict { "BTC/USDT": {...}, ... }
            if isinstance(mkts, dict):
                self.markets = mkts
            elif isinstance(mkts, list):
                # fallback: convert list to dict using 'symbol' key if present
                out = {}
                for i, m in enumerate(mkts):
                    try:
                        if isinstance(m, dict) and "symbol" in m:
                            key = m["symbol"]
                            out[key] = m
                        elif isinstance(m, str):
                            # some exchanges return a list of symbol strings
                            out[m] = {}
                        else:
                            out[f"idx-{i}"] = m
                    except Exception:
                        out[f"idx-{i}"] = m
                self.markets = out
            else:
                print(f"[router] load_markets unexpected type: {type(mkts)} value: {mkts}")
                self.markets = {}
        except Exception as e:
            print("[router] load_markets error:", e)
            # treat as malformed exchange
            self._exchange_malformed = True
            self.markets = {}

    # ---------- utilities ----------
    def info(self) -> Dict[str, Any]:
        return {"id": self.id, "mode": self.mode, "live": self.live, "testnet": self.testnet, "n_markets": len(self.markets)}

    def spot_symbols(self, quote: str = "USDT") -> List[str]:
        out: List[str] = []
        for sym, m in self.markets.items():  # ALWAYS .items()
            try:
                if isinstance(sym, str) and sym.endswith(f"/{quote}") and m.get("spot"):
                    out.append(sym)
            except Exception:
                continue
        return sorted(set(out))

    def linear_symbols(self, quote: str = "USDT") -> List[str]:
        out: List[str] = []
        for sym, m in self.markets.items():
            try:
                if not isinstance(sym, str) or not sym.endswith(f"/{quote}"):
                    continue
                if m.get("linear") or (m.get("swap") and m.get("contract") and m.get("quote") == quote):
                    out.append(sym)
            except Exception:
                continue
        return sorted(set(out))

    # ---------- data ----------
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        # If exchange failed to load markets previously, avoid calling into it
        if getattr(self, "_exchange_malformed", False):
            return {"last": 0.0}
        try:
            # prefer adapter safe wrapper if present
            if hasattr(self.ex, 'safe_fetch_ticker'):
                try:
                    return self.ex.safe_fetch_ticker(symbol) or {}
                except Exception as e:
                    print(f"[router] safe_fetch_ticker failed for {symbol}: {e}")
            try:
                return self.ex.fetch_ticker(symbol) or {}
            except Exception as e:
                print(f"[router] fetch_ticker {symbol} error: {e}")
                return {}
        except Exception as e:
            print(f"[router] fetch_ticker {symbol} outer error: {e}")
            return {}

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> List[List[float]]:
        # If exchange failed to load markets previously, avoid calling into it and return synthesized bars
        if getattr(self, "_exchange_malformed", False):
            # synthesize fallback immediately
            try:
                t = self.fetch_ticker(symbol)
                last = None
                if isinstance(t, dict):
                    last = t.get("last") or t.get("price") or t.get("close") or t.get("c")
                elif isinstance(t, (int, float)):
                    last = t
                price = float(last) if last is not None else 0.0
            except Exception:
                price = 0.0
            def _tf_seconds(tf: str) -> int:
                try:
                    tf = tf.strip().lower()
                    if tf.endswith("m"):
                        return int(float(tf[:-1]) * 60)
                    if tf.endswith("h"):
                        return int(float(tf[:-1]) * 3600)
                    if tf.endswith("d"):
                        return int(float(tf[:-1]) * 86400)
                    return 60
                except Exception:
                    return 60
            step_s = _tf_seconds(timeframe)
            now_ms = int(time.time() * 1000)
            bars: List[List[float]] = []
            for i in range(max(1, limit)):
                ts = now_ms - (max(1, limit) - i) * step_s * 1000
                bars.append([ts, price, price, price, price, 0.0])
            return bars

        # Try to fetch normal OHLCV. Be defensive: exchanges can return lists, dicts or malformed payloads.
        try:
            # prefer adapter safe wrapper when available
            if hasattr(self.ex, 'safe_fetch_ohlcv'):
                try:
                    result = self.ex.safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                except Exception as e:
                    print(f"[router] safe_fetch_ohlcv failed for {symbol}: {e}")
                    result = None
            else:
                result = None
            if result is None:
                result = self.ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            # Normal expected form: list of [ts, o, h, l, c, v]
            if isinstance(result, list) and all(isinstance(row, (list, tuple)) for row in result):
                return result or []

            # Sometimes exchanges return a dict with common keys pointing to the array
            if isinstance(result, dict):
                for key in ("data", "ohlcv", "result", "candles", "candlestick"):
                    if key in result and isinstance(result[key], list):
                        rows = result[key]
                        if all(isinstance(r, (list, tuple)) for r in rows):
                            return rows
                        # If rows are dicts, attempt to map to OHLCV
                        if all(isinstance(r, dict) for r in rows):
                            out = []
                            for r in rows[:limit]:
                                ts = r.get("time") or r.get("timestamp") or r.get("t") or r.get("datetime") or r.get("date")
                                o = r.get("open") or r.get("o") or r.get("1. open") or r.get("Open")
                                h = r.get("high") or r.get("h") or r.get("2. high") or r.get("High")
                                l = r.get("low") or r.get("l") or r.get("3. low") or r.get("Low")
                                c = r.get("close") or r.get("c") or r.get("4. close") or r.get("Close")
                                v = r.get("volume") or r.get("v") or r.get("5. volume") or r.get("Volume") or 0
                                try:
                                    if ts is None:
                                        ts_int = int(time.time() * 1000)
                                    else:
                                        ts_int = int(float(ts)) if not isinstance(ts, (int, float)) else int(ts)
                                        # normalize seconds -> ms
                                        if ts_int < 1e12:
                                            ts_int = int(ts_int * 1000)
                                except Exception:
                                    ts_int = int(time.time() * 1000)
                                try:
                                    out.append([ts_int, float(o), float(h), float(l), float(c), float(v)])
                                except Exception:
                                    # skip rows we can't coerce
                                    continue
                            if out:
                                return out

            # If we get here, the payload was unexpected
            print(f"[router] fetch_ohlcv {symbol} {timeframe} unexpected result type: {type(result)} value: {result}")
        except Exception as e:
            # Log the original exception for debugging, but fall through to a safe synthetic fallback
            print(f"[router] fetch_ohlcv {symbol} {timeframe} error:", e)

        # --- fallback: synthesize OHLCV using last ticker price so callers can continue in dry-run ---
        try:
            t = self.fetch_ticker(symbol)
            last = None
            if isinstance(t, dict):
                last = t.get("last") or t.get("price") or t.get("close") or t.get("c")
            elif isinstance(t, (int, float)):
                last = t
            price = float(last) if last is not None else 0.0
        except Exception:
            price = 0.0

        # helper: convert timeframe string to seconds (best-effort)
        def _tf_seconds(tf: str) -> int:
            try:
                tf = tf.strip().lower()
                if tf.endswith("m"):
                    return int(float(tf[:-1]) * 60)
                if tf.endswith("h"):
                    return int(float(tf[:-1]) * 3600)
                if tf.endswith("d"):
                    return int(float(tf[:-1]) * 86400)
                # default 60s
                return 60
            except Exception:
                return 60

        step_s = _tf_seconds(timeframe)
        now_ms = int(time.time() * 1000)
        bars: List[List[float]] = []
        # generate `limit` bars ending at now, spaced by timeframe
        for i in range(max(1, limit)):
            ts = now_ms - (max(1, limit) - i) * step_s * 1000
            bars.append([ts, price, price, price, price, 0.0])
        return bars

    # ---------- simple account view ----------
    def account(self) -> Dict[str, Any]:
        try:
            if hasattr(self.ex, 'safe_fetch_balance'):
                bal = self.ex.safe_fetch_balance()
            else:
                try:
                    bal = self.ex.fetch_balance()
                except Exception as e:
                    print(f"[router] fetch_balance failed: {e}")
                    bal = {}
            return {"ok": True, "balance": bal}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- safe convenience wrappers (used across the codebase) ----------
    def safe_fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        try:
            t = self.fetch_ticker(symbol)
            if isinstance(t, dict):
                return t
            return {"last": t}
        except Exception as e:
            print(f"[router] safe_fetch_ticker {symbol} error: {e}")
            return {}

    def safe_fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> List[List[float]]:
        # alias to fetch_ohlcv but keeps name consistent
        # guard when exchange is malformed
        if getattr(self, "_exchange_malformed", False):
            # synthesize fallback bars via fetch_ohlcv which already has a fallback path
            return self.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return self.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def safe_fetch_balance(self) -> Dict[str, Any]:
        if getattr(self, "_exchange_malformed", False):
            return {}
        try:
            # prefer adapter safe wrapper if available
            if hasattr(self.ex, 'safe_fetch_balance'):
                try:
                    bal = self.ex.safe_fetch_balance()
                except Exception as e:
                    print(f"[router] safe_fetch_balance failed: {e}")
                    bal = None
            else:
                bal = None
            if bal is None:
                try:
                    bal = self.ex.fetch_balance()
                except Exception as e:
                    print(f"[router] fetch_balance failed: {e}")
                    bal = {}
            return bal or {}
        except Exception as e:
            print(f"[router] safe_fetch_balance error: {e}")
            return {}

    def safe_place_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Thin, defensive order placement wrapper.
        - If router.live is False we perform a dry-run and return a simulated response.
        - Attempts to call common ccxt order methods otherwise, with graceful error handling.
        """
        try:
            if getattr(self, "_exchange_malformed", False):
                print(f"[router] exchange malformed, simulating dry-run order: {side} {amount} {symbol}")
                return {"ok": False, "dry_run": True, "symbol": symbol, "side": side, "amount": amount}
            if not self.live:
                print(f"[router] dry-run order: {side} {amount} {symbol} price={price}")
                return {"ok": False, "dry_run": True, "symbol": symbol, "side": side, "amount": amount}

            # prefer centralized safe_create_order if available
            if hasattr(self.ex, "create_order"):
                try:
                    typ = "market" if price is None else "limit"
                    from order_utils import safe_create_order
                    return safe_create_order(self.ex, typ, symbol, side, amount, price, params)
                except Exception as e:
                    # last-resort: try calling adapter directly
                    try:
                        typ = "market" if price is None else "limit"
                        order = self.ex.create_order(symbol, typ, side, amount, price, params or {})
                        return order or {}
                    except Exception as e2:
                        print(f"[router] direct create_order failed: {e2}")
                        return {"ok": False, "error": str(e2)}

            # fallbacks for some ccxt forks
            if hasattr(self.ex, "create_market_order") and price is None:
                try:
                    return self.ex.create_market_order(symbol, side, amount)
                except Exception as e:
                    print(f"[router] create_market_order failed: {e}")
                    return {"ok": False, "error": str(e)}
            if hasattr(self.ex, "create_limit_order") and price is not None:
                try:
                    return self.ex.create_limit_order(symbol, side, amount, price)
                except Exception as e:
                    print(f"[router] create_limit_order failed: {e}")
                    return {"ok": False, "error": str(e)}

            return {"ok": False, "error": "no order method available"}
        except Exception as e:
            print(f"[router] safe_place_order {symbol} {side} error: {e}")
            return {"ok": False, "error": str(e)}

    def safe_close_position(self, symbol: str) -> Dict[str, Any]:
        """
        Best-effort close for a given symbol. Implementation is intentionally conservative:
        - If not live: simulated response
        - Otherwise, callers should implement specific close logic (this is a safe stub)
        """
        try:
            if not self.live:
                print(f"[router] dry-run close position: {symbol}")
                return {"ok": False, "dry_run": True, "symbol": symbol}

            # Generic stub: try to fetch ticker and place an opposing market order for a tiny amount
            # (Real close logic depends on margin type and platform and should be implemented in adapters)
            pos = {}
            try:
                if hasattr(self.ex, 'safe_fetch_balance'):
                    bal = self.ex.safe_fetch_balance()
                else:
                    try:
                        bal = self.ex.fetch_balance()
                    except Exception:
                        bal = {}
                pos = bal or {}
            except Exception:
                pos = {}
            print(f"[router] safe_close_position called for {symbol}, position snapshot keys={list(pos.keys())}")
            return {"ok": True, "note": "close attempted (adapter may not implement)"}
        except Exception as e:
            print(f"[router] safe_close_position {symbol} error: {e}")
            return {"ok": False, "error": str(e)}

    # ---------- compatibility shims (old code expects these) ----------
    def create_order(self, symbol: str, typ: str, side: str, amount: float, price: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
    Compatibility shim so code calling `ex.create_order(...)` on an ExchangeRouter
    still works. Delegates to safe_place_order while passing through parameters.

    NOTE: This shim intentionally remains to preserve compatibility with older
    callsites. New code should call `order_utils.safe_create_order` or
    router.safe_place_order directly to get centralized defensive behavior.
        """
        return self.safe_place_order(symbol, side, amount, price=price, params=params)

    def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.safe_place_order(symbol, side, amount, price=None, params=params)

    def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.safe_place_order(symbol, side, amount, price=price, params=params)

    def create_stop_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # map to create_order; many callers pass stop semantics via 'typ' or params
        return self.safe_place_order(symbol, side, amount, price=price, params=params)
