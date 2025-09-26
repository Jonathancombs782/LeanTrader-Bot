"""FX fetcher via OANDA v20 REST API as a fallback for learning CSVs.

Environment:
  ENABLE_FX_LEARNING_OANDA=true
  OANDA_API_TOKEN=...
  OANDA_ACCOUNT_ID=...
  ***REDACTED*** | live (default practice)

Outputs CSV to runtime/data/fx_<SYMBOL>_<TF>.csv
Supported TF map: M1,M5,M15,M30,H1,H4,D1 -> M1,M5,M15,M30,H1,H4,D
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import List, Dict, Any

import oandapyV20
from oandapyV20.endpoints.instruments import InstrumentsCandles


_TF_MAP = {"M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30", "H1": "H1", "H4": "H4", "D1": "D"}


def _client():
    tok = os.getenv("OANDA_API_TOKEN", "").strip()
    if not tok:
        return None
    env = (os.getenv("OANDA_ENV", "practice").strip().lower())
    practice = env != "live"
    host = "api-fxpractice.oanda.com" if practice else "api-fxtrade.oanda.com"
    return oandapyV20.API(access_token=tok, environment="practice" if practice else "live", headers={"Host": host})


def fetch_fx(symbol: str, tf: str, count: int = 400) -> List[List[float]]:
    api = _client()
    if api is None:
        return []
    gran = _TF_MAP.get(tf.upper())
    if not gran:
        return []
    inst = symbol
    params = {"granularity": gran, "count": min(5000, max(100, int(count))), "price": "M"}
    r = InstrumentsCandles(instrument=inst, params=params)
    try:
        resp = api.request(r)
    except Exception:
        return []
    out: List[List[float]] = []
    for c in resp.get("candles", []):
        try:
            ts = c.get("time")
            o = c["mid"]["o"]
            h = c["mid"]["h"]
            l = c["mid"]["l"]
            cl = c["mid"]["c"]
            v = c.get("volume", 0)
            # convert RFC3339 to ms
            import datetime as _dt
            t = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ms = int(t.timestamp() * 1000)
            out.append([ms, float(o), float(h), float(l), float(cl), float(v)])
        except Exception:
            continue
    return out


def fetch_fx_full(symbol: str, tf: str, total: int = 2000) -> List[List[float]]:
    api = _client()
    if api is None:
        return []
    gran = _TF_MAP.get(tf.upper())
    if not gran:
        return []
    inst = symbol
    out: List[List[float]] = []
    next_from = None
    batch = min(5000, 500)  # keep batch reasonable
    fetched = 0
    # Try to walk back from now by sequential pages
    try:
        import datetime as _dt

        while fetched < total:
            params: Dict[str, Any] = {"granularity": gran, "count": batch, "price": "M"}
            if next_from:
                params["from"] = next_from
            r = InstrumentsCandles(instrument=inst, params=params)
            resp = api.request(r)
            candles = resp.get("candles", [])
            if not candles:
                break
            page_rows: List[List[float]] = []
            last_ts = None
            for c in candles:
                tsr = c.get("time")
                mid = c.get("mid", {})
                if not tsr or not mid:
                    continue
                t = _dt.datetime.fromisoformat(tsr.replace("Z", "+00:00"))
                ms = int(t.timestamp() * 1000)
                last_ts = tsr
                page_rows.append([ms, float(mid["o"]), float(mid["h"]), float(mid["l"]), float(mid["c"]), float(c.get("volume", 0))])
            if not page_rows:
                break
            out.extend(page_rows)
            fetched += len(page_rows)
            # Move 'from' forward using the last candle time
            if last_ts is None:
                break
            # add a small epsilon to avoid duplicate
            next_from = last_ts
            if len(candles) < batch:
                break
    except Exception:
        pass
    return out


def save_csv(symbol: str, tf: str, rows: List[List[float]]) -> str:
    p = Path("runtime") / "data"
    p.mkdir(parents=True, exist_ok=True)
    path = p / f"fx_{symbol}_{tf.upper()}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow(r)
    return str(path)


if __name__ == "__main__":
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "EUR_USD"  # OANDA uses underscore
    tf = sys.argv[2] if len(sys.argv) > 2 else "M15"
    lim = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    rows = fetch_fx(sym, tf, lim)
    if not rows:
        print("no rows")
        sys.exit(1)
    out = save_csv(sym, tf, rows)
    print("wrote", out)
