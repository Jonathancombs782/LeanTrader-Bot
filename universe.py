# universe.py  (experience-weighted edition)
from __future__ import annotations
import os, re, json, time, math, argparse, datetime as dt
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd

REGION_PREFS = {
    "US": ["kraken", "coinbase"],    # safer in US; add more if you use them
    "EU": ["bybit", "binance"],
    "GB": ["bybit", "binance"],
    "DEFAULT": ["bybit", "binanceus", "kraken"],
}

def pick_exchanges() -> List[str]:
    reg = (os.getenv("REGION") or "").upper()
    prefs = REGION_PREFS.get(reg) or REGION_PREFS["DEFAULT"]
    # allow explicit EXCHANGE_ID to be tried first
    ex0 = os.getenv("EXCHANGE_ID")
    if ex0 and ex0 not in prefs:
        return [ex0] + prefs
    return prefs

def discover_symbols(ex, quote="USDT", top_n=8, min_notional=10.0) -> List[str]:
    """
    Load markets and select active spot symbols quoted in `quote`, sorted by volume.
    """
    from router import ExchangeRouter
    router = ExchangeRouter()
    try:
        markets = router._load_markets_safe() or router.markets
    except Exception:
        return []
    rows: List[Tuple[float,str]] = []
    for m in markets.values():
        if m.get("spot") and m.get("quote") == quote and m.get("active", True):
            s = m.get("symbol")
            v = float(m.get("info", {}).get("quoteVolume", 0) or m.get("baseVolume") or 0)
            rows.append((v, s))
    rows.sort(reverse=True)
    out = [s for _, s in rows[:top_n]]
    return out or [f"BTC/{quote}", f"ETH/{quote}"]

DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)

STABLE_QUOTES = {"USDT","USD","USDC","BUSD","FDUSD","TUSD"}

EXCLUDE_PATTERNS = [
    r"(^|[-_/])(UP|DOWN|BULL|BEAR)(\d+X)?($|[-_/])",
    r"(^|[-_/])(\d+[LS]|[23]L|[23]S|5L|5S)($|[-_/])",
    r"(^|[-_/])(3X|5X|10X)($|[-_/])",
    r"PERP$", r"FUT$", r"\.P$"
]
_EXCLUDE_RE = re.compile("|".join(EXCLUDE_PATTERNS), re.IGNORECASE)

DEFAULT_MEMES = {
    "DOGE","SHIB","PEPE","FLOKI","WIF","BONK","BRETT","HOGE","ELON","AIDOGE","SNEK","PONKE","BOME","MOG","TURBO"
}

def setup_logger():
    try:
        from utils import setup_logger as _sl
        return _sl("universe", level=os.getenv("LOG_LEVEL","INFO"), log_dir=os.getenv("LOG_DIR","logs"))
    except Exception:
        class _L:
            def info(self, *a, **k): print(*a)
            def warning(self, *a, **k): print(*a)
            def error(self, *a, **k): print(*a)
        return _L()

def get_exchange(exchange_id: str):
    import ccxt
    return getattr(ccxt, exchange_id)({"enableRateLimit": True, "timeout": 20000})

def safe_float(x, d=0.0):
    try: return float(x)
    except Exception: return float(d)

def is_spot_market(m: Dict[str,Any]) -> bool:
    return bool(m.get("spot") is True or m.get("type") == "spot")

def is_excluded_symbol(sym: str) -> bool:
    return bool(_EXCLUDE_RE.search(sym))

def estimate_usd_volume(ticker: Dict[str,Any], base: str, quote: str) -> float:
    last  = safe_float(ticker.get("last", ticker.get("close", np.nan)), np.nan)
    qvol  = ticker.get("quoteVolume")
    bvol  = ticker.get("baseVolume")
    info  = ticker.get("info", {})
    if qvol is None:
        qvol = info.get("quoteVolume") or info.get("qv") or info.get("quote_volume")
    if bvol is None:
        bvol = info.get("baseVolume") or info.get("bv") or info.get("base_volume")
    if (quote or "").upper() in STABLE_QUOTES and qvol is not None:
        return safe_float(qvol, 0.0)
    if (bvol is not None) and (not math.isnan(last)):
        return safe_float(bvol, 0.0) * float(last)
    for k in ("volumeUsd","volume_usd","usdVolume","turnoverUsd","quoteTurnover"):
        if k in info: return safe_float(info[k], 0.0)
    return 0.0

