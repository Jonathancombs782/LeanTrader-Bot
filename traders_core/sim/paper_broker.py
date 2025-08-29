from __future__ import annotations
import os, json, time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv
from traders_core.observability.metrics import METRICS

load_dotenv()
STATE_PATH = os.getenv("PAPER_STATE","./runtime_paper/paper_state.json")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _load() -> Dict[str,Any]:
    p = Path(STATE_PATH)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"positions":[], "closed":[]}, indent=2))
    return json.loads(p.read_text())

def _save(state: Dict[str,Any]) -> None:
    Path(STATE_PATH).write_text(json.dumps(state, indent=2))

class PaperBroker:
    """
    Simplified long-only market order simulator.
    - Positions: [{symbol, qty, entry, sl, tp, ts_open}]
    - Close rules: call `mark_to_market(symbol, price)` each tick/bar to evaluate SL/TP.
    """
    def __init__(self):
        self.state = _load()

    def positions(self, symbol: Optional[str]=None) -> List[Dict[str,Any]]:
        pos = self.state["positions"]
        return [p for p in pos if (symbol is None or p["symbol"]==symbol)]

    def market_buy(self, symbol: str, price: float, qty: float, fee_rate: float=0.001, sl: Optional[float]=None, tp: Optional[float]=None):
        fee = price * qty * fee_rate
        lot = {"symbol":symbol, "qty":qty, "entry":price, "sl":sl, "tp":tp, "fee":fee, "ts_open":_now()}
        self.state["positions"].append(lot)
        _save(self.state)
        return {"filled_qty":qty, "price":price, "fee":fee}

    def close_all(self, symbol: str, price: float):
        keep = []
        closed = []
        for p in self.state["positions"]:
            if p["symbol"] != symbol:
                keep.append(p); continue
            pnl = (price - p["entry"]) * p["qty"] - p.get("fee",0.0)
            closed.append({**p, "exit":price, "pnl":pnl, "ts_close":_now()})
            METRICS.realized_pnl.labels(venue=("crypto" if symbol.startswith("CRYPTO:") else "mt5"),
                                        symbol=symbol).inc(pnl)
        self.state["positions"] = keep
        self.state["closed"].extend(closed)
        _save(self.state)
        return closed

    def mark_to_market(self, symbol: str, price: float):
        # Check SL/TP hit; if so, close
        changes = []
        keep = []
        for p in self.state["positions"]:
            if p["symbol"] != symbol: keep.append(p); continue
            hit_sl = p["sl"] is not None and price <= p["sl"]
            hit_tp = p["tp"] is not None and price >= p["tp"]
            if hit_sl or hit_tp:
                pnl = ( (p["sl"] if hit_sl else p["tp"]) - p["entry"] ) * p["qty"] - p.get("fee",0.0)
                rec = {**p, "exit": (p["sl"] if hit_sl else p["tp"]), "pnl": pnl, "ts_close": _now()}
                changes.append(rec)
                METRICS.realized_pnl.labels(venue=("crypto" if symbol.startswith("CRYPTO:") else "mt5"),
                                            symbol=symbol).inc(pnl)
            else:
                keep.append(p)
        self.state["positions"] = keep
        self.state["closed"].extend(changes)
        _save(self.state)
        return changes
