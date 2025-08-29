# trader_core.py
from __future__ import annotations

import os, time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import pandas as pd

from session_clock import fx_session_active, minutes_to_next_open
from volatility import vol_hot
from mt5_adapter import mt5_init
from mt5_signals import fetch_bars_safe, gen_signal, place_mt5_signal
from router import ExchangeRouter
from risk_guard import RiskManager, RiskConfig
from futures_signals import fut_side_from_ema, calc_contract_qty_usdt
from skillbook import update_vol_stats, personalized_thresholds

load_dotenv()

ENABLE_LIVE = (os.getenv("ENABLE_LIVE") or "false").strip().lower() in ("1","true","yes","on")

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
    env_key = f"{'FUT' if kind=='FUT' else 'STAKE'}_{tf.upper()}"
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

        self.mt5 = mt5_init()
        self.router = ExchangeRouter()
        self.risk = RiskManager(self.router, RiskConfig())

    # ---------- FX ----------
    def _poll_fx(self) -> None:
        for sym in self.fx_symbols:
            if not fx_session_active(sym):
                mins = minutes_to_next_open(sym)
                print(f"[FX] {sym} session closed. next ~{mins}m")
                continue

            for tf in self.fx_tfs:
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

                sig = gen_signal(df)
                if not sig:
                    print(f"[FX] {sym} {tf}: no signal")
                    continue

                lots = _lots_for(sym, tf)
                print(f"[FX] {sym} {tf}: {sig['side'].upper()} lots={lots:.2f} SL={sig['sl']:.5f} TP={sig['tp']:.5f} live={ENABLE_LIVE}")
                if ENABLE_LIVE:
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
                        df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
                        df["time"] = pd.to_datetime(df["time"], unit="ms")
                except Exception as e:
                    print(f"[trader_core] safe_fetch_ohlcv failed for {sym} {tf}: {e}")
                    df = pd.DataFrame()

                atr_th, bbw_th = personalized_thresholds(sym, self.base_atr_th, self.base_bbw_th)
                v = vol_hot(df, atr_th=atr_th, bbw_th=bbw_th) if not df.empty else {"hot": 1.0, "atr_pct":0.0, "bbw":0.0}
                update_vol_stats("SPOT", sym, tf, v.get("atr_pct",0.0), v.get("bbw",0.0))
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
                        df = pd.DataFrame(rows, columns=["time","open","high","low","close","volume"])
                        df["time"] = pd.to_datetime(df["time"], unit="ms")
                        px = float(df["close"].iloc[-1])
                except Exception as e:
                    print(f"[trader_core] safe_fetch_ohlcv failed for {sym} {tf}: {e}")
                    df, px = pd.DataFrame(), 0.0

                atr_th, bbw_th = personalized_thresholds(sym, self.base_atr_th, self.base_bbw_th)
                v = vol_hot(df, atr_th=atr_th, bbw_th=bbw_th) if not df.empty else {"hot": 1.0, "atr_pct":0.0, "bbw":0.0}
                update_vol_stats("FUT", sym, tf, v.get("atr_pct",0.0), v.get("bbw",0.0))
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
            except Exception as e:
                print("Loop error:", e)
            time.sleep(self.loop_sec)
