# trader_core.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional  # noqa: F401  # intentionally kept

import pandas as pd
from dotenv import load_dotenv

from futures_signals import calc_contract_qty_usdt, fut_side_from_ema


def _import_mt5_init():
    """Return a callable mt5_init() that initializes MT5 or a noop when not available."""
    try:
        import importlib

        mod = importlib.import_module("mt5_adapter")
        return getattr(mod, "mt5_init")
    except Exception:
        try:
            import importlib.util
            import sys
            from pathlib import Path

            repo_root = Path(__file__).resolve().parent
            candidate = repo_root / "mt5_adapter.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("mt5_adapter", str(candidate))
                mod = importlib.util.module_from_spec(spec)
                sys.modules["mt5_adapter"] = mod
                spec.loader.exec_module(mod)  # type: ignore
                return getattr(mod, "mt5_init", lambda: None)
        except Exception:
            pass

    def _noop_mt5_init():
        return None

    return _noop_mt5_init


def _import_risk_components():
    """Return (RiskConfig, RiskManager) from `risk_guard` if available.

    This helper tries a normal import first, then a file-based import from
    the repository root. If both fail, it returns lightweight compatibility
    shims so the rest of the system can run in demo/test environments.
    """
    try:
        from risk_guard import RiskConfig, RiskManager  # type: ignore

        try:
            print(
                f"[trader_core] loaded risk_guard from normal import; RiskConfig={hasattr(__import__('risk_guard'), 'RiskConfig')}"
            )
        except Exception:
            pass
        return RiskConfig, RiskManager
    except Exception:
        # continue to file-based import
        pass

    try:
        import importlib.util
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent
        candidate = repo_root / "risk_guard.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location("risk_guard", str(candidate))
            mod = importlib.util.module_from_spec(spec)
            sys.modules["risk_guard"] = mod
            spec.loader.exec_module(mod)  # type: ignore
            try:
                print(f"[trader_core] loaded risk_guard from file {candidate}")
            except Exception:
                pass
            return getattr(mod, "RiskConfig"), getattr(mod, "RiskManager")
    except Exception:
        pass

    # Fallback shims
    class RiskConfig:  # type: ignore
        def __init__(self, *args, **kwargs):
            self.max_order_usd = 5.0
            self.max_positions = 6
            self.max_per_symbol = 1
            self.max_exposure_frac = 0.35
            self.dd_limit_pct = 0.06
            self.dd_pause_min = 60

    class RiskManager:  # type: ignore
        def __init__(self, router, config=None):
            self.router = router
            self.cfg = config or RiskConfig()

        def allow_trade(self, *args, **kwargs):
            return {"ok": True, "reason": "shim"}

        def size_spot(self, *args, **kwargs):
            return 0.0

    return RiskConfig, RiskManager


# Resolve risk components once using the robust loader to avoid multiple
# import sites and reduce circular-import windows in supervised children.
try:
    RiskConfig, RiskManager = _import_risk_components()
except Exception:
    # last-resort fallback if loader itself fails
    class RiskConfig:  # type: ignore
        def __init__(self, *a, **k):
            self.max_order_usd = 5.0
            self.max_positions = 6
            self.max_per_symbol = 1
            self.max_exposure_frac = 0.35
            self.dd_limit_pct = 0.06
            self.dd_pause_min = 60

    class RiskManager:  # type: ignore
        def __init__(self, router, config=None):
            self.router = router
            self.cfg = config or RiskConfig()

        def allow_trade(self, *a, **k):
            return {"ok": True, "reason": "shim"}

        def size_spot(self, *a, **k):
            return 0.0


from router import ExchangeRouter  # noqa: E402


