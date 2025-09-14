import os
import threading
import time
import logging
from typing import Callable, Dict, List

from strategies.loader import create as create_strategy, load_config
from traders_core.connectors.crypto_ccxt import ticker_price, market_buy, market_sell
from traders_core.execution.fills_adapter import record_fill


def _to_pair(sym: str) -> str:
    s = sym.strip().upper()
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}/USDT"
    if s.endswith("USD"):
        return f"{s[:-3]}/USD"
    # fallback: try to split base/quote roughly
    return s.replace("_", "/").replace("-", "/")


class _Tick:
    def __init__(self, last: float):
        self.last = last


class MarketDataPoller:
    def __init__(self, ex_id: str, testnet: bool, symbols: List[str], interval: float = 1.0):
        self.ex_id = ex_id
        self.testnet = testnet
        self.interval = max(0.2, float(interval))
        self.symbols = symbols
        self._subs: Dict[str, List[Callable]] = {}
        self._stop = threading.Event()
        self._thr: threading.Thread | None = None

    def subscribe(self, topic: str, callback: Callable):
        self._subs.setdefault(topic, []).append(callback)

    def _emit(self, topic: str, price: float):
        for cb in self._subs.get(topic, []):
            try:
                cb(_Tick(price))
            except Exception:
                pass

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=0.2)

    def _loop(self):
        while not self._stop.is_set():
            try:
                for sym in self.symbols:
                    pair = _to_pair(sym)
                    px = float(ticker_price(self.ex_id, pair, self.testnet) or 0.0)
                    if px > 0:
                        self._emit(f"ticker.{sym}", px)
                time.sleep(self.interval)
            except Exception:
                time.sleep(self.interval)


class BrokerAdapter:
    def __init__(self, ex_id: str, testnet: bool):
        self.ex_id = ex_id
        self.testnet = testnet

    def create_order(self, symbol: str, side: str, qty: float, order_type: str = "market"):
        pair = _to_pair(symbol)
        side = (side or "").lower()
        # use last price for record keeping
        px = float(ticker_price(self.ex_id, pair, self.testnet) or 0.0)
        if order_type != "market":
            # minimal implementation uses market orders only
            order_type = "market"
        if side == "buy":
            resp = market_buy(self.ex_id, pair, float(qty), self.testnet)
        else:
            resp = market_sell(self.ex_id, pair, float(qty), self.testnet)
        try:
            record_fill(
                symbol=symbol,
                side=side,
                price=px,
                qty=float(qty),
                fee=0.0,
                fee_ccy="USDT",
                order_id=str((resp or {}).get("id", "")) if isinstance(resp, dict) else "",
                trade_id="",
                strategy="ratio_arb",
                exchange=self.ex_id,
            )
        except Exception:
            pass
        return resp


def start():
    """Start the ratio-arb daemon with minimal dependencies.

    Controlled via env:
      - STRATEGY_CONFIG: path to YAML, default runtime/strategies/ratio_arb/config.yaml
      - EXCHANGE_ID: ccxt exchange id (default bybit)
      - BYBIT_TESTNET: use testnet endpoints when true (for bybit)
    """
    cfg_path = os.getenv("RATIO_ARB_CONFIG") or os.getenv(
        "STRATEGY_CONFIG", "runtime/strategies/ratio_arb/config.yaml"
    )
    ex_id = os.getenv("EXCHANGE_ID", "bybit")
    if ex_id.lower() == "paper":
        ex_id = "bybit"
    testnet = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

    # load config for symbols
    try:
        cfg = load_config("ratio_arb", cfg_path)
    except Exception:
        cfg = {
            "symbol_sol": "SOLUSDT",
            "symbol_btc": "BTCUSDT",
            "amount_sol": 0.001,
            "buy_trig": 0.0007,
            "sell_trig": 0.0008,
            "use_market": True,
            "cooldown_ms": 120000,
            "bias_narrow_pct": 15,
        }

    symbols = [cfg.get("symbol_sol", "SOLUSDT"), cfg.get("symbol_btc", "BTCUSDT")]

    # minimal logger/metrics
    logger = logging.getLogger("ratio_arb")

    class _MiniMetrics:
        def gauge(self, name: str, value: float):
            try:
                logger.debug(f"metric {name}={value}")
            except Exception:
                pass

    metrics = _MiniMetrics()

    md = MarketDataPoller(ex_id, testnet, symbols, interval=1.0)
    broker = BrokerAdapter(ex_id, testnet)

    # instantiate strategy (subscriptions happen in __init__)
    _ = create_strategy("ratio_arb", broker, md, logger, metrics, cfg_path=cfg_path)

    # run marketdata poller in background
    md.start()
    print("[ratio_arb_daemon] started")
