
import os, time, math
from dotenv import load_dotenv
import MetaTrader5 as mt5

class MT5Broker:
    def __init__(self):
        load_dotenv()
        login = int(os.getenv("MT5_LOGIN") or 0)
        password = os.getenv("MT5_PASSWORD") or ""
        server = os.getenv("MT5_SERVER") or ""
        if not mt5.initialize():
            raise RuntimeError("MetaTrader5 initialize failed")
        if login and password and server:
            if not mt5.login(login, password=password, server=server):
                raise RuntimeError("MetaTrader5 login failed")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 400):
        try:
            tf_map = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15, "1h": mt5.TIMEFRAME_H1}
            tf = tf_map.get(timeframe, mt5.TIMEFRAME_M5)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
            rows = []
            for r in rates:
                rows.append([r['time'], r['open'], r['high'], r['low'], r['close'], r['tick_volume']])
            return rows
        except Exception as e:
            print(f"[broker_mt5] fetch_ohlcv failed for {symbol}: {e}")
            return []

    def price(self, symbol: str) -> float:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return 0.0
            return (tick.bid + tick.ask) / 2.0
        except Exception as e:
            print(f"[broker_mt5] price failed for {symbol}: {e}")
            return 0.0

    def get_spread_bps(self, symbol: str) -> float:
        try:
            tick = mt5.symbol_info_tick(symbol)
            if not tick or tick.bid == 0: return 0.0
            return ((tick.ask - tick.bid) / tick.bid) * 10000.0
        except Exception as e:
            print(f"[broker_mt5] get_spread_bps failed for {symbol}: {e}")
            return 0.0

    def market_buy(self, symbol: str, units: float):
        try:
            lot = units / 100000.0  # rough convert units to lots
            req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot, "type": mt5.ORDER_TYPE_BUY, "deviation": 10, "magic": 234000, "type_filling": mt5.ORDER_FILLING_FOK}
            return mt5.order_send(req)
        except Exception as e:
            print(f"[broker_mt5] market_buy failed for {symbol}: {e}")
            return {"ok": False, "error": str(e)}

    def market_sell(self, symbol: str, units: float):
        try:
            lot = units / 100000.0
            req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot, "type": mt5.ORDER_TYPE_SELL, "deviation": 10, "magic": 234000, "type_filling": mt5.ORDER_FILLING_FOK}
            return mt5.order_send(req)
        except Exception as e:
            print(f"[broker_mt5] market_sell failed for {symbol}: {e}")
            return {"ok": False, "error": str(e)}
