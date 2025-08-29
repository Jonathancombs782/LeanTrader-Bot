# test_router.py
import os, json, time
from router import ExchangeRouter  # uses your new router.py

def j(x): return json.dumps(x, indent=2, default=str)

def banner(t): print("\n" + "="*10 + " " + t + " " + "="*10)

def test_account(r):
    banner("ROUTER INFO")
    print(j(r.info))
    banner("ACCOUNT")
    print(j(r.account()))
    banner("SAMPLE SYMBOLS")
    print(j(r.sample_symbols()))

def test_spot(r, sym="BTC/USDT"):
    banner(f"SPOT PAPER DEMO ({sym})")
    print("# buy ~5 USDT notional")
    print(j(r.place_spot_market(sym, "buy", notional=5)))
    print("# sell ~5 USDT notional")
    print(j(r.place_spot_market(sym, "sell", notional=5)))

def test_futures(r, sym="BTC/USDT", qty=0.001, lev=3):
    banner(f"FUTURES PAPER DEMO ({sym})")
    # open
    print("# open long")
    print(j(r.place_futures_market(sym, "buy", qty=qty, leverage=lev)))
    time.sleep(1)
    # close (reduce)
    print("# close long (reduceOnly)")
    print(j(r.place_futures_market(sym, "sell", qty=qty, leverage=lev, close=True)))

def main():
    r = ExchangeRouter()
    test_account(r)

    mode = (os.getenv("EXCHANGE_MODE") or "spot").lower()
    paper = os.getenv("CRYPTO_PAPER", "true").lower() == "true"

    # Spot paper demo always safe
    test_spot(r, "BTC/USDT")

    # Futures demo if router supports it (linear USDT-perp)
    try:
        if mode == "linear" or hasattr(r, "place_futures_market"):
            test_futures(r, "BTC/USDT", qty=0.001, lev=int(os.getenv("FUT_LEVERAGE", "3")))
    except Exception as e:
        banner("FUTURES TEST SKIPPED")
        print(str(e))

if __name__ == "__main__":
    main()
