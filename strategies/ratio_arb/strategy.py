from decimal import Decimal
import time
from services.web3_bias_daemon import bias_map

class SolBtcRatioArb:
    def __init__(self, broker, marketdata, logger, metrics, cfg):
        self.broker = broker
        self.md = marketdata
        self.log = logger
        self.metrics = metrics
        self.cfg = cfg
        self.sol = None
        self.btc = None
        self.cooldown_until = 0

        # subscribe to tickers using your app's event system
        self.md.subscribe("ticker.SOLUSDT", self.on_sol)
        self.md.subscribe("ticker.BTCUSDT", self.on_btc)

    def on_sol(self, tick):
        self.sol = Decimal(str(tick.last))
        self._maybe_trade()

    def on_btc(self, tick):
        self.btc = Decimal(str(tick.last))
        self._maybe_trade()

    def _maybe_trade(self):
        if self.sol is None or self.btc is None:
            return
        ratio = (self.sol / self.btc).quantize(Decimal("0.00000001"))
        self.metrics.gauge("ratio.sol_btc", float(ratio))

        now = time.time()*1000
        if now < self.cooldown_until:
            return

        buy_trig  = Decimal(str(self.cfg["buy_trig"]))
        sell_trig = Decimal(str(self.cfg["sell_trig"]))
        # apply bias: narrow band when bias>0
        b = bias_map.get(self.cfg["symbol_sol"])
        narrow = Decimal(str(self.cfg.get("bias_narrow_pct", 0))) / Decimal(100)
        if b > 0:
            buy_trig *= (Decimal(1) - narrow)
            sell_trig *= (Decimal(1) - narrow)

        if ratio < buy_trig:
            self._submit("buy")
        elif ratio > sell_trig:
            self._submit("sell")

    def _submit(self, side: str):
        qty = Decimal(str(self.cfg["amount_sol"]))
        order_type = "market" if self.cfg.get("use_market", True) else "limit"
        resp = self.broker.create_order(symbol=self.cfg["symbol_sol"], side=side, qty=qty, order_type=order_type)
        self.log.info({"event":"order_submitted","side":side,"resp":resp})
        self.cooldown_until = time.time()*1000 + int(self.cfg.get("cooldown_ms", 120000))

