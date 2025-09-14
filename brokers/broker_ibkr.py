import os

from dotenv import load_dotenv
from ib_insync import IB, Forex, MarketOrder

# time and math not used; keep imports lean


class IBKRBroker:
    def __init__(self):
        load_dotenv()
        host = os.getenv("IB_HOST", "127.0.0.1")
        port = int(os.getenv("IB_PORT", "7497"))
        cid = int(os.getenv("IB_CLIENT_ID", "1"))
        self.ib = IB()
        self.ib.connect(host, port, clientId=cid)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 400):
        """Fetch historical bars from IBKR via ib_insync.

        Returns a list of [timestamp, open, high, low, close, volume]. On error
        returns an empty list.
        """
        # symbol like "EUR/USD" or "EURUSD" — Forex contract wants 'EURUSD'
        contract = Forex(symbol.replace("/", ""))
        barsize = {
            "1m": "1 min",
            "5m": "5 mins",
            "15m": "15 mins",
            "1h": "1 hour",
        }.get(timeframe, "5 mins")

        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="2 D",
                barSizeSetting=barsize,
                whatToShow="MIDPOINT",
                useRTH=False,
            )
            rows = []
            for b in bars[-limit:]:
                # b.date is a datetime; convert to epoch seconds
                rows.append(
                    [
                        int(b.date.timestamp()),
                        b.open,
                        b.high,
                        b.low,
                        b.close,
                        b.volume,
                    ]
                )
            return rows
        except Exception as e:
            print(f"[broker_ibkr] fetch_ohlcv failed for {symbol}: {e}")
            return []

    def price(self, symbol: str) -> float:
        contract = Forex(symbol.replace("/", ""))
        try:
            ticker = self.ib.reqMktData(contract, "", False, False)
            # brief pause to allow market data to populate
            self.ib.sleep(1)
            if getattr(ticker, "bid", None) and getattr(ticker, "ask", None):
                return (ticker.bid + ticker.ask) / 2.0
            return 0.0
        except Exception as e:
            print(f"[broker_ibkr] price failed for {symbol}: {e}")
            return 0.0

    def get_spread_bps(self, symbol: str) -> float:
        contract = Forex(symbol.replace("/", ""))
        try:
            ticker = self.ib.reqMktData(contract, "", False, False)
            self.ib.sleep(1)
            if getattr(ticker, "bid", None) and getattr(ticker, "ask", None) and ticker.bid > 0:
                return ((ticker.ask - ticker.bid) / ticker.bid) * 10000.0
            return 0.0
        except Exception:
            return 0.0

    def market_buy(self, symbol: str, units: float):
        contract = Forex(symbol.replace("/", ""))
        try:
            # IBKR FX often expresses size in 1000s; keep caller semantics by
            # dividing if needed. Caller should pass appropriate units.
            order = MarketOrder("BUY", abs(units))
            return self.ib.placeOrder(contract, order)
        except Exception as e:
            print(f"[broker_ibkr] market_buy failed for {symbol}: {e}")
            return {"ok": False, "error": str(e)}

    def market_sell(self, symbol: str, units: float):
        contract = Forex(symbol.replace("/", ""))
        try:
            order = MarketOrder("SELL", abs(units))
            return self.ib.placeOrder(contract, order)
        except Exception as e:
            print(f"[broker_ibkr] market_sell failed for {symbol}: {e}")
            return {"ok": False, "error": str(e)}
