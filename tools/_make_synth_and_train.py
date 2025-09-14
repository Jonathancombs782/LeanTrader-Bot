"""Create synthetic OHLCV CSV and run trainer (no network required)."""
from __future__ import annotations
import csv
import random
import time
from pathlib import Path

p = Path("runtime") / "data"
p.mkdir(parents=True, exist_ok=True)
csv_path = p / "binance_BTC_USDT_1m.csv"

now = int(time.time() * 1000)
rows = []
price = 30000.0
for i in range(400):
    o = price
    hi = o * (1 + random.random() * 0.001)
    lo = o * (1 - random.random() * 0.001)
    c = o * (1 + (random.random() - 0.5) * 0.002)
    v = random.random() * 10
    ts = now - (400 - i) * 60 * 1000
    rows.append([ts, o, hi, lo, c, v])
    price = c

with csv_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['ts','open','high','low','close','vol'])
    for r in rows:
        w.writerow(r)

print('wrote csv', csv_path)

# run trainer
try:
    from trainer import train_dummy_classifier
except Exception as e:
    print('trainer import error', e)
    raise SystemExit(2)

try:
    out = train_dummy_classifier(str(csv_path))
    print('trainer out:', out)
except Exception as e:
    print('trainer run error', e)
    raise SystemExit(3)

# list models
models_dir = Path('runtime') / 'models'
print('models dir exists', models_dir.exists())
if models_dir.exists():
    for p in models_dir.iterdir():
        print('model', p, p.stat().st_size)
