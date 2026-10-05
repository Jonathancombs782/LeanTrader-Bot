"""Evening loop: scan the watchlist, build trade plans, run the risk gates.

Usage:  python -m paper.daily_loop [--ledger PATH] [--plans-dir PATH]

For each symbol in the WATCHLIST it fetches daily history, runs the trend
strategy, and submits any signal through the paper engine (risk gates,
position sizing, simulated fill, ledger). Every plan — accepted, rejected,
or "no trend" — lands in paper/plans/YYYY-MM-DD.md for Jonathan's
approve-or-kill review. Paper only: no keys, no accounts, no real money.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from . import feeds, history, strategy
from . import universe as universe_mod
from .engine import replay_ledger
from .ledger import Ledger
from .receipts import utcnow_iso
from .signals import Signal


def run_loop(ledger_path: str = "paper/ledger", plans_dir: str = "paper/plans",
             cache_dir: str = "paper/cache", evidence_dir: str = "paper/evidence") -> dict:
    engine = replay_ledger(Ledger(ledger_path))
    plans: list[dict] = []

    # Current marks: crypto via CoinGecko, stocks via their own history fetch.
    prices, price_receipt = feeds.fetch_prices(
        None, universe_mod.WATCHLIST, cache_dir=cache_dir, evidence_dir=evidence_dir
    )

    for asset in universe_mod.WATCHLIST:
        bars, hist_receipt = history.fetch_daily_bars(
            asset.symbol, universe_mod.WATCHLIST,
            cache_dir=cache_dir, evidence_dir=evidence_dir,
        )
        if asset.symbol in prices:
            price = prices[asset.symbol]
        elif bars:
            price = bars[-1].close  # stock: last daily close
        else:
            plans.append({"symbol": asset.symbol, "disposition": "no_data",
                          "note": "no price and no history — feed down?"})
            continue

        engine.update_prices({asset.symbol: price})
        receipts = tuple(r for r in (price_receipt, hist_receipt) if r)
        crypto = asset.coingecko_id is not None
        signal: Signal | None = strategy.generate_signal(
            asset.symbol, bars, price, receipts, crypto_closes_only=crypto)

        if signal is None:
            closes = [b.close for b in bars]
            plans.append({
                "symbol": asset.symbol, "disposition": "flat",
                "note": (f"no trend at ${price:,.2f} "
                         f"(20d SMA ${strategy.sma(closes, 20) or 0:,.2f}, "
                         f"50d SMA ${strategy.sma(closes, 50) or 0:,.2f})"),
                "price": price,
            })
            continue

        result = engine.submit_signal(signal)
        plan = {
            "symbol": asset.symbol,
            "side": signal.side.value,
            "entry": signal.entry, "stop": signal.stop, "target": signal.target,
            "thesis": signal.thesis,
            "signal_id": signal.signal_id,
            "disposition": "accepted" if result.accepted else "rejected",
            "reason": result.reason,
        }
        if result.accepted and result.position:
            plan["quantity"] = result.position.quantity
            plan["fill_price"] = result.fill_price
        plans.append(plan)

    engine.roll_day_if_new()
    summary = {
        "run_at": utcnow_iso(),
        "plans": plans,
        "equity": engine.portfolio.equity(engine.prices),
        "open_positions": {
            s: {"qty": p.quantity, "side": p.side.value}
            for s, p in engine.portfolio.positions.items()
        },
    }
    _write_plan_file(summary, plans_dir)
    return summary


def _write_plan_file(summary: dict, plans_dir: str) -> Path:
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    path = Path(plans_dir) / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Paper trade plans — {day}", ""]
    lines.append(f"Run at {summary['run_at']}. Portfolio equity: ${summary['equity']:,.2f}.")
    lines.append("")
    for p in summary["plans"]:
        lines.append(f"## {p['symbol']} — {p['disposition'].upper()}")
        if p["disposition"] in ("accepted", "rejected"):
            lines.append(f"- Side: {p['side'].upper()} | Entry ${p['entry']:,.2f} | "
                         f"Stop ${p['stop']:,.2f} | Target ${p['target']:,.2f}")
            if "quantity" in p:
                lines.append(f"- Size: {p['quantity']:,.4f} @ fill ${p['fill_price']:,.2f}")
            lines.append(f"- Thesis: {p['thesis']}")
            if p.get("reason"):
                lines.append(f"- Gate: {p['reason']}")
            lines.append(f"- Signal ID: `{p['signal_id']}` — reply APPROVE or KILL.")
        else:
            lines.append(f"- {p['note']}")
        lines.append("")
    if summary["open_positions"]:
        lines.append("## Open paper positions")
        for s, pos in summary["open_positions"].items():
            lines.append(f"- {s}: {pos['qty']} {pos['side']}")
        lines.append("")
    lines.append("_Paper only. No real money. Jonathan approves or kills every plan._")
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="paper/ledger")
    ap.add_argument("--plans-dir", default="paper/plans")
    ap.add_argument("--cache", default="paper/cache")
    ap.add_argument("--evidence", default="paper/evidence")
    args = ap.parse_args()
    summary = run_loop(args.ledger, args.plans_dir, args.cache, args.evidence)
    for p in summary["plans"]:
        if p["disposition"] in ("accepted", "rejected"):
            extra = f" {p['side'].upper()} entry ${p['entry']:,.2f}"
        else:
            extra = f" {p.get('note', '')}"
        print(f"{p['symbol']}: {p['disposition'].upper()}{extra}")
    print(f"equity: ${summary['equity']:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
