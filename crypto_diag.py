# crypto_diag.py
from __future__ import annotations
import json
from crypto_router import ExchangeRouter

def main():
    r = ExchangeRouter()
    print("router ok; paper=", r.paper)
    syms = r.list_scan_symbols()
    print("sample symbols:", syms[:10])
    ohlcv = r.fetch_ohlcv_1m(syms[0], 30)
    print("bars:", len(ohlcv), "last close:", ohlcv[-1][4])
    print("spot paper demo:", r.place_spot_market(syms[0], "buy", notional=5.0))

if __name__ == "__main__":
    main()
