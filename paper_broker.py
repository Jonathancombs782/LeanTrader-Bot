# paper_broker.py
import time, random
from typing import Dict, Any, List, Optional, Tuple

class PaperBroker:
    """
    CCXT-like paper broker
      • Spot: USDT-quoted pairs (e.g., BTC/USDT)
      • Futures: Linear USDT-perps (qty in base coin), cross margin, leverage
      • PnL: mark-to-market, realized on reduce; margin reserved on opens
    """

    # ------------------ lifecycle / account / markets ------------------
    def __init__(self, start_cash: float = 5000.0):
        # account
        self.cash: float = float(start_cash)      # free USDT
        self.history: List[Dict[str, Any]] = []

        # spot holdings: base -> qty
        self.holdings: Dict[str, float] = {}

        # futures positions: sym -> {qty, entry, lev, mode}
        self.fut_pos: Dict[str, Dict[str, float]] = {}   # qty (base), entry (USDT), lev (int)

        # simple universe + synthetic prices
        self._symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"]
        self._px: Dict[str, float] = {
            "BTC/USDT": 100000.0,
            "ETH/USDT": 3500.0,
            "SOL/USDT": 150.0,
            "XRP/USDT": 0.6,
            "DOGE/USDT": 0.12,
        }

    def load_markets(self) -> Dict[str, Any]:
        return {s: {"symbol": s, "quote": "USDT"} for s in self._symbols}

    # ------------------ market data (synthetic) ------------------
    def _price(self, symbol: str) -> float:
        p = self._px.get(symbol, 1.0)
        p *= 1.0 + random.uniform(-0.0015, 0.0015)  # ±0.15% drift
        p = max(1e-8, p)
        self._px[symbol] = p
        return p

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        last = self._price(symbol)
        return {"symbol": symbol, "last": last, "timestamp": int(time.time() * 1000)}

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 120) -> List[List[float]]:
        ms = 60_000
        now = int(time.time() // 60 * 60) * 1000
        out, p = [], self._px.get(symbol, 1.0)
        for i in range(limit):
            base = max(1e-8, p * (1 + random.uniform(-0.002, 0.002)))
            high = base * (1 + random.uniform(0, 0.001))
            low  = base * (1 - random.uniform(0, 0.001))
            open_ = base * (1 + random.uniform(-0.0005, 0.0005))
            close = base * (1 + random.uniform(-0.0005, 0.0005))
            vol = abs(random.gauss(1.0, 0.25))
            out.append([now - (limit - i) * ms, float(open_), float(high), float(low), float(close), float(vol)])
            p = close
        self._px[symbol] = p
        return out

    # ------------------ helpers ------------------
    def _split(self, symbol: str) -> Tuple[str, str]:
        base, quote = symbol.split("/")
        if quote != "USDT":
            raise ValueError("PaperBroker supports USDT quote only")
        return base, quote

    def _fut(self, symbol: str) -> Dict[str, float]:
        if symbol not in self.fut_pos:
            self.fut_pos[symbol] = {"qty": 0.0, "entry": 0.0, "lev": 1}
        return self.fut_pos[symbol]

    # -------- margin / pnl (linear perp, cross) --------
    def _fut_notional(self, symbol: str, price: float, qty: float) -> float:
        return abs(qty) * price

    def _fut_used_margin(self, symbol: str, price: float) -> float:
        pos = self._fut(symbol)
        if pos["qty"] == 0:
            return 0.0
        notional = self._fut_notional(symbol, price, pos["qty"])
        return notional / max(1, int(pos["lev"]))

    def _fut_unrealized(self, symbol: str, price: float) -> float:
        pos = self._fut(symbol)
        q, e = pos["qty"], pos["entry"]
        if q == 0:
            return 0.0
        # long: (px - entry) * qty ; short: (entry - px) * |qty|
        return (price - e) * q

    # ------------------ balances / positions ------------------
    def fetch_balance(self) -> Dict[str, Any]:
        totals = {"USDT": {"free": self.cash, "used": 0.0, "total": self.cash}}
        # spot mark
        for base, qty in self.holdings.items():
            sym = f"{base}/USDT"
            px = self._price(sym)
            totals[base] = {"free": qty, "used": 0.0, "total": qty}
            totals["USDT"]["total"] += qty * px

        # futures margin + PnL
        used_margin, unreal = 0.0, 0.0
        for sym, pos in self.fut_pos.items():
            px = self._price(sym)
            used_margin += self._fut_used_margin(sym, px)
            unreal      += self._fut_unrealized(sym, px)

        equity = self.cash + unreal
        free_cash = max(0.0, self.cash - used_margin)  # cross: margin reserved from cash

        return {
            "info": {},
            "total": totals,
            "futures": {
                "used_margin": used_margin,
                "unrealized_pnl": unreal,
                "equity": equity,
                "free_cash": free_cash,
            },
        }

    def fetch_positions(self) -> List[Dict[str, Any]]:
        out = []
        for sym, pos in self.fut_pos.items():
            px = self._price(sym)
            out.append({
                "symbol": sym,
                "contracts": pos["qty"],
                "entryPrice": pos["entry"],
                "leverage": int(pos["lev"]),
                "unrealizedPnl": self._fut_unrealized(sym, px),
                "margin": self._fut_used_margin(sym, px),
                "markPrice": px,
            })
        return out

    # ------------------ trading ------------------
    def create_order(self, symbol: str, type: str, side: str, amount: float,
                     price: Optional[float] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        assert type == "market", "PaperBroker supports market orders only"
        params = params or {}
        ts = int(time.time() * 1000)
        base, _ = self._split(symbol)
        px = self._price(symbol)

        # spot vs futures (by reduceOnly presence or active futures pos/lev)
        reduce_only = bool(params.get("reduceOnly"))
        is_futures  = reduce_only or (symbol in self.fut_pos and self._fut(symbol)["lev"] >= 1 and self._fut(symbol)["qty"] != 0)

        if not is_futures and symbol in self.fut_pos and self._fut(symbol)["lev"] >= 1 and params.get("futures", False):
            is_futures = True

        if not is_futures and "mode" in params and params["mode"] == "futures":
            is_futures = True

        if is_futures:
            ord_obj = self._exec_futures(symbol, side, amount, px, reduce_only)
        else:
            ord_obj = self._exec_spot(symbol, base, side, amount, px)

        self.history.append(ord_obj)
        return ord_obj

    def _exec_spot(self, symbol: str, base: str, side: str, amount: float, px: float) -> Dict[str, Any]:
        if side == "buy":
            cost = amount * px
            if cost > self.cash + 1e-9:
                raise ValueError("insufficient USDT")
            self.cash -= cost
            self.holdings[base] = self.holdings.get(base, 0.0) + amount
        else:
            qty = self.holdings.get(base, 0.0)
            if amount > qty + 1e-12:
                raise ValueError("insufficient base qty")
            self.holdings[base] = qty - amount
            self.cash += amount * px

        return {
            "id": f"paper-{int(time.time()*1000)}",
            "symbol": symbol,
            "side": side,
            "type": "market",
            "amount": float(amount),
            "price": float(px),
            "status": "closed",
            "mode": "spot",
        }

    def _exec_futures(self, symbol: str, side: str, amount: float, px: float, reduce_only: bool) -> Dict[str, Any]:
        pos = self._fut(symbol)
        q_old, e_old, lev = pos["qty"], pos["entry"], max(1, int(pos["lev"]))
        q_delta = amount if side == "buy" else -amount
        q_new = q_old

        realized = 0.0

        if reduce_only:
            # move qty toward zero
            if (q_old > 0 and q_delta < 0) or (q_old < 0 and q_delta > 0):
                close_amt = min(abs(q_delta), abs(q_old))
                realized += (px - e_old) * (close_amt if q_old > 0 else -close_amt)
                q_new = q_old + (close_amt if q_old < 0 else -close_amt)
            else:
                # reduceOnly but direction doesn't reduce -> ignore open
                q_delta = 0.0
        else:
            # allow flipping: first reduce opposite, then open remainder
            if q_old != 0 and (q_old > 0 > q_delta or q_old < 0 < q_delta):
                close_amt = min(abs(q_delta), abs(q_old))
                realized += (px - e_old) * (close_amt if q_old > 0 else -close_amt)
                q_old += close_amt if q_old < 0 else -close_amt
                q_delta = (amount if side == "buy" else -amount) - (close_amt if (side == "buy" and q_old < 0) or (side == "sell" and q_old > 0) else -close_amt)

            # opening remainder
            q_new = q_old + q_delta
            if q_new != 0 and (q_new * q_old >= 0):  # same direction extend or fresh open
                add = abs(q_delta)
                if add > 0:
                    # margin required for the incremental size
                    add_margin = (add * px) / lev
                    if add_margin > self.cash + 1e-9:
                        raise ValueError("insufficient USDT for margin")
                    self.cash -= add_margin
                    # avg entry if same side extend; if fresh open from 0 => entry=px
                    if q_old == 0 or (q_new * q_old > 0):
                        w_old = abs(q_old)
                        pos["entry"] = (e_old * w_old + px * add) / (w_old + add) if w_old > 0 else px

        # update position
        pos["qty"] = q_new
        if q_new == 0:
            pos["entry"] = 0.0  # fully flat releases entry ref

        # release margin when reducing/closing
        used_margin = self._fut_used_margin(symbol, px)
        # free cash cannot be negative; realized PnL credited immediately
        self.cash += realized
        # (cross margin recalculates on next balance call; we keep it simple)

        return {
            "id": f"paper-{int(time.time()*1000)}",
            "symbol": symbol,
            "side": side,
            "type": "market",
            "amount": float(abs(amount)),
            "price": float(px),
            "status": "closed",
            "mode": "futures",
            "reduceOnly": reduce_only,
            "realizedPnl": realized,
            "marginUsed": used_margin,
            "leverage": lev,
        }

    # ------------------ futures controls (CCXT-like) ------------------
    def set_leverage(self, lev: int, symbol: str):
        self._fut(symbol)["lev"] = max(1, int(lev))

    def set_margin_mode(self, mode: str, symbol: str):
        # cross only (stub kept for compatibility)
        return

    # ------------------ misc ------------------
    def options(self) -> Dict[str, Any]:
        return {}
