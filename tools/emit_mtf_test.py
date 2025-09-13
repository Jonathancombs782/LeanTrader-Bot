# tools/emit_mtf_test.py
import datetime
import json
import time
from pathlib import Path

p = Path("runtime") / f"signals-{datetime.datetime.utcnow().strftime('%Y%m%d')}.ndjson"
p.parent.mkdir(parents=True, exist_ok=True)

tfs = ["5m", "15m", "1h", "4h"]
now = int(time.time())
signals = []
for tf in tfs:
    s = {
        "market": "crypto",
        "symbol": "BTC/USDT",
        "tf": tf,
        "side": "buy",
        "entry": 60000.0,
        "tp1": 60100.0,
        "tp2": 60200.0,
        "tp3": 60400.0,
        "sl": 59880.0,
        "confidence": 0.95,
        "context": ["MTF test signal (auto)"],
        "ts": now,
    }
    signals.append(s)

with open(p, "a", encoding="utf-8") as f:
    for s in signals:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
print("WROTE", p)