def fetch_liquidity_table(ex, markets: Dict[str,Any], quotes: set[str], preselect_max: int, log) -> pd.DataFrame:
    from router import ExchangeRouter
    router = ExchangeRouter()
    try:
        tickers = {}  # router does not have fetch_tickers, fallback to per-symbol
    except Exception as e:
        log.warning(f"fetch_tickers failed: {e}. Falling back to per-symbol.")
        tickers = {}
    rows = []
    for sym, m in markets.items():
        try:
            if not is_spot_market(m): continue
            base = str(m.get("base","")).upper()
            quote= str(m.get("quote","")).upper()
            if quote not in quotes: continue
            if is_excluded_symbol(sym): continue
            if (m.get("active") is False): continue
            t = tickers.get(sym) or {}
            if not t:
                try:
                    t = router.safe_fetch_ticker(sym)
                except Exception:
                    t = {}
            usd_vol = estimate_usd_volume(t, base, quote)
            last = safe_float(t.get("last", t.get("close", np.nan)), np.nan)
            if math.isnan(last) or last <= 0: continue
            rows.append({"symbol": sym, "base": base, "quote": quote, "usd_vol": usd_vol, "last": last})
        except Exception:
            continue
    df = pd.DataFrame(rows)
    if df.empty: return df
    df = df.sort_values("usd_vol", ascending=False).head(preselect_max).reset_index(drop=True)
    return df

def compute_vol_metric(ex, df_liq: pd.DataFrame, timeframe: str, limit: int, log) -> pd.DataFrame:
    if df_liq.empty: return df_liq.assign(vol_metric=0.0)
    vals = []
    for _, r in df_liq.iterrows():
        sym = r["symbol"]
        try:
            from router import ExchangeRouter
            router = ExchangeRouter()
            ohlcv = router.safe_fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
            if not ohlcv or len(ohlcv) < 10: vals.append(0.0); continue
            d = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","vol"])
            atr_abs = (d["high"] - d["low"]).rolling(14).mean().iloc[-1]
            close   = float(d["close"].iloc[-1])
            volp = float(atr_abs / max(1e-9, close)) if pd.notna(atr_abs) else 0.0
            ret = np.log(d["close"]).diff()
            st  = float(ret.rolling(30).std().iloc[-1] or 0.0)
            vals.append(max(0.0, 0.7*volp + 0.3*st))
        except Exception:
            vals.append(0.0)
        time.sleep(0.05)
    df = df_liq.copy(); df["vol_metric"] = vals
    return df

