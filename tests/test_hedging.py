from __future__ import annotations

from hedging.multi_account import Instrument, hedge_plan, net_exposure
from hedging.multi_account import account_state


def test_hedge_plan_risk_parity_weights():
    exposures = {"ETH": 10000.0}
    insts = {
        "ETH": [Instrument(asset="ETH", symbol="ETH/USDT:USDT", vol=0.01), Instrument(asset="ETH", symbol="ETH/USDT:USDT", vol=0.02)],
    }
    plan = hedge_plan(exposures, insts, min_usd=0.0)
    # Two legs with weights 0.8 and 0.2 roughly
    notional = sorted([round(p["notional_usd"], 1) for p in plan])
    assert notional == sorted([-(10000 * 0.8), -(10000 * 0.2)])


def test_option_delta_effect():
    exposures = {"ETH": 10000.0}
    insts = {"ETH": [Instrument(asset="ETH", symbol="ETH-C-OPT", kind="option", vol=0.02, delta=0.5)]}
    plan = hedge_plan(exposures, insts, min_usd=0.0)
    assert len(plan) == 1
    # delta 0.5 implies double notional to hedge
    assert round(plan[0]["notional_usd"], 1) == -20000.0


def test_net_exposure_fake_venue():
    class V:
        id = "paper"

        def __init__(self):
            self._bal = {"total": {"ETH": 2.0, "USDT": 100.0}}
            self._px = {"ETH/USDT": 1500.0}

        def safe_fetch_balance(self):
            return self._bal

        def fetch_ticker(self, symbol):
            return {"last": self._px.get(symbol, 0.0)}

    v = V()
    expo = net_exposure([v], price_router=v)
    # 2 ETH * 1500 + 100 USDT
    assert round(expo["ETH"], 2) == 3000.0
    assert round(expo["USDT"], 2) == 100.0


def test_ccxt_positions_parsing_like_bybit():
    class Ex:
        def __init__(self):
            self._px = {"ETH/USDT:USDT": 2000.0}

        def fetch_positions(self):
            return [
                {
                    "symbol": "ETH/USDT:USDT",
                    "side": "long",
                    "contracts": 2.0,
                    "contractSize": 0.1,  # 0.1 ETH per contract
                    "entryPrice": 1950.0,
                }
            ]

        def fetch_ticker(self, symbol):
            return {"last": self._px.get(symbol, 0.0)}

    st = account_state(Ex())
    # qty should be contracts*contractSize = 0.2 ETH
    pos = st["positions"][0]
    assert pos["symbol"].startswith("ETH/USDT")
    assert abs(pos["qty"] - 0.2) < 1e-6
