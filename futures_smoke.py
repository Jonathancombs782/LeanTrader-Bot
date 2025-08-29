# futures_smoke.py
from __future__ import annotations
from dotenv import load_dotenv
from crypto_router import ExchangeRouter

load_dotenv()

def main():
    r = ExchangeRouter()

    print("\n--- SPOT test ---")
    print(r.place_spot_market("DOGE/USD", "buy", 5))

    print("\n--- FUTURES test (isolated x5, hedge off, TP/SL inline) ---")
    print(r.place_futures_market(
        "BTC/USDT",
        "buy",
        0.001,
        leverage=5,
        margin_mode="isolated",
        hedge=False,
        tp=None,    # fill a price if you want, e.g. 69000
        sl=None     # e.g. 62000
    ))

if __name__ == "__main__":
    main()
