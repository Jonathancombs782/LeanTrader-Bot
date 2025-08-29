from __future__ import annotations
import os, yaml, time
from pathlib import Path
from dotenv import load_dotenv
from traders_core.mt5_adapter import init as mt5_init, shutdown as mt5_shutdown
from traders_core.research.walk_forward import train_evaluate, online_partial_fit
from traders_core.knowledge.note import write_digest
from traders_core.execution.router import decide_and_execute_mt5
from traders_core.execution.crypto_router import decide_and_execute_crypto
from traders_core.observability.metrics import METRICS
from traders_core.connectors.crypto_ccxt import ticker_price, ohlcv_df
from traders_core.research.regime import tag_regimes
from traders_core.features.pipeline import rates_to_df, make_features, build_xy
from traders_core.mt5_adapter import copy_rates_days
from traders_core.portfolio.wallets import crypto_wallet_usd, mt5_equity_usd
from traders_core.portfolio.market_selector import compute_selection
from traders_core.storage.registry import load_latest_tagged

load_dotenv()
MODELS_DIR = os.getenv("MODELS_DIR", "./runtime_models")
NOTES_DIR  = os.getenv("NOTES_DIR", "./runtime_notes")
CRYPTO_TESTNET = (os.getenv("CRYPTO_TESTNET","true").lower() == "true")

def load_cfg(path="traders_core/configs/default.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())

def _relabel_symbol_for_models(symbol: str, venue: str) -> str:
    # Save/load models under symbol-timeframe directories; for crypto, replace '/'
    return symbol.replace("/","_") if venue=="crypto" else symbol

def research_once(cfg: dict):
    results = {}
    for a in cfg["assets"]:
        sym = a["symbol"]; venue = a["venue"]; tf = a["timeframe"]
        sym_for_model = sym.replace("/","_") if venue=="crypto" else sym

        # choose cost stress per venue
        bps = cfg["tcost"]["crypto_bps"] if venue=="crypto" else cfg["tcost"]["fx_bps"]
        out = train_evaluate(
            symbol=sym_for_model,
            timeframe=tf,
            lookback_days=cfg["lookback_days"],
            horizon_bars=cfg["horizon_bars"],
            models_dir=MODELS_DIR,
            promotion_cfg=cfg["promotion"],
            tcost_bps=bps
        )
        # optional: online learning on the latest window
        if cfg.get("online_learning",{}).get("enabled", False):
            rates = copy_rates_days(sym_for_model, tf, max(5, cfg["online_learning"]["window_bars"]//288 + 2))
            df = rates_to_df(rates)
            feats = make_features(df)
            X, y = build_xy(feats, horizon=cfg["horizon_bars"])
            Xw, yw = X.tail(cfg["online_learning"]["window_bars"]), y.tail(cfg["online_learning"]["window_bars"])
            if len(Xw) >= cfg["online_learning"]["min_samples"]:
                from traders_core.storage.registry import load_latest, save_model
                model, meta = load_latest(sym_for_model, tf, MODELS_DIR)
                if model is not None:
                    try:
                        new = online_partial_fit(Xw, yw, None)  # separate online model variant
                        meta["online_adapter"] = True
                        save_model(sym_for_model, tf, new, meta, MODELS_DIR)
                    except Exception:
                        pass

        results[sym] = out
        # ... write digest, metrics unchanged ...
    return results

def signals_once(cfg: dict):
    out = {}
    # Pull quick wallets
    exchange = os.getenv("CRYPTO_EXCHANGE","binance")
    crypto_eq = crypto_wallet_usd(exchange, os.getenv("CRYPTO_TESTNET","true").lower()=="true")
    fx_eq     = mt5_equity_usd()

    # Preload small windows for scoring
    crypto_dfs, fx_dfs = {}, {}
    for a in cfg["assets"]:
        if a["venue"] == "crypto":
            crypto_dfs[a["symbol"]] = ohlcv_df(a.get("exchange","binance"), a["symbol"], a["timeframe"], 5, os.getenv("CRYPTO_TESTNET","true").lower()=="true")
        else:
            # 5-day window from MT5
            import pandas as pd
            rates = copy_rates_days(a["symbol"], a["timeframe"], 5)
            fx_dfs[a["symbol"]] = rates_to_df(rates)

    sel = compute_selection(cfg, crypto_eq, fx_eq, crypto_dfs, fx_dfs, exchange)
    allowed = {(sym, venue) for (sym, _score, venue) in sel["selected"]}

    for a in cfg["assets"]:
        sym, venue, tf = a["symbol"], a["venue"], a["timeframe"]
        if (sym, venue) not in allowed:
            out[sym] = {"status": "skipped_by_selector"}
            continue

        # Regime-tagged model loading (prefer tagged model)
        if cfg.get("regime_models",{}).get("enabled", False):
            df = crypto_dfs.get(sym) if venue=="crypto" else fx_dfs.get(sym)
            reg = tag_regimes(df["close"], cfg["regimes"]["vol_window"], cfg["regimes"]["calm_quantile"]).iloc[-1]
            tag = "storm" if reg == "storm" else "calm"
            model, meta = load_latest_tagged(sym.replace("/","_") if venue=="crypto" else sym, tf, tag, MODELS_DIR)
            # if tagged missing, the routers will still fallback to global model internally

        # Route
        if venue == "mt5":
            out[sym] = decide_and_execute_mt5(sym, tf, cfg, MODELS_DIR)
        else:
            ex = a.get("exchange","binance")
            out[sym] = decide_and_execute_crypto(ex, sym, tf, cfg, MODELS_DIR, cfg["lookback_days"])
    return out

def run_forever(cfg_path="traders_core/configs/default.yaml"):
    cfg = load_cfg(cfg_path)
    # MT5 init only if we actually have mt5 assets
    needs_mt5 = any(a["venue"]=="mt5" for a in cfg["assets"])
    if needs_mt5:
        mt5_init()
    try:
        t0 = 0.0
        while True:
            now = time.time()
            if now - t0 > cfg["scheduler"]["research_cadence_sec"]:
                research_once(cfg); t0 = now
            sig = signals_once(cfg)
            print("signals:", sig, flush=True)
            time.sleep(cfg["scheduler"]["signal_cadence_sec"])
    finally:
        if needs_mt5:
            mt5_shutdown()
