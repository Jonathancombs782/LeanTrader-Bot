from __future__ import annotations

import os  # noqa: F401  # intentionally kept
import time

import pandas as pd  # noqa: F401  # intentionally kept
from dotenv import load_dotenv

from traders_core.connectors.crypto_ccxt import market_buy, market_info, market_sell, ohlcv_df, ticker_price
from traders_core.features.pipeline import make_features
from traders_core.observability.metrics import METRICS
try:
    from observability.metrics import record_slippage, record_order_sent, record_order_reject
except Exception:
    def record_slippage(_: float):
        return None

    def record_order_sent(n: int = 1):
        return None

    def record_order_reject(n: int = 1):
        return None
from traders_core.research.regime import tag_regimes
from traders_core.storage.registry import load_latest, load_latest_tagged
from traders_core.utils.ta import atr
try:
    from risk.guards import GuardState, RiskLimits, should_halt_trading, HaltTrading  # type: ignore
    from config import (
        RISK_MAX_LOSS_PER_SYMBOL,
        RISK_MAX_DAILY_LOSS,
        RISK_MAX_ACCOUNT_DD,
        RISK_LIMITS_PCT,
    )
    _GUARD_STATE = GuardState()
except Exception:
    GuardState = None  # type: ignore
    RiskLimits = None  # type: ignore
    should_halt_trading = None  # type: ignore
    HaltTrading = Exception  # type: ignore
    _GUARD_STATE = None

load_dotenv()
TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()
CRYPTO_TESTNET = os.getenv("CRYPTO_TESTNET", "true").lower() == "true"


def _round_amount(amount: float, prec: int) -> float:
    q = 10**prec
    return int(amount * q) / q


def _emulate_oco(symbol_key: str, get_price, sl: float, tp: float, poll: int):
    """Client-side OCO: close paper position when SL or TP hit; for live, send market close."""
    from traders_core.sim.paper_broker import PaperBroker  # noqa: E402

    brk = PaperBroker()
    while True:
        px = float(get_price())
        # mark-to-market will close on exact SL/TP in paper mode
        brk.mark_to_market(symbol_key, px)
        # If no position left, break
        if not brk.positions(symbol_key):
            break
        time.sleep(max(1, poll))