def _lazy_mt5_signals():
    """Return a tuple (fetch_bars_safe, gen_signal, place_mt5_signal).

    This tries a normal import first then falls back to loading the
    local mt5_signals module by file if needed. If both fail, return
    lightweight fallbacks so importing this module won't raise.
    """
    try:
        import importlib

        mod = importlib.import_module("mt5_signals")
        return (
            getattr(mod, "fetch_bars_safe", lambda *a, **k: __import__("pandas").DataFrame()),
            getattr(mod, "gen_signal", lambda *a, **k: {}),
            getattr(mod, "place_mt5_signal", lambda *a, **k: {"ok": False, "comment": "mt5 unavailable"}),
        )
    except Exception:
        try:
            import importlib.util
            import sys
            from pathlib import Path

            repo_root = Path(__file__).resolve().parent
            candidate = repo_root / "mt5_signals.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("mt5_signals", str(candidate))
                mod = importlib.util.module_from_spec(spec)
                sys.modules["mt5_signals"] = mod
                spec.loader.exec_module(mod)  # type: ignore
                return (
                    getattr(mod, "fetch_bars_safe", lambda *a, **k: __import__("pandas").DataFrame()),
                    getattr(mod, "gen_signal", lambda *a, **k: {}),
                    getattr(mod, "place_mt5_signal", lambda *a, **k: {"ok": False, "comment": "mt5 unavailable"}),
                )
        except Exception:
            pass

    # fallbacks
    def _fb(*a, **k):
        return __import__("pandas").DataFrame()

    def _fg(*a, **k):
        return {}

    def _fp(*a, **k):
        return {"ok": False, "comment": "mt5 unavailable"}

    return _fb, _fg, _fp


from session_clock import fx_session_active, minutes_to_next_open  # noqa: E402
from skillbook import personalized_thresholds, update_vol_stats  # noqa: E402
from volatility import vol_hot  # noqa: E402

load_dotenv()

# Early import-time diagnostics for supervisor children. Keep minimal and safe.
try:
    import sys

    print(f"[diag trader_core] exe={getattr(sys, 'executable', None)} cwd={os.getcwd()} sys.path0={sys.path[0]}")
    try:
        # list a few repo files to validate working directory
        root = os.path.dirname(__file__)
        files = sorted([f for f in os.listdir(root) if f.endswith(".py")])[:10]
        print(f"[diag trader_core] repo_py_files={files}")
    except Exception:
        pass
except Exception:
    pass

