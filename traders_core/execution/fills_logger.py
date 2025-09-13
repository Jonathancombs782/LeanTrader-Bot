import os, csv, time, threading
from pathlib import Path
from typing import Dict, Any

FILLS_PATH = Path("runtime/logs/fills.csv")
_LOCK = threading.Lock()

HEADER = ["ts","symbol","side","price","qty","fee","fee_ccy","order_id","trade_id","strategy","exchange"]

def _ensure_parent():
    FILLS_PATH.parent.mkdir(parents=True, exist_ok=True)

def _ensure_header():
    if not FILLS_PATH.exists():
        with open(FILLS_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADER)

def on_fill(event: Dict[str, Any]):
    """
    Expected event keys (strings):
      ts(ms), symbol, side('buy'|'sell'), price(float), qty(float),
      fee(float, optional), fee_ccy(str, optional),
      order_id(str, optional), trade_id(str, optional),
      strategy(str, optional), exchange(str, optional)
    """
    _ensure_parent()
    _ensure_header()
    row = [
        int(event.get("ts", int(time.time()*1000))),
        str(event["symbol"]).upper(),
        str(event["side"]).lower(),
        float(event["price"]),
        float(event["qty"]),
        float(event.get("fee", 0.0)),
        str(event.get("fee_ccy", "")),
        str(event.get("order_id","")),
        str(event.get("trade_id","")),
        str(event.get("strategy","")),
        str(event.get("exchange","")),
    ]
    with _LOCK:
        with open(FILLS_PATH, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