# -------- NEW: experience read --------
def _read_recent_pnl(xp_dir: Path, days: int) -> pd.DataFrame:
    """Read last N days pnl_*.csv and aggregate PnL per symbol."""
    if not xp_dir.exists(): return pd.DataFrame(columns=["symbol","pnl"])
    today = dt.datetime.utcnow().date()
    rows = []
    for i in range(days):
        d = (today - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        f = xp_dir / f"pnl_{d}.csv"
        if not f.exists():  # allow also pnl*.csv (generic)
            f = xp_dir / f"pnl_{d}.csv"
        if not f.exists(): continue
        try:
            df = pd.read_csv(f)
            if "symbol" in df.columns and "pnl" in df.columns:
                rows.append(df[["symbol","pnl"]].copy())
        except Exception:
            continue
    if not rows: return pd.DataFrame(columns=["symbol","pnl"])
    allp = pd.concat(rows, ignore_index=True)
    agg = allp.groupby("symbol", as_index=False)["pnl"].sum()
    return agg

def _score_from_xp(df_pick: pd.DataFrame, agg_pnl: pd.DataFrame, xp_weight: float) -> pd.DataFrame:
    if df_pick.empty or agg_pnl.empty:
        df_pick["xp_score"] = 0.0
        df_pick["score_xp"] = df_pick.get("score", 0.0)
        return df_pick
    m = df_pick.merge(agg_pnl, how="left", on="symbol")
    m["pnl"] = m["pnl"].fillna(0.0)
    # Normalize pnl to 0..1 with symmetric clamp around median
    lo, hi = np.percentile(m["pnl"], 5), np.percentile(m["pnl"], 95)
    if hi - lo <= 1e-9:
        scal = np.zeros_like(m["pnl"])
    else:
        scal = (m["pnl"] - lo) / (hi - lo)
    m["xp_score"] = scal
    # Blend: final = (1-xp_w)*score + xp_w*xp_score
    base = m.get("score", 0.0)
    m["score_xp"] = (1.0 - xp_weight) * base + xp_weight * m["xp_score"]
    m = m.sort_values("score_xp", ascending=False).reset_index(drop=True)
    return m

def score_and_pick(df: pd.DataFrame, min_usd_vol: float, w_liq: float, w_vol: float,
                   max_symbols: int) -> pd.DataFrame:
    if df.empty: return df
    df = df[df["usd_vol"] >= float(min_usd_vol)].copy()
    if df.empty: return df
    df["liq_score"] = (np.log10(df["usd_vol"] + 1) - np.log10(df["usd_vol"].min() + 1))
    if df["liq_score"].max() > 0: df["liq_score"] /= df["liq_score"].max()
    else: df["liq_score"] = 0.0
    vmax = df["vol_metric"].max() or 1.0
    df["vol_score"] = df["vol_metric"] / vmax
    df["score"] = 0.65*df["liq_score"] + 0.35*df["vol_score"]  # base blend
    return df.sort_values("score", ascending=False).head(max_symbols).reset_index(drop=True)

def save_outputs(exchange_id: str, out_json: Path, out_csv: Path, params: Dict[str,Any], df: pd.DataFrame, log):
    payload = {"exchange": exchange_id, "generated_at": int(time.time()), "params": params,
               "symbols": df["symbol"].tolist() if not df.empty else []}
    out_json.write_text(json.dumps(payload, indent=2))
    if not df.empty: df.to_csv(out_csv, index=False)
    else:
        if not out_csv.exists(): pd.DataFrame(columns=["symbol","base","quote","usd_vol","last","vol_metric","score"]).to_csv(out_csv, index=False)
    log.info(f"Saved {len(payload['symbols'])} symbols -> {out_json.name} and {out_csv.name}")
    return payload["symbols"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default=os.getenv("EXCHANGE_ID","bybit"))
    ap.add_argument("--quotes", default=os.getenv("UNIVERSE_QUOTES","USDT,USD,USDC"))
    ap.add_argument("--min_usd_vol", type=float, default=float(os.getenv("UNIVERSE_MIN_USD_VOL","500000")))
    ap.add_argument("--preselect", type=int, default=int(os.getenv("UNIVERSE_PRESELECT","120")))
    ap.add_argument("--max", type=int, default=int(os.getenv("UNIVERSE_MAX","25")))
    ap.add_argument("--tf", default=os.getenv("UNIVERSE_TF","1m"))
    ap.add_argument("--limit", type=int, default=int(os.getenv("UNIVERSE_LIMIT","200")))
    ap.add_argument("--w_liq", type=float, default=float(os.getenv("UNIVERSE_W_LIQ","0.65")))
    ap.add_argument("--w_vol", type=float, default=float(os.getenv("UNIVERSE_W_VOL","0.35")))
    ap.add_argument("--include_regex", default=os.getenv("UNIVERSE_INCLUDE_RE",""))
    ap.add_argument("--exclude_regex", default=os.getenv("UNIVERSE_EXCLUDE_RE",""))
    ap.add_argument("--out", default=os.getenv("UNIVERSE_OUT",""))  # per-exchange out file
    # ---- NEW XP knobs ----
    ap.add_argument("--xp_days", type=int, default=int(os.getenv("UNIVERSE_XP_DAYS","0")), help="Days of recent PnL to weight (0 = off)")
    ap.add_argument("--xp_weight", type=float, default=float(os.getenv("UNIVERSE_XP_WEIGHT","0.25")), help="Blend weight 0..1")
    ap.add_argument("--xp_dir", default=os.getenv("UNIVERSE_XP_DIR","reports/ledger"))
    ap.add_argument("--print", dest="just_print", action="store_true")
    args = ap.parse_args()

    log = setup_logger()
    quotes = {q.strip().upper() for q in args.quotes.split(",") if q.strip()}
    include_re = re.compile(args.include_regex, re.IGNORECASE) if args.include_regex else None
    exclude_re = re.compile(args.exclude_regex, re.IGNORECASE) if args.exclude_regex else None

    ex = get_exchange(args.exchange)
    log.info(f"Loading markets for {args.exchange}…")
    markets = ex.load_markets()

    filtered = {}
    for sym, m in markets.items():
        if not is_spot_market(m): continue
        if include_re and not include_re.search(sym): continue
        if exclude_re and exclude_re.search(sym): continue
        if is_excluded_symbol(sym): continue
        filtered[sym] = m
    log.info(f"Spot markets after masks: {len(filtered)}")

    # Liquidity shortlist
    df_liq = fetch_liquidity_table(ex, filtered, quotes, args.preselect, log)
    if df_liq.empty:
        log.error("No liquid markets found. Try relaxing filters.")
        if args.just_print: print("")
        return
    # Volatility metric on shortlist
    df_liq = compute_vol_metric(ex, df_liq, timeframe=args.tf, limit=args.limit, log=log)

    # Base score
    df_pick = score_and_pick(df_liq, min_usd_vol=args.min_usd_vol, w_liq=args.w_liq, w_vol=args.w_vol, max_symbols=args.max)

    # Experience weighting (optional)
    if args.xp_days > 0 and args.xp_weight > 0:
        xp_dir = Path(args.xp_dir)
        agg_pnl = _read_recent_pnl(xp_dir, args.xp_days)
        df_pick = _score_from_xp(df_pick, agg_pnl, xp_weight=float(args.xp_weight))
        df_pick = df_pick.head(args.max)

    # Output paths
    if args.out:
        out_json = Path(args.out)
        out_csv  = out_json.with_suffix(".csv")
    else:
        out_json = DATA_DIR / f"symbols_{args.exchange.lower()}.json"
        out_csv  = DATA_DIR / f"symbols_{args.exchange.lower()}.csv"

    params = {
        "quotes": sorted(list(quotes)), "min_usd_vol": args.min_usd_vol,
        "preselect": args.preselect, "max": args.max, "tf": args.tf, "limit": args.limit,
        "w_liq": args.w_liq, "w_vol": args.w_vol, "xp_days": args.xp_days, "xp_weight": args.xp_weight,
        "include_regex": args.include_regex, "exclude_regex": args.exclude_regex
    }
    symbols = save_outputs(args.exchange, out_json, out_csv, params, df_pick, log)
    if args.just_print:
        print(",".join(symbols))

if __name__ == "__main__":
    main()


class Universe:
    """Lightweight Universe helper compatible with UltraCore expectations.

    Provides a minimal API used in the codebase:
      - Universe(router).get_all_markets() -> iterable of market symbols
      - Universe(...).get_open_positions() -> iterable of open position symbols

    This implementation is intentionally conservative and uses the provided
    router if available, otherwise attempts to load markets from CCXT.
    """
    def __init__(self, router=None, exchange_id: str | None = None, symbols: list | None = None):
        self.router = router
        self.exchange_id = exchange_id or (getattr(router, 'id', None) if router else os.getenv('EXCHANGE_ID'))
        self._markets = None
        try:
            if symbols:
                # explicit symbol list
                self._markets = {s: {} for s in symbols}
            elif router is not None and hasattr(router, 'markets'):
                self._markets = getattr(router, 'markets') or {}
            else:
                # try to load via ccxt if exchange_id available
                if self.exchange_id:
                    ex = get_exchange(self.exchange_id)
                    self._markets = ex.load_markets() or {}
                else:
                    self._markets = {}
        except Exception:
            # fallback to empty
            self._markets = {}

    def get_all_markets(self):
        try:
            return list(self._markets.keys()) if self._markets else []
        except Exception:
            return []

    def get_open_positions(self):
        """Return a list of open position symbols via ledger.open_positions() if available."""
        try:
            from ledger import open_positions
            ops = open_positions() or []
            return [o.get('symbol') for o in ops if o.get('symbol')]
        except Exception:
            return []
