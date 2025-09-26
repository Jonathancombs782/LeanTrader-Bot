import csv
import time
import threading
from pathlib import Path
from typing import Dict, Tuple

FILLS_PATH = Path("runtime/logs/fills.csv")
PNL_PATH   = Path("runtime/logs/pnl.csv")
_LOCK = threading.Lock()

PNL_HEADER = ["ts","symbol","pos_qty","avg_cost","realized_pnl","last_fill_side","last_fill_price","last_fill_qty"]

class PnLEngine:
    """
    Maintains per-symbol:
      - position qty (signed, base units)
      - average cost (USDT/quote)
      - realized PnL (USDT), updated on opposing fills
    Assumes quote currency is stable across fills (e.g., USDT).
    """
    def __init__(self):
        self.pos: Dict[str, float] = {}
        self.avg: Dict[str, float] = {}
        self.realized: Dict[str, float] = {}

    def _apply_fill(self, sym: str, side: str, price: float, qty: float, fee: float = 0.0):
        side = side.lower()
        sgn = 1 if side == "buy" else -1
        q = self.pos.get(sym, 0.0)
        a = self.avg.get(sym, 0.0)
        realized = self.realized.get(sym, 0.0)

        if sgn == 1:
            # BUY: new_avg = (q*a + qty*price + fee) / (q+qty)
            new_q = q + qty
            if new_q <= 1e-12:
                a = 0.0
                q = 0.0
            else:
                a = (q*a + qty*price + fee) / new_q
                q = new_q
        else:
            # SELL: close against avg; realized += (price - a)*qty - fee
            close_qty = min(qty, max(0.0, q))
            realized += (price - a)*close_qty - fee
            q = q - qty
            if q <= 1e-12:
                q = 0.0
                a = 0.0  # flat resets avg

        self.pos[sym] = q
        self.avg[sym] = a
        self.realized[sym] = realized
        return q, a, realized

    def process_fill(self, row: Dict[str, str]) -> Tuple[float,float,float]:
        sym   = row["symbol"].upper()
        side  = row["side"].lower()
        price = float(row["price"])
        qty   = float(row["qty"])
        fee   = float(row.get("fee","0") or 0)
        return self._apply_fill(sym, side, price, qty, fee)

def _ensure_header(path: Path, header: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def tail_fills_and_update_pnl(stop_event, interval_sec=1.0):
    """
    Poll-reads fills.csv and appends a snapshot per new fill into pnl.csv.
    idempotent even if restarted (based on line count in pnl.csv).
    """
    engine = PnLEngine()
    _ensure_header(FILLS_PATH, [])
    _ensure_header(PNL_PATH, PNL_HEADER)

    processed = 0
    while not stop_event.is_set():
        try:
            with open(FILLS_PATH, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            time.sleep(interval_sec)
            continue

        # Fast-forward engine to already processed fills
        if processed == 0:
            for r in rows:
                engine.process_fill(r)
            processed = len(rows)
        else:
            for r in rows[processed:]:
                q,a,real = engine.process_fill(r)
                _write_pnl_snapshot(r, q, a, real)
            processed = len(rows)
        time.sleep(interval_sec)

def _write_pnl_snapshot(fill_row: Dict[str,str], pos_qty: float, avg_cost: float, realized: float):
    with _LOCK:
        with open(PNL_PATH, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                int(fill_row.get("ts", int(time.time()*1000))),
                fill_row["symbol"].upper(),
                round(pos_qty, 12),
                round(avg_cost, 12),
                round(realized, 6),
                fill_row["side"].lower(),
                float(fill_row["price"]),
                float(fill_row["qty"]),
            ])

