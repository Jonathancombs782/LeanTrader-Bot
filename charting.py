"""charting.py
Small helper to render simple price charts with signal markers.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join("runtime", "charts")
os.makedirs(DATA_DIR, exist_ok=True)


def _to_df_like(ohlcv):
    """Accepts list-of-lists [[ts,open,high,low,close,vol], ...] or a pandas.DataFrame-like object.
    Returns a tuple (timestamps, close_prices).
    """
    try:
        import pandas as pd
    except Exception:
        pd = None

    if pd is not None and hasattr(ohlcv, "to_numpy"):
        df = ohlcv
        ts = pd.to_datetime(df["ts"], unit="ms") if "ts" in df.columns else df.iloc[:, 0]
        close = df["close"] if "close" in df.columns else df.iloc[:, 4]
        return list(ts), list(close)

    # assume list of lists: [ [ts, o, h, l, c, v], ... ]
    ts = [datetime.fromtimestamp(int(r[0]) / 1000) for r in ohlcv]
    close = [float(r[4]) for r in ohlcv]
    return ts, close


def plot_signal_chart(
    symbol: str,
    ohlcv,
    entries: Optional[List[Dict[str, Any]]] = None,
    tps: Optional[List[float]] = None,
    sl: Optional[float] = None,
    out_path: Optional[str] = None,
) -> str:
    """Create a PNG chart for `symbol` from OHLCV data.
    entries: list of dicts with {'ts': int(ms) or datetime, 'price': float, 'side': 'buy'|'sell'}
    Returns the path to the generated PNG file.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        raise RuntimeError("matplotlib is required to plot charts")

    ts, close = _to_df_like(ohlcv)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(ts, close, color="C0", lw=1)
    ax.set_title(f"{symbol} — close price")
    ax.set_xlabel("")
    ax.grid(alpha=0.25)

    # plot entries
    if entries:
        for e in entries:
            try:
                e_ts = e.get("ts")
                if isinstance(e_ts, (int, float)):
                    from datetime import datetime

                    e_ts = datetime.fromtimestamp(int(e_ts) / 1000)
                e_px = float(e.get("price"))
                side = (e.get("side") or "").lower()
                marker = "^" if side == "buy" else "v"
                color = "g" if side == "buy" else "r"
                ax.scatter([e_ts], [e_px], marker=marker, color=color, zorder=5)
            except Exception:
                continue

    # TP markers
    if tps:
        for tp in tps:
            ax.axhline(tp, color="blue", lw=0.6, ls="--", alpha=0.7)

    # SL
    if sl:
        ax.axhline(sl, color="black", lw=0.8, ls="-.", alpha=0.7)

    # output
    if not out_path:
        safe_sym = symbol.replace("/", "_").replace(":", "_")
        out_path = os.path.join(DATA_DIR, f"{safe_sym}_{int(datetime.now().timestamp())}.png")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_candlestick(
    symbol: str,
    ohlcv,
    entries: Optional[List[Dict[str, Any]]] = None,
    tps: Optional[List[float]] = None,
    sl: Optional[float] = None,
    ma_periods: Optional[List[int]] = None,
    out_path: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> str:
    """Produce a pro-style candlestick chart (PNG).

    This prefers mplfinance when available. Falls back to the simpler
    `plot_signal_chart` line-chart if mplfinance isn't installed.
    """
    if ma_periods is None:
        ma_periods = [20, 50]

    # prefer mplfinance for polished candlesticks
    try:
        import mplfinance as mpf
        import pandas as pd

        use_mpf = True
    except Exception:
        use_mpf = False

    # convert ohlcv to DataFrame
    def _to_df(ohlcv_rows):
        try:
            import pandas as pd
        except Exception:
            return None
        # accept DataFrame-like
        if hasattr(ohlcv_rows, "to_numpy") and hasattr(ohlcv_rows, "columns"):
            df = ohlcv_rows
            if "ts" in df.columns:
                df = df.rename(
                    columns={
                        "ts": "Date",
                        "open": "Open",
                        "high": "High",
                        "low": "Low",
                        "close": "Close",
                        "vol": "Volume",
                    }
                )
                df = df.set_index(pd.to_datetime(df["Date"], unit="ms"))
            return df

        rows = []
        for r in ohlcv_rows:
            try:
                ts = int(r[0])
                o = float(r[1])
                h = float(r[2])
                low = float(r[3])
                c = float(r[4])
                v = float(r[5]) if len(r) > 5 else 0.0
                rows.append((datetime.fromtimestamp(ts / 1000.0), o, h, low, c, v))
            except Exception:
                continue
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"]).set_index("Date")
        return df

    df = _to_df(ohlcv)
    if df is None and not use_mpf:
        return plot_signal_chart(symbol, ohlcv, entries=entries, tps=tps, sl=sl, out_path=out_path)

    if not out_path:
        safe_sym = symbol.replace("/", "_").replace(":", "_")
        out_path = os.path.join(DATA_DIR, f"{safe_sym}_{int(datetime.now().timestamp())}.png")

    if use_mpf:
        # compute ATR (14)
        try:
            high = df["High"]
            low = df["Low"]
            close = df["Close"]
            prev_close = close.shift(1)
            tr = pd.concat(
                [
                    (high - low).abs(),
                    (high - prev_close).abs(),
                    (low - prev_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            atr = tr.rolling(window=14, min_periods=1).mean()
        except Exception:
            atr = None

        # additional plots
        ap = []
        # ATR as separate panel
        if atr is not None:
            ap.append(mpf.make_addplot(atr, panel=1, color="#ff8800", secondary_y=False, ylabel="ATR"))

        # RSI panel (compute series)
        try:
            delta = df["Close"].diff()
            up = delta.clip(lower=0).rolling(window=14, min_periods=1).mean()
            down = -delta.clip(upper=0).rolling(window=14, min_periods=1).mean()
            rs = up / (down.replace(0, 1e-9))
            rsi_series = 100 - (100 / (1 + rs))
            if not rsi_series.empty:
                ap.append(mpf.make_addplot(rsi_series, panel=2, color="#4e8cff", ylabel="RSI"))
        except Exception:
            pass

        # entries scatter
        if entries:
            try:
                import pandas as _pd

                xs = []
                ys = []
                colors = []
                for e in entries:
                    try:
                        ets = e.get("ts")
                        if isinstance(ets, (int, float)):
                            ets = datetime.fromtimestamp(int(ets) / 1000)
                        elif isinstance(ets, str):
                            ets = datetime.fromisoformat(ets)
                        xs.append(ets)
                        ys.append(float(e.get("price")))
                        colors.append("g" if (e.get("side") or "").lower() == "buy" else "r")
                    except Exception:
                        continue
                if xs:
                    sser = _pd.Series(ys, index=_pd.DatetimeIndex(xs))
                    ap.append(
                        mpf.make_addplot(
                            sser, type="scatter", markersize=80, marker="^", color=["g" if y >= 0 else "r" for y in ys]
                        )
                    )
            except Exception:
                pass

        # TP/SL horizontal lines
        hlines = [float(x) for x in (tps or []) if x]
        if sl:
            hlines.append(float(sl))

        # styling: dark professional theme
        mc = mpf.make_marketcolors(up="#0f9d58", down="#d93025", wick="inherit", edge="inherit", volume="in")
        s = mpf.make_mpf_style(base_mpf_style="nightclouds", marketcolors=mc, gridstyle="--")

        # multi-panel: main + volume + atr (panel=1) + rsi (panel=2)
        try:
            mpf.plot(
                df,
                type="candle",
                mav=ma_periods,
                volume=True,
                addplot=ap if ap else None,
                hlines=hlines if hlines else None,
                style=s,
                figsize=(12, 8),
                panel_ratios=(6, 2, 2),
                savefig=dict(fname=out_path, dpi=180, bbox_inches="tight"),
            )
        except Exception:
            # fallback to simple save
            fig, ax = mpf.figure(figsize=(12, 7))
            ax.plot(df.index, df["Close"], color="#0f9d58")
            fig.savefig(out_path, dpi=150)

        # Post-process: annotate trade duration, metrics box and overlay logo if present
        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.open(out_path).convert("RGBA")
            draw = ImageDraw.Draw(img)
            w, h = img.size
            # annotate trade duration top-right
            if entries:
                try:
                    e = entries[0]
                    ets = e.get("ts")
                    if isinstance(ets, (int, float)):
                        ets_dt = datetime.fromtimestamp(int(ets) / 1000)
                    else:
                        ets_dt = ets
                    last_dt = df.index[-1]
                    txt = f"Entry: {ets_dt.strftime('%Y-%m-%d %H:%M')}  →  Now: {last_dt.strftime('%Y-%m-%d %H:%M')}"
                    # choose font size
                    try:
                        font = ImageFont.truetype("arial.ttf", 14)
                    except Exception:
                        font = ImageFont.load_default()
                    tw, th = draw.textsize(txt, font=font)
                    pad = 8
                    rect_x0 = w - tw - pad * 2 - 10
                    rect_y0 = 10
                    rect_x1 = w - 10
                    rect_y1 = 10 + th + pad * 2
                    # semi-transparent background
                    draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], fill=(0, 0, 0, 160))
                    draw.text((rect_x0 + pad, rect_y0 + pad), txt, font=font, fill=(255, 255, 255, 255))
                except Exception:
                    pass
            # metrics box top-left
            try:
                if metrics:
                    lines = []
                    if metrics.get("trend"):
                        lines.append(f"Trend: {metrics.get('trend')} ({metrics.get('trend_score'):.4f})")
                    if metrics.get("rsi") is not None:
                        lines.append(f"RSI: {metrics.get('rsi')}  ATR: {metrics.get('atr')}")
                    if metrics.get("momentum_pct") is not None:
                        lines.append(f"Momentum: {metrics.get('momentum_pct')}%  Vol: {metrics.get('volatility')}")
                    txt = "\n".join(lines)
                    try:
                        font2 = ImageFont.truetype("arial.ttf", 12)
                    except Exception:
                        font2 = ImageFont.load_default()
                    tw, th = draw.multiline_textsize(txt, font=font2)
                    pad = 8
                    mx0 = 10
                    my0 = 10
                    mx1 = mx0 + tw + pad * 2
                    my1 = my0 + th + pad * 2
                    draw.rectangle([mx0, my0, mx1, my1], fill=(10, 10, 10, 180))
                    draw.multiline_text((mx0 + pad, my0 + pad), txt, font=font2, fill=(255, 255, 255, 255))
            except Exception:
                pass

            # overlay logo if exists at repo root
            try:
                logo_path = os.path.join(os.getcwd(), "logo.png")
                if os.path.exists(logo_path):
                    logo = Image.open(logo_path).convert("RGBA")
                    # resize logo to 10% width
                    lw = int(w * 0.10)
                    lh = int(logo.size[1] * (lw / logo.size[0]))
                    logo = logo.resize((lw, lh), Image.LANCZOS)
                    img.paste(logo, (w - lw - 12, h - lh - 12), logo)
            except Exception:
                pass

            img.save(out_path)
        except Exception:
            pass

        return out_path

    # fallback: non-mplfinance
    return plot_signal_chart(symbol, ohlcv, entries=entries, tps=tps, sl=sl, out_path=out_path)


def analyze_ohlcv(ohlcv, lookback: int = 50) -> dict:
    """Compute simple market snapshot metrics from OHLCV.

    Returns: {trend: str, trend_score: float, rsi: float, atr: float, momentum: float, volatility: float}
    """
    try:
        import numpy as np
        import pandas as pd
    except Exception:
        return {}

    # convert to DataFrame
    df = None
    if hasattr(ohlcv, "to_numpy") and hasattr(ohlcv, "columns"):
        df = ohlcv
        if "ts" in df.columns:
            df = df.rename(
                columns={"ts": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "vol": "Volume"}
            )
            df = df.set_index(pd.to_datetime(df["Date"], unit="ms"))
    else:
        rows = []
        for r in ohlcv:
            try:
                ts = int(r[0])
                o = float(r[1])
                h = float(r[2])
                low = float(r[3])
                c = float(r[4])
                v = float(r[5]) if len(r) > 5 else 0.0
                rows.append((datetime.fromtimestamp(ts / 1000.0), o, h, low, c, v))
            except Exception:
                continue
        if rows:
            df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"]).set_index("Date")

    if df is None or len(df) < 5:
        return {}

    s = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    # ATR
    prev_close = s.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(window=14, min_periods=1).mean().iloc[-1])

    # RSI
    delta = s.diff()
    up = delta.clip(lower=0).rolling(window=14, min_periods=1).mean()
    down = -delta.clip(upper=0).rolling(window=14, min_periods=1).mean()
    rs = up / (down.replace(0, 1e-9))
    rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if not rs.empty else 50.0

    # momentum: slope of 20-period EMA normalized
    ema20 = s.ewm(span=20, adjust=False).mean()
    # compute linear slope via np.polyfit on last lookback
    n = min(len(ema20), lookback)
    y = ema20.iloc[-n:].to_numpy()
    x = np.arange(len(y))
    try:
        m, _ = np.polyfit(x, y, 1)
    except Exception:
        m = 0.0
    # normalize slope by mean price
    trend_score = float(m / (y.mean() if y.mean() else 1.0))

    # momentum: pct change over lookback
    momentum = float((s.iloc[-1] / s.iloc[-n] - 1.0) * 100) if n >= 2 else 0.0

    # volatility: std dev of returns annualized-like simple
    ret = s.pct_change().dropna()
    volatility = float(ret.std() * (252**0.5)) if not ret.empty else 0.0

    # trend label
    if trend_score > 0.0005 and momentum > 0.5:
        trend = "Bullish"
    elif trend_score < -0.0005 and momentum < -0.5:
        trend = "Bearish"
    else:
        trend = "Neutral"

    return {
        "trend": trend,
        "trend_score": trend_score,
        "rsi": round(rsi, 2),
        "atr": round(atr, 6),
        "momentum_pct": round(momentum, 2),
        "volatility": round(volatility, 4),
    }
