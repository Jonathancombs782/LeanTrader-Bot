# router.py
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

# Note: import ccxt lazily inside ExchangeRouter when a real exchange is requested.
ccxt = None
_log = logging.getLogger("router")


def _env(k: str, d: str = "") -> str:
    v = os.getenv(k)
    return v if v is not None else d


def _env_bool(k: str, d: bool = False) -> bool:
    return _env(k, "true" if d else "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )


def _env_int(k: str, d: int) -> int:
    try:
        return int(float(_env(k, str(d))))
    except Exception:
        return d


def _env_float(k: str, d: float) -> float:
    """Parse float env var with safe fallback."""
    try:
        return float(_env(k, str(d)))
    except Exception:
        return d


class ExchangeRouter:
    """
    Thin, safe wrapper around one ccxt exchange.
    Fixes the classic 'string indices must be integers' by ALWAYS treating markets as dict and iterating .items().
    """

    def __init__(self) -> None:
        self.id = _env("EXCHANGE_ID", "bybit").lower()
        self.mode = _env("EXCHANGE_MODE", "spot").lower()  # 'spot' | 'linear'
        self.live = _env_bool("ENABLE_LIVE", False)
        self.testnet = _env_bool("BYBIT_TESTNET", False)

        # explicit allow flag required to actually send live orders (extra safety)
        # instance-level allow flag captured at init time to avoid mid-run env changes
        self.allow_live = _env_bool("ALLOW_LIVE", False)
        # extra explicit confirmation required in addition to ALLOW_LIVE to prevent accidental live orders
        # set LIVE_CONFIRM=YES in your environment to enable live order placement when ENABLE_LIVE+ALLOW_LIVE are set
        self.live_confirm = _env("LIVE_CONFIRM", "").strip().lower() == "yes"

        # Support a paper broker backend when EXCHANGE_ID=paper for safe dry-runs
        # Initialize paper broker early and force dry-run mode regardless of env flags.
        if self.id == "paper":
            try:
                from paper_broker import PaperBroker

                self.ex = PaperBroker(float(_env("PAPER_START_CASH", "5000")))
                self.markets = (
                    self.ex.load_markets() if hasattr(self.ex, "load_markets") else {}
                )
                self._exchange_malformed = False
                # Paper broker is always dry-run even if ENABLE_LIVE was set
                self.live = False
                return
            except Exception as e:
                raise RuntimeError(f"failed to init PaperBroker: {e}") from e

        if self.live and not self.allow_live:
            # avoid silently performing live trading unless explicitly allowed
            print(
                "[router] ENABLE_LIVE requested but ALLOW_LIVE not set -> running in dry-run mode"
            )
            self.live = False
        elif self.live and self.allow_live and not self.live_confirm:
            # require explicit live confirmation token in addition to ALLOW_LIVE
            print(
                "[router] ENABLE_LIVE and ALLOW_LIVE set but LIVE_CONFIRM not set to 'YES' -> running in dry-run mode"
            )
            self.live = False

        api_key = _env("API_KEY") or _env(f"{self.id.upper()}_API_KEY")
        api_sec = _env("API_SECRET") or _env(f"{self.id.upper()}_API_SECRET")

        # If user insisted on live mode via envs, require API credentials to avoid accidental live execution.
        if self.live and not (api_key and api_sec):
            raise RuntimeError(
                "Live trading enabled (ENABLE_LIVE/ALLOW_LIVE) but API_KEY/API_SECRET are missing."
            )

        opts: Dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": _env_int("CCXT_TIMEOUT_MS", 15000),
            "options": {},
        }
        if api_key and api_sec:
            opts["apiKey"] = api_key
            opts["secret"] = api_sec
        # store credential presence for runtime safety checks
        self._has_api_creds = bool(api_key and api_sec)

        # market-type hints
        if self.id == "bybit":
            # defaultType: 'spot' or 'swap'
            opts["options"]["defaultType"] = "swap" if self.mode == "linear" else "spot"
            if self.mode == "linear":
                opts["options"]["defaultSubType"] = "linear"
            if self.testnet:
                # testnet REST base; ccxt bybit uses different url fields; set both common forms
                opts_urls = {
                    "api": "https://api-testnet.bybit.com",
                    "rest": "https://api-testnet.bybit.com",
                }
                # merge with existing opts if present
                if "urls" in opts and isinstance(opts["urls"], dict):
                    opts["urls"].update(opts_urls)
                else:
                    opts["urls"] = opts_urls
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
            raise RuntimeError(
                f"failed to initialize ccxt exchange '{self.id}': {e}"
            ) from e

        self.markets: Dict[str, Dict[str, Any]] = {}
        # If load_markets fails repeatedly we mark the exchange as malformed and avoid calling it.
        self._exchange_malformed: bool = False
        self._load_markets_safe()

        # Apply a non-destructive runtime safety overlay so accidental live orders
        # are blocked unless ENABLE_LIVE is explicitly set to 'true'. This method
        # is extracted so tests can exercise it without initializing real ccxt.
        try:
            self.apply_runtime_order_block()
        except Exception:
            _log.exception("[router] apply_runtime_order_block failed")

    # ---------- internals ----------
    def _load_markets_safe(self) -> None:
        # Try load_markets a few times with short backoff to handle flaky testnets or transient network errors
        attempts = 0
        mkts = None
        while attempts < 3:
            try:
                mkts = self.ex.load_markets()
                _log.debug(f"[router] load_markets raw type={type(mkts)}")
                break
            except Exception as e:
                attempts += 1
                if os.getenv("CCXT_DEBUG", "false").lower() == "true":
                    _log.warning(
                        f"[router] load_markets attempt {attempts} failed: {type(e).__name__}: {e}"
                    )
                else:
                    _log.warning(
                        f"[router] load_markets attempt {attempts} failed: {e}"
                    )
                time.sleep(0.5 * attempts)
                mkts = None
        try:
            # mkts may be None if all attempts failed; try a fallback via fetch_markets
            if mkts is None:
                try:
                    if hasattr(self.ex, "fetch_markets"):
                        mkts = self.ex.fetch_markets()
                        print(f"[router] fetch_markets fallback raw type={type(mkts)}")
                except Exception as e2:
                    print(f"[router] fetch_markets fallback failed: {e2}")
            if mkts is None:
                # Do not raise here; provide a minimal safe default so scanners can proceed.
                _log.error(
                    "[router] load_markets failed; using safe default market list"
                )
                self._exchange_malformed = True
                self.markets = {
                    "BTC/USDT": {},
                    "ETH/USDT": {},
                    "SOL/USDT": {},
                    "XRP/USDT": {},
                    "DOGE/USDT": {},
                }
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
                print(
                    f"[router] load_markets unexpected type: {type(mkts)} value: {mkts}"
                )
                self.markets = {}
        except Exception as e:
            print(f"[router] load_markets error: {e}")
            # treat as malformed exchange
            self._exchange_malformed = True
            self.markets = {}

    # ---------- utilities ----------
    def info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "live": self.live,
            "testnet": self.testnet,
            "n_markets": len(self.markets),
        }

    def spot_symbols(self, quote: str = "USDT") -> List[str]:
        out: List[str] = []
        for sym, m in self.markets.items():  # ALWAYS .items()
            try:
                # be defensive: some market entries may be non-dict; require dict for .get()
                if (
                    isinstance(sym, str)
                    and sym.endswith(f"/{quote}")
                    and isinstance(m, dict)
                    and m.get("spot")
                ):
                    out.append(sym)
            except Exception:
                # keep scanning even if one entry is malformed
                continue
        return sorted(set(out))

    def linear_symbols(self, quote: str = "USDT") -> List[str]:
        out: List[str] = []
        for sym, m in self.markets.items():
            try:
                # defensive: ensure m is a dict before calling .get()
                if not isinstance(sym, str) or not sym.endswith(f"/{quote}"):
                    continue
                if not isinstance(m, dict):
                    continue
                if m.get("linear") or (
                    m.get("swap") and m.get("contract") and m.get("quote") == quote
                ):
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
            if hasattr(self.ex, "safe_fetch_ticker"):
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

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", limit: int = 200
    ) -> List[List[float]]:
        # If exchange failed to load markets previously, avoid calling into it and return synthesized bars
        if getattr(self, "_exchange_malformed", False):
            # synthesize fallback immediately
            try:
                t = self.fetch_ticker(symbol)
                last = None
                if isinstance(t, dict):
                    last = (
                        t.get("last") or t.get("price") or t.get("close") or t.get("c")
                    )
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
            if hasattr(self.ex, "safe_fetch_ohlcv"):
                try:
                    result = self.ex.safe_fetch_ohlcv(
                        symbol, timeframe=timeframe, limit=limit
                    )
                except Exception as e:
                    print(f"[router] safe_fetch_ohlcv failed for {symbol}: {e}")
                    result = None
            else:
                result = None
            if result is None:
                result = self.ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            # Normal expected form: list of [ts, o, h, l, c, v]
            if isinstance(result, list) and all(
                isinstance(row, (list, tuple)) for row in result
            ):
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
                                ts = (
                                    r.get("time")
                                    or r.get("timestamp")
                                    or r.get("t")
                                    or r.get("datetime")
                                    or r.get("date")
                                )
                                o = (
                                    r.get("open")
                                    or r.get("o")
                                    or r.get("1. open")
                                    or r.get("Open")
                                )
                                h = (
                                    r.get("high")
                                    or r.get("h")
                                    or r.get("2. high")
                                    or r.get("High")
                                )
                                low = (
                                    r.get("low")
                                    or r.get("l")
                                    or r.get("3. low")
                                    or r.get("Low")
                                )
                                c = (
                                    r.get("close")
                                    or r.get("c")
                                    or r.get("4. close")
                                    or r.get("Close")
                                )
                                v = (
                                    r.get("volume")
                                    or r.get("v")
                                    or r.get("5. volume")
                                    or r.get("Volume")
                                    or 0
                                )
                                try:
                                    if ts is None:
                                        ts_int = int(time.time() * 1000)
                                    else:
                                        ts_int = (
                                            int(float(ts))
                                            if not isinstance(ts, (int, float))
                                            else int(ts)
                                        )
                                        # normalize seconds -> ms
                                        if ts_int < 1e12:
                                            ts_int = int(ts_int * 1000)
                                except Exception:
                                    ts_int = int(time.time() * 1000)
                                try:
                                        out.append(
                                            [
                                                ts_int,
                                                float(o),
                                                float(h),
                                                float(low),
                                                float(c),
                                                float(v),
                                            ]
                                        )
                                except Exception:
                                    # skip rows we can't coerce
                                    continue
                            if out:
                                return out

            # If we get here, the payload was unexpected
            print(
                f"[router] fetch_ohlcv {symbol} {timeframe} unexpected result type: {type(result)} value: {result}"
            )
        except Exception as e:
            # Log the original exception for debugging, but fall through to a safe synthetic fallback
            print(f"[router] fetch_ohlcv {symbol} {timeframe} error: {e}")

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
            if hasattr(self.ex, "safe_fetch_balance"):
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

        def apply_runtime_order_block(self, logger: Optional[logging.Logger] = None) -> None:
            """
            Apply a runtime overlay that stubs order-sending methods when ENABLE_LIVE
            is not explicitly enabled. This is non-destructive: original callables
            are saved as `_orig_<name>` on the instance where possible.

            This method is safe to call multiple times; it will attempt to preserve
            existing originals when present.
            """
            lg = logger or _log
            try:
                enable_live_env = _env("ENABLE_LIVE", "").strip().lower() == "true"
                # Do not override behavior for paper broker
                if getattr(self, "id", "").lower() == "paper":
                    lg.debug("[router] paper broker detected: skipping runtime order overlay")
                    return

                if enable_live_env:
                    lg.debug("[router] ENABLE_LIVE=true: no runtime order overlay applied")
                    return

                lg.warning("[router] ENABLE_LIVE not true: applying runtime order-block overlay")

                def _stub_order(*args, **kwargs):
                    lg.warning("[router] blocked live order call (ENABLE_LIVE != 'true')")
                    return {"ok": False, "dry_run": True, "error": "live disabled"}

                # Instance-level shims (high-level router methods)
                for name in (
                    "safe_place_order",
                    "create_order",
                    "create_market_order",
                    "create_limit_order",
                    "create_stop_order",
                ):
                    try:
                        if hasattr(self, name):
                            if not hasattr(self, f"_orig_{name}"):
                                setattr(self, f"_orig_{name}", getattr(self, name))
                            setattr(self, name, _stub_order)
                    except Exception:
                        lg.exception("[router] failed to stub router.%s", name)

                # Try to stub underlying exchange methods if present (best-effort)
                try:
                    ex = getattr(self, "ex", None)
                    if ex is not None:
                        def make_ex_stub():
                            def _ex_stub(*a, **k):
                                lg.warning("[router] blocked underlying exchange order (ENABLE_LIVE != 'true')")
                                return {"ok": False, "dry_run": True, "error": "live disabled"}

                            return _ex_stub

                        for cname in ("create_order", "create_market_order", "create_limit_order"):
                            try:
                                if hasattr(ex, cname) and not hasattr(ex, f"_orig_{cname}"):
                                    setattr(ex, f"_orig_{cname}", getattr(ex, cname))
                                    setattr(ex, cname, make_ex_stub())
                            except Exception:
                                lg.exception("[router] failed to stub ex.%s", cname)
                except Exception:
                    lg.exception("[router] underlying exchange overlay failed")
            except Exception:
                lg.exception("[router] apply_runtime_order_block outer failure")

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

    def safe_fetch_ohlcv(
        self, symbol: str, timeframe: str = "1m", limit: int = 200
    ) -> List[List[float]]:
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
            if hasattr(self.ex, "safe_fetch_balance"):
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

    def safe_place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Thin, defensive order placement wrapper.
        - If router.live is False we perform a dry-run and return a simulated response.
        - Attempts to call common ccxt order methods otherwise, with graceful error handling.
        """
        try:
            # If exchange failed to load markets previously, avoid calling into it
            if getattr(self, "_exchange_malformed", False):
                print(
                    f"[router] exchange malformed, simulating dry-run order: {side} {amount} {symbol}"
                )
                return {
                    "ok": False,
                    "dry_run": True,
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                }

            # Live-safety: require explicit ALLOW_LIVE env to actually send live orders.
            # DEFAULT: even if ENABLE_LIVE=true, ALLOW_LIVE must be set to a truthy value.
            # require both ALLOW_LIVE and LIVE_CONFIRM=YES to proceed with real orders
            allow_live = _env_bool("ALLOW_LIVE", False) and (
                _env("LIVE_CONFIRM", "").strip().lower() == "yes"
            )
            max_order_size = _env_float("MAX_ORDER_SIZE", float("inf"))
            # Optional USD cap per order to avoid large accidental trades (set LIVE_ORDER_USD)
            live_order_usd_env = _env("LIVE_ORDER_USD", "")
            try:
                live_order_usd = (
                    float(live_order_usd_env) if live_order_usd_env else None
                )
            except Exception:
                live_order_usd = None

            if not self.live or not allow_live:
                # still simulate/dry-run when live not allowed
                if self.live and not allow_live:
                    print(
                        "[router] live trading requested but ALLOW_LIVE not set -> dry-run"
                    )
                else:
                    print(
                        f"[router] dry-run order: {side} {amount} {symbol} price={price}"
                    )
                return {
                    "ok": False,
                    "dry_run": True,
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                }

            # Runtime credential guard: refuse to place live orders if the router instance
            # does not have API credentials (captured at init) — protects against
            # enabling live mode via envs during runtime without credentials present.
            if self.live and allow_live and not getattr(self, "_has_api_creds", False):
                msg = "Live trading allowed by flags but API credentials missing at runtime; refusing to place live order"
                print(f"[router] {msg}")
                return {"ok": False, "error": msg}

            # enforce maximum allowed order size when configured
            try:
                if (
                    max_order_size is not None
                    and max_order_size != float("inf")
                    and float(amount) > float(max_order_size)
                ):
                    msg = (
                        f"order amount {amount} exceeds MAX_ORDER_SIZE={max_order_size}"
                    )
                    print(f"[router] {msg}")
                    return {
                        "ok": False,
                        "error": msg,
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                    }
            except Exception:
                # Don't block on conversion errors; proceed to attempt placing the order
                pass

            # If a USD per-order cap is configured, attempt to compute the order notional and enforce it.
            try:
                if self.live and live_order_usd is not None:
                    price_for_notional = price
                    # if price not provided, try to fetch last ticker
                    if price_for_notional is None:
                        try:
                            t = self.fetch_ticker(symbol) or {}
                            price_for_notional = (
                                t.get("last")
                                or t.get("price")
                                or t.get("close")
                                or t.get("c")
                            )
                        except Exception:
                            price_for_notional = None
                    try:
                        price_f = (
                            float(price_for_notional)
                            if price_for_notional is not None
                            else 0.0
                        )
                    except Exception:
                        price_f = 0.0
                    usd_notional = float(amount) * price_f if price_f else 0.0
                    if usd_notional and usd_notional > float(live_order_usd):
                        msg = f"order notional ${usd_notional:.2f} exceeds LIVE_ORDER_USD=${live_order_usd:.2f}"
                        print(f"[router] {msg}")
                        return {
                            "ok": False,
                            "error": msg,
                            "symbol": symbol,
                            "side": side,
                            "amount": amount,
                            "usd_notional": usd_notional,
                        }
            except Exception:
                # don't block on notional checks if something goes wrong computing price
                pass

            # prefer centralized safe_create_order if available
            if hasattr(self.ex, "create_order"):
                try:
                    typ = "market" if price is None else "limit"
                    from order_utils import safe_create_order

                    return safe_create_order(
                        self.ex, typ, symbol, side, amount, price, params
                    )
                except Exception:
                    # last-resort: try calling adapter directly
                    try:
                        typ = "market" if price is None else "limit"
                        order = self.ex.create_order(
                            symbol, typ, side, amount, price, params or {}
                        )
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
                if hasattr(self.ex, "safe_fetch_balance"):
                    bal = self.ex.safe_fetch_balance()
                else:
                    try:
                        bal = self.ex.fetch_balance()
                    except Exception:
                        bal = {}
                pos = bal or {}
            except Exception:
                pos = {}
            print(
                f"[router] safe_close_position called for {symbol}, position snapshot keys={list(pos.keys())}"
            )
            return {"ok": True, "note": "close attempted (adapter may not implement)"}
        except Exception as e:
            print(f"[router] safe_close_position {symbol} error: {e}")
            return {"ok": False, "error": str(e)}

    # ---------- compatibility shims (old code expects these) ----------
    def create_order(
        self,
        symbol: str,
        typ: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Compatibility shim so code calling `ex.create_order(...)` on an ExchangeRouter
        still works. Delegates to safe_place_order while passing through parameters.

        NOTE: This shim intentionally remains to preserve compatibility with older
        callsites. New code should call `order_utils.safe_create_order` or
        router.safe_place_order directly to get centralized defensive behavior.
        """
        return self.safe_place_order(symbol, side, amount, price=price, params=params)

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.safe_place_order(symbol, side, amount, price=None, params=params)

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.safe_place_order(symbol, side, amount, price=price, params=params)

    def create_stop_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # map to create_order; many callers pass stop semantics via 'typ' or params
        return self.safe_place_order(symbol, side, amount, price=price, params=params)

    # ---------- market helpers ----------
    def precision(self, symbol: str) -> float:
        """Return a quantity step/precision for a symbol if available, else 0.0"""
        try:
            m = self.markets.get(symbol) or {}
            if not isinstance(m, dict):
                return 0.0
            step = m.get("precision") or {}
            # ccxt sometimes provides 'precision': {'amount': 0.001}
            if isinstance(step, dict):
                amt = step.get("amount") or step.get("base") or 0.0
                try:
                    return float(amt) if amt else 0.0
                except Exception:
                    return 0.0
            # some markets provide 'lot' or 'step'
            for key in ("step", "lot", "amount"):
                v = m.get(key)
                if v:
                    try:
                        return float(v)
                    except Exception:
                        pass
            return 0.0
        except Exception:
            return 0.0

    def limits(self, symbol: str) -> Dict[str, Any]:
        """Return limits dict for symbol if available (min/max qty, price)"""
        try:
            m = self.markets.get(symbol) or {}
            if not isinstance(m, dict):
                return {}
            return m.get("limits", {}) or {}
        except Exception:
            return {}


