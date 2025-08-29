# test_all.py
import os, time
from pprint import pprint
os.environ.setdefault("EXCHANGE_ID", "paper")
os.environ.setdefault("EXCHANGE_MODE", "spot")
os.environ.setdefault("ENABLE_LIVE", "false")

from crypto_router import ExchangeRouter

def hr(t): print("\n" + "="*8 + f" {t} " + "="*8)

def main():
    r = ExchangeRouter()
    hr("ROUTER INFO"); pprint(r.info())
    hr("ACCOUNT");     pprint(r.account())
    hr("SAMPLE");      pprint(r.sample_symbols())

    # Spot paper demo (~$5)
    hr("SPOT BUY $5 BTC/USDT")
    pprint(r.place_spot_market("BTC/USDT", "buy", notional=5.0))
    hr("SPOT SELL $5 BTC/USDT")
    pprint(r.place_spot_market("BTC/USDT", "sell", notional=5.0))

    # Futures paper/testnet demo (0.001 BTC @ x3)
    os.environ["EXCHANGE_MODE"] = "linear"
    r = ExchangeRouter()  # re-init in linear
    hr("FUT OPEN 0.001 BTC x3")
    pprint(r.place_futures_market("BTC/USDT", "buy", qty=0.001, leverage=3))
    time.sleep(1)
    hr("FUT CLOSE 0.001 (reduceOnly)")
    pprint(r.place_futures_market("BTC/USDT", "sell", qty=0.001, close=True))

    # One-pass scan
    hr("SCAN TOP MOVERS (snap)")
    snap = r.scan_top_movers(topn=10, quote="USDT", limit=120)
    pprint(snap[:5])

if __name__ == "__main__":
    main()