def decide_and_execute_crypto(
    exchange: str,
    symbol: str,
    timeframe: str,
    cfg: dict,
    models_dir: str,
    lookback_days: int = 120,
):
    sym_key = symbol.replace("/", "_")
    model, meta = load_latest(sym_key, timeframe, models_dir)
    if model is None:
        return {"status": "no_model"}

    df = ohlcv_df(exchange, symbol, timeframe, lookback_days, CRYPTO_TESTNET)
    feats = make_features(df, rsi_window=cfg["risk"]["atr_window"], atr_window=cfg["risk"]["atr_window"])
    X_live = feats[meta["features"]].iloc[[-1]]
    prob = float(getattr(model, "predict_proba")(X_live)[0, 1])

    # Regime tag (calm/storm) and probability gate
    reg = tag_regimes(df["close"], cfg["regimes"]["vol_window"], cfg["regimes"]["calm_quantile"])
    regime_now = reg.iloc[-1]
    gate = 0.55 if regime_now == "storm" else 0.5
    side = 1 if prob > gate else 0

    sym_key = symbol.replace("/", "_")
    tag = "storm" if regime_now == "storm" else "calm"
    model, meta = load_latest_tagged(sym_key, timeframe, tag, models_dir)
    if model is None:
        model, meta = load_latest(sym_key, timeframe, models_dir)  # fallback

    price = float(df["close"].iloc[-1])
    latest_atr = float(atr(df.tail(200), cfg["risk"]["atr_window"]).iloc[-1])
    # Flash-crash detector: monitor mid and depth
    try:
        if _FLASH_GUARD is not None:
            from execution.liquidity_guard import _fetch_orderbook

            ob = _fetch_orderbook(exchange, symbol)
            mid = (float(ob.get("bid", 0.0)) + float(ob.get("ask", 0.0))) / 2.0 if ob else float(df["close"].iloc[-1])
            depth = float(ob.get("bid_size", 0.0) + ob.get("ask_size", 0.0))
            if _FLASH_GUARD.update(mid, depth):
                # Estimate exposure as small notional and hedge
                notional = float(df["close"].iloc[-1]) * 0.01
                res = emergency_hedge(notional, exchange)
                if FLASH_HEDGE_COUNT is not None:
                    FLASH_HEDGE_COUNT.inc()
                slack_warn("Flash-crash hedge", [f"symbol={symbol}", f"venue={exchange}", f"ok={res.get('ok')}" ])
                return {"status": "flash_hedge", "hedge": res}
    except Exception:
        pass
    if side == 0:
        METRICS.last_signal.labels(venue="crypto", symbol=symbol).set(0)
        METRICS.latest_prob.labels(venue="crypto", symbol=symbol).set(prob)
        return {"status": "flat", "prob": prob, "regime": regime_now}

    mkt = market_info(exchange, symbol, CRYPTO_TESTNET)
    equity = float(cfg["risk"].get("equity_usd", 50.0))
    # ---- Risk guard check before routing ----
    try:
        if _GUARD_STATE is not None and RiskLimits is not None and should_halt_trading is not None:
            _GUARD_STATE.update_equity(equity)
            limits = RiskLimits(
                max_loss_per_symbol=float(RISK_MAX_LOSS_PER_SYMBOL),
                max_daily_loss=float(RISK_MAX_DAILY_LOSS),
                max_account_drawdown=float(RISK_MAX_ACCOUNT_DD),
                pct=bool(RISK_LIMITS_PCT),
            )
            halt, reasons = should_halt_trading(_GUARD_STATE, limits)
            if halt:
                raise HaltTrading(f"risk guards tripped: {', '.join(reasons)}")
    except HaltTrading:
        raise
    except Exception:
        pass
    risk_money = equity * cfg["risk"]["per_trade_risk_pct"]
    raw_amount = risk_money / max(latest_atr, 1e-9)
    min_amount_cost = mkt["min_cost"] / price
    amount = max(raw_amount, min_amount_cost, mkt["min_qty"])
    amount = _round_amount(amount, mkt["amount_prec"])
    # Liquidity guard: reduce amount if estimated price impact too high
    try:
        import os
        from execution.liquidity_guard import guard_order
        from observability.metrics import LIQUIDITY_BLOCKS

        bps_cap = float(os.getenv("LIQUIDITY_BPS_CAP", "30"))
        amt_safe = guard_order(symbol, exchange, amount, bps_cap=bps_cap)
        # If reduced below threshold (e.g., below min notional cost), skip trade
        min_frac = float(os.getenv("MIN_LIQ_BLOCK_FRAC", "0.25"))
        if amt_safe < max(min_amount_cost, amount * min_frac):
            if LIQUIDITY_BLOCKS is not None:
                LIQUIDITY_BLOCKS.inc()
            return {"status": "liquidity_blocked", "amount": float(amount), "safe": float(amt_safe)}
        amount = amt_safe
    except Exception:
        pass

    sl = price - cfg["risk"]["atr_stop_mult"] * latest_atr
    tp = price + cfg["risk"]["atr_tp_mult"] * latest_atr

    METRICS.latest_prob.labels(venue="crypto", symbol=symbol).set(prob)
    METRICS.last_signal.labels(venue="crypto", symbol=symbol).set(1)

    if TRADING_MODE == "paper":
        from traders_core.sim.paper_broker import PaperBroker  # noqa: E402

        brk = PaperBroker()
        record_order_sent(1)
        fill = brk.market_buy(
            symbol=f"CRYPTO:{symbol}",
            price=price,
            qty=amount,
            fee_rate=mkt["taker"],
            sl=sl,
            tp=tp,
        )
        METRICS.orders_total.labels(venue="crypto", symbol=symbol, status="paper").inc()
        try:
            fp = float((fill or {}).get("price") or price)
            bps = abs(fp - float(price)) / max(1e-9, float(price)) * 1e4
            record_slippage(bps)
        except Exception:
            pass

        if cfg.get("oco", {}).get("enabled", True):
            # spawn a lightweight OCO emulator loop (blocking in our simple loop; okay since we poll every tick)
            _emulate_oco(
                f"CRYPTO:{symbol}",
                lambda: ticker_price(exchange, symbol, CRYPTO_TESTNET),
                sl,
                tp,
                cfg["oco"]["poll_sec"],
            )

        result = {
            "status": "paper_filled",
            "prob": prob,
            "amount": amount,
            "price": price,
            "sl": sl,
            "tp": tp,
            "regime": regime_now,
            "fill": fill,
        }
        # Best-effort: write per-trade explanation
        try:
            from reporting.explain import write_explanation_markdown

            write_explanation_markdown(
                order={
                    "id": (fill or {}).get("id") or f"paper-{symbol}-{int(time.time())}",
                    "symbol": symbol,
                    "side": "buy",
                    "price": float((fill or {}).get("price") or price),
                    "qty": float((fill or {}).get("qty") or amount),
                    "ts": int(time.time()),
                    "route": "spot",
                },
                context={
                    "regime": regime_now,
                    "selector": "crypto_router",
                    "key_signals": [{"name": "model_prob", "score": prob}],
                    "hype_score": None,
                    "risk_caps": None,
                    "expected_slippage_bps": 0.0,
                },
            )
            # Encrypted trade log
            try:
                from security.vault import secure_write  # type: ignore

                trade_log = {
                    "venue": "crypto",
                    "symbol": symbol,
                    "mode": "paper",
                    "qty": float(amount),
                    "price": float((fill or {}).get("price") or price),
                    "ts": int(time.time()),
                }
                secure_write(f"runtime/trade_logs/{symbol.replace('/', '_')}_{int(time.time())}.enc", trade_log)
            except Exception:
                pass
        except Exception:
            pass
        return result

    # LIVE: send market buy; emulate OCO client-side by watching price and sending market sell on trigger.
    try:
        record_order_sent(1)
        res = market_buy(exchange, symbol, amount, CRYPTO_TESTNET)
        METRICS.orders_total.labels(venue="crypto", symbol=symbol, status="live_sent").inc()
        if cfg.get("oco", {}).get("enabled", True):

            def _live_close():
                px = float(ticker_price(exchange, symbol, CRYPTO_TESTNET))
                hit_sl = px <= sl
                hit_tp = px >= tp
                if hit_sl or hit_tp:
                    try:
                        market_sell(exchange, symbol, amount, CRYPTO_TESTNET)
                    except Exception:
                        pass

            # quick loop (non-threaded): check once; orchestration calls this function every signal pass
            _live_close()
        result = {
            "status": "live_sent",
            "id": res.get("id"),
            "amount": amount,
            "prob": prob,
            "price": price,
            "regime": regime_now,
        }
        # Best-effort: write per-trade explanation
        try:
            from reporting.explain import write_explanation_markdown

            write_explanation_markdown(
                order={
                    "id": res.get("id") or f"live-{symbol}-{int(time.time())}",
                    "symbol": symbol,
                    "side": "buy",
                    "price": float(price),
                    "qty": float(amount),
                    "ts": int(time.time()),
                    "route": "spot",
                },
                context={
                    "regime": regime_now,
                    "selector": "crypto_router",
                    "key_signals": [{"name": "model_prob", "score": prob}],
                },
            )
            # Encrypted trade log
            try:
                from security.vault import secure_write  # type: ignore

                trade_log = {
                    "venue": "crypto",
                    "symbol": symbol,
                    "mode": "live",
                    "qty": float(amount),
                    "price": float(price),
                    "ts": int(time.time()),
                    "order_id": res.get("id"),
                }
                secure_write(f"runtime/trade_logs/{symbol.replace('/', '_')}_{int(time.time())}.enc", trade_log)
            except Exception:
                pass
        except Exception:
            pass
        return result
    except Exception as e:
        METRICS.orders_total.labels(venue="crypto", symbol=symbol, status="live_error").inc()
        record_order_reject(1)
        return {"status": "live_error", "error": str(e), "regime": regime_now}

try:
    from risk.flash_crash import FlashCrashGuard, FlashCrashParams, emergency_hedge
    from observability.metrics import FLASH_HEDGE_COUNT
    from ops.slack_notify import warn as slack_warn
    _FLASH_GUARD = FlashCrashGuard(FlashCrashParams())
except Exception:
    _FLASH_GUARD = None
    FLASH_HEDGE_COUNT = None
    def slack_warn(title: str, reasons=None):
        return False