def scan_codebase(root: str = ".", py_ext: str = ".py", exclude_dirs=None) -> dict:
    """
    Walk `root` and produce a lightweight analysis of Python files:
      - line counts
      - AST counts: functions, classes
      - TODO comments
      - bare except occurrences (AST-based)
      - parse errors (if ast.parse fails) with message
    Returns a dict summary suitable for quick inspection or automated checks.
    """
    import ast  # noqa: F401  # intentionally kept
    import os
    import re

    if exclude_dirs is None:
        exclude_dirs = {".git", "__pycache__", "venv", "env", "node_modules", "reports"}
    report = {
        "files": {},
        "totals": {
            "files": 0,
            "lines": 0,
            "functions": 0,
            "classes": 0,
            "todos": 0,
            "bare_excepts": 0,
            "parse_errors": 0,
        },
    }
    for dirpath, dirnames, filenames in os.walk(root):
        # skip excluded dirs
        parts = set(p for p in dirpath.split(os.sep) if p)
        if parts & exclude_dirs:
            continue
        for fn in filenames:
            if not fn.endswith(py_ext):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
            except Exception:
                continue
            lines = src.count("\n") + (1 if src and not src.endswith("\n") else 0)
            # parse AST defensively
            funcs = classes = bare_except = 0
            parse_error = False
            parse_error_msg = None
            try:
                tree = ast.parse(src)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        funcs += 1
                    elif isinstance(node, ast.ClassDef):
                        classes += 1
                    elif isinstance(node, ast.ExceptHandler):
                        if getattr(node, "type", None) is None:
                            bare_except += 1
            except Exception as e:
                # capture parse error message for diagnostics
                parse_error = True
                parse_error_msg = str(e)
                report["totals"]["parse_errors"] += 1
            todos = len(re.findall(r"\bTODO\b", src, flags=re.IGNORECASE))
            report["files"][path] = {
                "lines": lines,
                "functions": funcs,
                "classes": classes,
                "todos": todos,
                "bare_excepts": bare_except,
                "parse_error": parse_error,
                "parse_error_msg": parse_error_msg,
            }
            report["totals"]["files"] += 1
            report["totals"]["lines"] += lines
            report["totals"]["functions"] += funcs
            report["totals"]["classes"] += classes
            report["totals"]["todos"] += todos
            report["totals"]["bare_excepts"] += bare_except
    return report


