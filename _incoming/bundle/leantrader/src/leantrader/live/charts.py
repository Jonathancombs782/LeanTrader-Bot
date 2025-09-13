import os

import matplotlib.pyplot as plt
import pandas as pd


def render_signal_chart(df: pd.DataFrame, out_path: str, title: str):
    # Single-figure plot: price close and simple EMA50/EMA200 overlay
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
