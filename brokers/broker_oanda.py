
import os, time, math
from dotenv import load_dotenv
import oandapyV20
from oandapyV20.endpoints import instruments, pricing, orders, accounts

class OandaBroker:
    def __init__(self):
        load_dotenv()
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        token = os.getenv("OANDA_API_TOKEN")
        env = os.getenv("OANDA_ENV","practice")
        host = "api-fxpractice.oanda.com" if env=="practice" else "api-fxtrade.oanda.com"
        self.client = oandapyV20.API(access_token=token, environment=env)

    def normalize(self, symbol: str) -> str:
        return symbol.replace("_","/").replace("-","/").upper()

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 400):
        # Map timeframe to OANDA granularity
        tf_map = {"1m":"M1","5m":"M5","15m":"M15","1h":"H1","4h":"H4","1d":"D"}
        gran = tf_map.get(timeframe, "M5")
        params = {"granularity": gran, "count": limit, "price":"M"}
        try:
            r = instruments.InstrumentsCandles(instrument=self.normalize(symbol).replace("/","_"), params=params)
            data = self.client.request(r)
            rows = []
            for c in data.get("candles", []):
                t = c.get("time")
                o = float(c["mid"]["o"]) if c.get("mid") else 0.0
                h = float(c["mid"]["h"]) if c.get("mid") else 0.0
                l = float(c["mid"]["l"]) if c.get("mid") else 0.0
                cl = float(c["mid"]["c"]) if c.get("mid") else 0.0
                v = int(c.get("volume") or 0)
                rows.append([t,o,h,l,cl,v])
            return rows
        except Exception as e:
            print(f"[broker_oanda] fetch_ohlcv failed for {symbol}: {e}")
            return []

    def price(self, symbol: str) -> float:
        try:
            r = pricing.PricingInfo(accountID=self.account_id, params={"instruments": self.normalize(symbol).replace("/","_")})
            d = self.client.request(r)
            bids = float(d["prices"][0]["bids"][0]["price"])
            asks = float(d["prices"][0]["asks"][0]["price"])
            return (bids+asks)/2.0
        except Exception as e:
            print(f"[broker_oanda] price fetch failed for {symbol}: {e}")
            return 0.0

    def get_spread_bps(self, symbol: str) -> float:
        r = pricing.PricingInfo(accountID=self.account_id, params={"instruments": self.normalize(symbol).replace("/","_")})
        d = self.client.request(r)
        bid = float(d["prices"][0]["bids"][0]["price"])
        ask = float(d["prices"][0]["asks"][0]["price"])
        return ((ask - bid) / bid) * 10000.0

    def market_buy(self, symbol: str, units: float):
        try:
            data = {"order": {"units": str(int(units)), "instrument": self.normalize(symbol).replace("/","_"), "timeInForce":"FOK","type":"MARKET","positionFill":"DEFAULT"}}
            r = orders.OrderCreate(self.account_id, data=data)
            return self.client.request(r)
        except Exception as e:
            print(f"[broker_oanda] market_buy failed for {symbol}: {e}")
            return {"ok": False, "error": str(e)}

    def market_sell(self, symbol: str, units: float):
        try:
            data = {"order": {"units": str(int(-units)), "instrument": self.normalize(symbol).replace("/","_"), "timeInForce":"FOK","type":"MARKET","positionFill":"DEFAULT"}}
            r = orders.OrderCreate(self.account_id, data=data)
            return self.client.request(r)
        except Exception as e:
            print(f"[broker_oanda] market_sell failed for {symbol}: {e}")
            return {"ok": False, "error": str(e)}