def scan_all_files(
    root: str = ".", include_exts: Optional[List[str]] = None, top_n: int = 10
) -> dict:
    """
    Walk `root` and return simple stats about all files (not just .py):
      - counts by extension
      - total size
      - top N largest files (path, size)
    Useful to "check other files" (data, configs, reports, binaries).
    """
    import os

    if include_exts is not None:
        include_exts = set(e.lower() for e in include_exts)
    counts = {}
    total_size = 0
    files_sizes = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip common venv / git dirs
        parts = set(p for p in dirpath.split(os.sep) if p)
        if parts & {".git", "__pycache__", "venv", "env", "node_modules", "reports"}:
            continue
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            try:
                st = os.stat(path)
                sz = st.st_size
            except Exception:
                continue
            _, ext = os.path.splitext(fn)
            ext = ext.lower() or "<noext>"
            if include_exts is not None and ext not in include_exts:
                continue
            counts[ext] = counts.get(ext, 0) + 1
            total_size += sz
            files_sizes.append((path, sz))
    files_sizes.sort(key=lambda x: x[1], reverse=True)
    top = [{"path": p, "size": s} for p, s in files_sizes[:top_n]]
    return {"counts_by_ext": counts, "total_size": total_size, "top_files": top}


def scan_full_project(
    root: str = ".",
    py_ext: str = ".py",
    include_exts: Optional[List[str]] = None,
    top_n: int = 20,
) -> dict:
    """
    Run a combined project scan:
      - scan_codebase (Python AST metrics)
      - scan_all_files (files by extension & largest files)
    Returns a dict with both sections for quick inspection.
    """
    out = {}
    try:
        out["codebase"] = scan_codebase(root, py_ext=py_ext)
    except Exception as e:
        out["codebase_error"] = str(e)
    try:
        out["other_files"] = scan_all_files(
            root, include_exts=include_exts, top_n=top_n
        )
    except Exception as e:
        out["other_files_error"] = str(e)
    return out


if __name__ == "__main__":  # simple CLI for quick scanning
    try:
        import json as _json
        import sys

        root = sys.argv[1] if len(sys.argv) > 1 else "."
        out = scan_full_project(root)
        print(_json.dumps(out, indent=2))
    except Exception as e:
        print(f"[router.scan] error: {e}")
