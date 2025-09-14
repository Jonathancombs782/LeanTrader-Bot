import matplotlib.pyplot as plt
import pandas as pd


def _candlestick_mplfinance(df: pd.DataFrame, out_path: str, title: str):
    try:
        import mplfinance as mpf  # type: ignore

        d = df.copy()
        d = d[["open", "high", "low", "close"]].copy()
        d.index.name = "Date"
        apds = []
        s1 = d["close"].ewm(span=50, adjust=False).mean()
        s2 = d["close"].ewm(span=200, adjust=False).mean()
        apds.append(mpf.make_addplot(s1, color="orange"))
        apds.append(mpf.make_addplot(s2, color="blue"))
        mpf.plot(
            d.tail(200),
            type="candle",
            style="charles",
            addplot=apds,
            title=title,
            ylabel="Price",
            volume=False,
            savefig=out_path,
        )
        return out_path
    except Exception:
        return None


def render_signal_chart(df: pd.DataFrame, out_path: str, title: str):
    # Prefer a candlestick chart with overlays; fallback to line chart
    p = _candlestick_mplfinance(df, out_path, title)
    if p:
        return p
    plt.figure()
    df["close"].plot(label="Close")
    ema50 = df["close"].ewm(span=50, adjust=False).mean()
    ema200 = df["close"].ewm(span=200, adjust=False).mean()
    ema50.plot(label="EMA50")
    ema200.plot(label="EMA200")
    plt.title(title)
    plt.xlabel("Time")
    plt.ylabel("Price")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return out_path


def render_signal_illustration(
    df: pd.DataFrame,
    out_path: str,
    title: str,
    entry: float,
    sl: float | None = None,
    tps: list[float] | None = None,
):
    """Render a richer chart with entry/SL/TP lines and labels.

    Falls back to basic line chart when mplfinance is unavailable.
    """
    p = _candlestick_mplfinance(df, out_path, title)
    if p:
        # annotate lines via matplotlib overlay (second pass)
        try:
            import matplotlib.pyplot as plt

            img_out = out_path  # save path
            # reopen figure and draw annotations
            plt.figure()
            d = df.tail(200).copy()
            c = d["close"]
            c.plot(label="Close")
            # Volatility band: ±ATR (14)
            try:
                tr = (d["high"] - d["low"]).rolling(14).mean()
                upper = c + tr
                lower = c - tr
                plt.fill_between(c.index, lower, upper, color="#87CEFA", alpha=0.2, label="ATR band")
            except Exception:
                pass
            # Simple Bollinger (20)
            try:
                ma = c.rolling(20).mean()
                sd = c.rolling(20).std(ddof=0)
                up = ma + 2 * sd
                dn = ma - 2 * sd
                plt.plot(up.index, up, color="#999999", linewidth=0.8)
                plt.plot(dn.index, dn, color="#999999", linewidth=0.8)
            except Exception:
                pass
            if entry:
                plt.axhline(entry, color="gold", linestyle="--", linewidth=1, label="Entry")
            if sl is not None:
                plt.axhline(sl, color="red", linestyle=":", linewidth=1, label="SL")
            if tps:
                colors = ["#00aa00", "#00cc66", "#00ff99"]
                for i, tp in enumerate(tps[:3]):
                    plt.axhline(tp, color=colors[i % len(colors)], linestyle=":", linewidth=1, label=f"TP{i+1}")
            plt.title(title)
            plt.legend(loc="best")
            plt.tight_layout()
            plt.savefig(img_out)
            plt.close()
            return img_out
        except Exception:
            return out_path
    # fallback to line chart
    try:
        import matplotlib.pyplot as plt

        plt.figure()
        df["close"].tail(200).plot(label="Close")
        if entry:
            plt.axhline(entry, color="gold", linestyle="--", linewidth=1, label="Entry")
        if sl is not None:
            plt.axhline(sl, color="red", linestyle=":", linewidth=1, label="SL")
        if tps:
            colors = ["#00aa00", "#00cc66", "#00ff99"]
            for i, tp in enumerate(tps[:3]):
                plt.axhline(tp, color=colors[i % len(colors)], linestyle=":", linewidth=1, label=f"TP{i+1}")
        plt.title(title)
        plt.legend(loc="best")
        plt.tight_layout()
        plt.savefig(out_path)
        plt.close()
    except Exception:
        pass
    return out_path
