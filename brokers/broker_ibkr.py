
import os, time, math
from dotenv import load_dotenv
from ib_insync import IB, Forex, MarketOrder

class IBKRBroker:
    def __init__(self):
        load_dotenv()
        host = os.getenv("IB_HOST","127.0.0.1")
        port = int(os.getenv("IB_PORT","7497"))
        cid = int(os.getenv("IB_CLIENT_ID","1"))
        self.ib = IB()
        self.ib.connect(host, port, clientId=cid)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 400):
        # symbol like "EURUSD"
        contract = Forex(symbol.replace("/",""))
        barsize = {"1m":"1 min","5m":"5 mins","15m":"15 mins","1h":"1 hour"}.get(timeframe,"5 mins")
            try:
                bars = self.ib.reqHistoricalData(contract, endDateTime="", durationStr="2 D", barSizeSetting=barsize, whatToShow='MIDPOINT', useRTH=False)
                rows = []
                for b in bars[-limit:]:
                    rows.append([b.date.timestamp(), b.open, b.high, b.low, b.close, b.volume])
                return rows
            except Exception as e:
                print(f"[broker_ibkr] fetch_ohlcv failed for {symbol}: {e}")
                return []

    def price(self, symbol: str) -> float:
        contract = Forex(symbol.replace("/",""))
            try:
                ticker = self.ib.reqMktData(contract, '', False, False)
                self.ib.sleep(1)
                return (ticker.bid + ticker.ask)/2 if ticker.bid and ticker.ask else 0.0
            except Exception as e:
                print(f"[broker_ibkr] price failed for {symbol}: {e}")
                return 0.0

    def get_spread_bps(self, symbol: str) -> float:
        contract = Forex(symbol.replace("/",""))
        ticker = self.ib.reqMktData(contract, '', False, False)
        self.ib.sleep(1)
        if ticker.bid and ticker.ask and ticker.bid > 0:
            return ((ticker.ask - ticker.bid) / ticker.bid) * 10000.0
        return 0.0

    def market_buy(self, symbol: str, units: float):
        contract = Forex(symbol.replace("/",""))
            try:
                order = MarketOrder('BUY', abs(units)/1000)  # IBKR FX size in 1k?
                return self.ib.placeOrder(contract, order)
            except Exception as e:
                print(f"[broker_ibkr] market_buy failed for {symbol}: {e}")
                return {"ok": False, "error": str(e)}

    def market_sell(self, symbol: str, units: float):
        contract = Forex(symbol.replace("/",""))
            try:
                order = MarketOrder('SELL', abs(units)/1000)
                return self.ib.placeOrder(contract, order)
            except Exception as e:
                print(f"[broker_ibkr] market_sell failed for {symbol}: {e}")
                return {"ok": False, "error": str(e)}
