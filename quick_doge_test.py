import time, pandas as pd
from router import ExchangeRouter

print("starting quick doge test...")
ex = ExchangeRouter()
sym = 'DOGE/USDT'
print("router:", ex.info())
for i in range(3):
    rows = ex.safe_fetch_ohlcv(sym, '1m', limit=5)
    if not rows:
        print(i, "no rows")
    else:
        df = pd.DataFrame(rows, columns=['ts','o','h','l','c','v'])
        print(i, "last close:", df['c'].iloc[-1])
    time.sleep(2)
print("ok")
