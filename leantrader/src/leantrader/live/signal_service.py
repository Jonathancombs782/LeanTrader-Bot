import json
import os
from typing import Dict

import pandas as pd

from ..features.microstructure import engineer
from ..live.charts import render_signal_chart
from ..live.notifier import is_premium, send_photo
from ..policy.dispatcher import run_for_pair
from ..risk.global_lock import GlobalRiskLock
from ..risk.news_filter import NewsCalendar

NEWS_JSON = os.getenv("NEWS_EVENTS_JSON", "data/news/events.json")
TRADE_WEBHOOK = os.getenv("TRADE_WEBHOOK_URL", "https://example.com/trade")  # replace in production


def _load_calendar() -> NewsCalendar:
    cal = NewsCalendar()
    if os.path.exists(NEWS_JSON):
        try:
            with open(NEWS_JSON, "r", encoding="utf-8") as f:
                items = json.load(f)
            for it in items:
                t = pd.to_datetime(it["time"])
                cal.add_event(t.to_pydatetime(), it.get("impact", ""), it.get("currency", ""), it.get("desc", ""))
        except Exception:
            pass
    return cal


def _confluence(eng_frames: Dict[str, pd.DataFrame]) -> int:
    m15 = eng_frames["M15"]
    h1 = eng_frames["H1"]
    score = 0
    ema50 = h1["close"].ewm(span=50, adjust=False).mean().iloc[-1]
    ema200 = h1["close"].ewm(span=200, adjust=False).mean().iloc[-1]
    if ema50 > ema200:
        score += 1
    if h1["adx_14"].iloc[-1] > 20:
        score += 1
    if m15["fvg_score"].iloc[-1] != 0 or (m15.get("rsi_div", pd.Series([0])).iloc[-1] != 0):
        score += 1
    return score


def _explain_signal(ts, pair, eng_frames):
    h1 = eng_frames["H1"]
    m15 = eng_frames["M15"]
    ema50 = h1["close"].ewm(span=50, adjust=False).mean().iloc[-1]
    ema200 = h1["close"].ewm(span=200, adjust=False).mean().iloc[-1]
    adx = float(h1["adx_14"].iloc[-1])
    fvg = float(m15["fvg_score"].iloc[-1])
    rdiv = float(m15.get("rsi_div", pd.Series([0])).iloc[-1])
    return (
        f"*Analytics for {pair} at {pd.to_datetime(ts).strftime('%Y-%m-%d %H:%M')}*\n"
        f"- Trend: EMA50 {'>' if ema50>ema200 else '<='} EMA200\n"
        f"- ADX: `{adx:.1f}`\n"
        f"- FVG score: `{fvg:.0f}` | RSI-div: `{rdiv:.0f}`\n"
        f"- Confluence: trend + ADX + (FVG or RSI-div)"
    )


def _buttons(pair: str, side: str, price: float):
    # Inline keyboard with quick actions and deep-links/webhooks
    data_buy = json.dumps({"action": "trade", "side": "buy", "pair": pair, "price": price})
    data_sell = json.dumps({"action": "trade", "side": "sell", "pair": pair, "price": price})
    return {
        "inline_keyboard": [
            [{"text": "Buy ✅", "callback_data": data_buy}, {"text": "Sell 🟥", "callback_data": data_sell}],
            [
                {"text": "Open in Broker", "url": TRADE_WEBHOOK + f"?pair={pair}&price={price:.5f}"},
                {"text": "Set SL/TP ⚙️", "url": TRADE_WEBHOOK + f"?pair={pair}&config=sl_tp"},
            ],
            [{"text": "Mute Pair 🔕", "callback_data": json.dumps({"action": "mute", "pair": pair})}],
        ]
    }


def to_signal_text(ts, side, pair, rule, px, conf) -> str:
    tstr = pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M")
    return (
        f"*LeanTrader Signal*\n"
        f"*Pair:* `{pair}`\n"
        f"*Side:* *{side.upper()}*\n"
        f"*Rule:* `{rule}`\n"
        f"*Price:* `{px:.5f}`\n"
        f"*Confluence:* `{conf}`\n"
        f"*Time:* `{tstr}`"
    )


def generate_signals(
    frames: Dict[str, pd.DataFrame], pair: str, post: bool = True, min_confluence: int = 3, chat_id: str = None
) -> pd.DataFrame:
    # Risk lock
    if GlobalRiskLock().is_locked():
        return pd.DataFrame()

    # News blackout
    cal = _load_calendar()
    now = pd.Timestamp.utcnow().to_pydatetime()
    if cal.is_blackout(now, pair, lookahead_min=30):
        return pd.DataFrame()

    eng = {k: engineer(v) for k, v in frames.items()}
    sigs = run_for_pair(pair, eng)
    m15 = eng.get("M15") or list(eng.values())[-1]
    sigs["price"] = m15["close"].reindex(sigs.index, method="ffill")
    fired = sigs[(sigs["go"] > 0) & sigs["side"].notna()].copy()
    if len(fired):
        conf = _confluence(eng)
        last = fired.iloc[-1]
        if conf >= min_confluence and post:
            txt = to_signal_text(fired.index[-1], last["side"], pair, last["signal"], float(last["price"]), conf)
            # Render chart image for context
            img_path = "data/tmp_chart.png"
            render_signal_chart(m15.tail(200), img_path, title=f"{pair} — Latest Signal")
            # Send photo with buttons
            btns = _buttons(pair, last["side"], float(last["price"]))
            expl = _explain_signal(fired.index[-1], pair, eng)
            send_photo(
                img_path,
                caption=txt + "\n\n" + expl,
                chat_id=chat_id,
                reply_markup=(btns if is_premium(chat_id) else None),
            )
        return sigs
    return sigs