ENABLE_LIVE = (os.getenv("ENABLE_LIVE") or "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _csv(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _lots_for(symbol: str, tf: str) -> float:
    env_key = f"LOTS_{tf.upper()}"
    base = float(os.getenv(env_key, "0.01") or "0.01")
    # Be more conservative on XAU by default
    if "XAU" in symbol.upper():
        base *= float(os.getenv("XAU_LOT_MULT", "0.6") or "0.6")
    return base


def _stake_for_tf(tf: str, kind: str = "SPOT") -> float:
    # SPOT stake per TF or FUT stake per TF
    env_key = f"{'FUT' if kind == 'FUT' else 'STAKE'}_{tf.upper()}"
    default = 5.0 if kind == "SPOT" else 10.0
    try:
        return float(os.getenv(env_key, str(default)) or str(default))
    except Exception:
        return default


def _fut_leverage(symbol: str) -> float:
    # Per-symbol leverage (env) with fallback
    s = symbol.upper().replace("/", "_")
    v = os.getenv(f"LEV_{s}") or os.getenv("FUT_LEVERAGE") or "5"
    try:
        return float(v)
    except Exception:
        return 5.0


class TraderCore:
    def __init__(
        self,
        fx_symbols: List[str],
        fx_tfs: List[str],
        crypto_spot: List[str],
        crypto_spot_tfs: List[str],
        crypto_fut: List[str],
        crypto_fut_tfs: List[str],
        loop_sec: int = 20,
        atr_th: float = 0.003,
        bbw_th: float = 0.02,
    ) -> None:
        self.fx_symbols = fx_symbols
        self.fx_tfs = fx_tfs
        self.crypto_spot = crypto_spot
        self.crypto_spot_tfs = crypto_spot_tfs
        self.crypto_fut = crypto_fut
        self.crypto_fut_tfs = crypto_fut_tfs
        self.loop_sec = max(5, loop_sec)
        self.base_atr_th = atr_th
        self.base_bbw_th = bbw_th

        try:
            mt5_init = _import_mt5_init()
            self.mt5 = mt5_init()
        except Exception:
            # allow running in environments without MetaTrader5; fall back to None
            self.mt5 = None
        self.router = ExchangeRouter()
        # Use module-level RiskConfig/RiskManager resolved at import time above.
        try:
            self.risk = RiskManager(self.router, RiskConfig())
        except Exception:
            # last-resort shim
            class _Shim:
                def __init__(self, r):
                    self.cfg = type("C", (), {"max_order_usd": 5.0})()

                def allow_trade(self, *a, **k):
                    return {"ok": True, "reason": "shim"}

                def size_spot(self, *a, **k):
                    return 0.0

            self.risk = _Shim(self.router)

    # ---------- FX ----------
    def _poll_fx(self) -> None:
        for sym in self.fx_symbols:
            if not fx_session_active(sym):
                mins = minutes_to_next_open(sym)
                print(f"[FX] {sym} session closed. next ~{mins}m")
                continue

            for tf in self.fx_tfs:
                # lazy import to avoid top-level import-time failures in
                # environments missing MT5 or when mt5_adapter raises.
                try:
                    ms = __import__("mt5_signals")
                    fetch_bars_safe = getattr(ms, "fetch_bars_safe")
                except Exception:

                    def fetch_bars_safe(s, t, limit=250):
                        return __import__("pandas").DataFrame()

                df = fetch_bars_safe(sym, tf, limit=250)
                if df.empty:
                    print(f"[FX] {sym} {tf}: no bars")
                    continue

                # symbol-aware thresholds (XAU stricter)
                atr_th, bbw_th = personalized_thresholds(sym, self.base_atr_th, self.base_bbw_th)
                v = vol_hot(df, atr_th=atr_th, bbw_th=bbw_th)
                update_vol_stats("FX", sym, tf, v.get("atr_pct", 0.0), v.get("bbw", 0.0))
                if not v["hot"]:
                    print(f"[FX] {sym} {tf}: cool (ATR%={v['atr_pct']:.4f}, BBW={v['bbw']:.4f})")
                    continue

                try:
                    gen_signal = getattr(__import__("mt5_signals"), "gen_signal")
                except Exception:

                    def gen_signal(d):
                        return {}

                sig = gen_signal(df)
                if not sig:
                    print(f"[FX] {sym} {tf}: no signal")
                    continue

                lots = _lots_for(sym, tf)
                print(
                    f"[FX] {sym} {tf}: {sig['side'].upper()} lots={lots:.2f} SL={sig['sl']:.5f} TP={sig['tp']:.5f} live={ENABLE_LIVE}"
                )
                if ENABLE_LIVE:
                    try:
                        place_mt5_signal = getattr(__import__("mt5_signals"), "place_mt5_signal")
                    except Exception:

                        def place_mt5_signal(mt5mod, symbol, side, lots, sl, tp):
                            return {
                                "ok": False,
                                "comment": "mt5 not available",
                            }

                    res = place_mt5_signal(self.mt5, sym, sig["side"], lots, sig["sl"], sig["tp"])
                    print(" -> order:", res)

    # ---------- Crypto Spot ----------
    def _poll_crypto_spot(self) -> None:
        for sym in self.crypto_spot:
            for tf in self.crypto_spot_tfs:
                try:
                    m = self.router._resolve_symbol(sym, futures=False)
                    rows = self.router.safe_fetch_ohlcv(m, timeframe=tf, limit=150)
                    if not rows:
                        df = pd.DataFrame()
                    else:
                        df = pd.DataFrame(
                            rows,
                            columns=["time", "open", "high", "low", "close", "volume"],
                        )
                        df["time"] = pd.to_datetime(df["time"], unit="ms")
                except Exception as _e:
                    print(f"[trader_core] safe_fetch_ohlcv failed for {sym} {tf}: {_e}")
                    df = pd.DataFrame()

                atr_th, bbw_th = personalized_thresholds(sym, self.base_atr_th, self.base_bbw_th)
                v = (
                    vol_hot(df, atr_th=atr_th, bbw_th=bbw_th)
                    if not df.empty
                    else {"hot": 1.0, "atr_pct": 0.0, "bbw": 0.0}
                )
                update_vol_stats("SPOT", sym, tf, v.get("atr_pct", 0.0), v.get("bbw", 0.0))
                if not v["hot"]:
                    print(f"[SPOT] {sym} {tf}: cool (ATR%={v['atr_pct']:.4f}, BBW={v['bbw']:.4f})")
                    continue

                if df.empty:
                    print(f"[SPOT] {sym} {tf}: no bars; skip")
                    continue

                # reuse futures EMA logic for direction
                side = fut_side_from_ema(df)
                if not side:
                    print(f"[SPOT] {sym} {tf}: no signal")
                    continue

                stake = _stake_for_tf(tf, "SPOT")
                self.risk.cfg.max_order_usd = stake
                pre = self.risk.allow_trade(sym, side)
                if not pre["ok"]:
                    print(f"[SPOT] {sym}: blocked by risk: {pre['reason']}")
                    continue
                qty = self.risk.size_spot(sym) or 0.0
                print(f"[SPOT] {sym} {tf}: {side.upper()} qty≈{qty:.6f} live={ENABLE_LIVE}")
                if ENABLE_LIVE:
                    res = self.router.place_spot_market(sym, side, qty)
                    print(" -> order:", res)

    # ---------- Crypto Futures (linear USDT perps) ----------
    def _poll_crypto_futures(self) -> None:
        for sym in self.crypto_fut:
            for tf in self.crypto_fut_tfs:
                try:
                    m = self.router._resolve_symbol(sym, futures=True)
                    rows = self.router.safe_fetch_ohlcv(m, timeframe=tf, limit=150)
                    if not rows:
                        df, px = pd.DataFrame(), 0.0
                    else:
                        df = pd.DataFrame(
                            rows,
                            columns=["time", "open", "high", "low", "close", "volume"],
                        )
                        df["time"] = pd.to_datetime(df["time"], unit="ms")
                        px = float(df["close"].iloc[-1])
                except Exception as _e:
                    print(f"[trader_core] safe_fetch_ohlcv failed for {sym} {tf}: {_e}")
                    df, px = pd.DataFrame(), 0.0

                atr_th, bbw_th = personalized_thresholds(sym, self.base_atr_th, self.base_bbw_th)
                v = (
                    vol_hot(df, atr_th=atr_th, bbw_th=bbw_th)
                    if not df.empty
                    else {"hot": 1.0, "atr_pct": 0.0, "bbw": 0.0}
                )
                update_vol_stats("FUT", sym, tf, v.get("atr_pct", 0.0), v.get("bbw", 0.0))
                if not v["hot"]:
                    print(f"[FUT] {sym} {tf}: cool (ATR%={v['atr_pct']:.4f}, BBW={v['bbw']:.4f})")
                    continue

                side = fut_side_from_ema(df) if not df.empty else None
                if not side:
                    print(f"[FUT] {sym} {tf}: no signal")
                    continue

                stake = _stake_for_tf(tf, "FUT")
                lev = _fut_leverage(sym)
                qty = calc_contract_qty_usdt(px, stake, lev, min_qty=0.001, step=0.001)
                print(f"[FUT] {sym} {tf}: {side.upper()} qty≈{qty:.4f} lev={lev} live={ENABLE_LIVE}")
                if ENABLE_LIVE and qty > 0:
                    # Place market order; your router handles margin mode/hedge/reduce-only defaults
                    res = self.router.place_futures_market(sym, side, qty, leverage=lev)
                    print(" -> order:", res)

    # ---------- Main loop ----------
    def run_forever(self) -> None:
        print(f"TraderCore live={ENABLE_LIVE} | FX={self.fx_symbols} | SPOT={self.crypto_spot} | FUT={self.crypto_fut}")
        while True:
            try:
                if self.fx_symbols:
                    self._poll_fx()
                if self.crypto_spot:
                    self._poll_crypto_spot()
                if self.crypto_fut:
                    self._poll_crypto_futures()
            except KeyboardInterrupt:
                print("Stopping...")
                break
            except Exception as _e:
                print("Loop error:", _e)
            time.sleep(self.loop_sec)
