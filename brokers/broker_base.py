
class BrokerBase:
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 400):
        raise NotImplementedError
    def get_spread_bps(self, symbol: str) -> float:
        raise NotImplementedError
    def market_buy(self, symbol: str, units: float):
        raise NotImplementedError
    def market_sell(self, symbol: str, units: float):
        raise NotImplementedError
    def price(self, symbol: str) -> float:
        raise NotImplementedError
