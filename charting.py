"""charting.py
Small helper to render simple price charts with signal markers.
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join("reports")
os.makedirs(DATA_DIR, exist_ok=True)

def _to_df_like(ohlcv):
    """Accepts list-of-lists [[ts,open,high,low,close,vol], ...] or a pandas.DataFrame-like object.
    Returns a tuple (timestamps, close_prices).
    """
    try:
        import pandas as pd
    except Exception:
        pd = None

    if pd is not None and hasattr(ohlcv, 'to_numpy'):
        df = ohlcv
        ts = pd.to_datetime(df['ts'], unit='ms') if 'ts' in df.columns else df.iloc[:,0]
        close = df['close'] if 'close' in df.columns else df.iloc[:,4]
        return list(ts), list(close)

    # assume list of lists: [ [ts, o, h, l, c, v], ... ]
    ts = [datetime.fromtimestamp(int(r[0])/1000) for r in ohlcv]
    close = [float(r[4]) for r in ohlcv]
    return ts, close

def plot_signal_chart(symbol: str, ohlcv, entries: Optional[List[Dict[str, Any]]] = None,
                      tps: Optional[List[float]] = None, sl: Optional[float] = None,
                      out_path: Optional[str] = None) -> str:
    """Create a PNG chart for `symbol` from OHLCV data.
    entries: list of dicts with {'ts': int(ms) or datetime, 'price': float, 'side': 'buy'|'sell'}
    Returns the path to the generated PNG file.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        raise RuntimeError("matplotlib is required to plot charts")

    ts, close = _to_df_like(ohlcv)

    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot(ts, close, color='C0', lw=1)
    ax.set_title(f"{symbol} — close price")
    ax.set_xlabel("")
    ax.grid(alpha=0.25)

    # plot entries
    if entries:
        for e in entries:
            try:
                e_ts = e.get('ts')
                if isinstance(e_ts, (int, float)):
                    from datetime import datetime
                    e_ts = datetime.fromtimestamp(int(e_ts)/1000)
                e_px = float(e.get('price'))
                side = (e.get('side') or '').lower()
                marker = '^' if side == 'buy' else 'v'
                color = 'g' if side == 'buy' else 'r'
                ax.scatter([e_ts], [e_px], marker=marker, color=color, zorder=5)
            except Exception:
                continue

    # TP markers
    if tps:
        for tp in tps:
            ax.axhline(tp, color='blue', lw=0.6, ls='--', alpha=0.7)

    # SL
    if sl:
        ax.axhline(sl, color='black', lw=0.8, ls='-.', alpha=0.7)

    # output
    if not out_path:
        safe_sym = symbol.replace('/','_').replace(':','_')
        out_path = os.path.join(DATA_DIR, f"{safe_sym}_{int(datetime.now().timestamp())}.png")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
