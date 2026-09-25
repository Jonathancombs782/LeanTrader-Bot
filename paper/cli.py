"""CLI: python -m paper.cli <command>

Commands:
  signal   Submit a paper signal (LONG/SHORT) with live public prices.
  status   Show portfolio equity, positions, PnL.
  verify   Re-hash every stored receipt payload; report failures.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import feeds
from .engine import PaperEngine
from .ledger import Ledger
from .signals import Signal, SignalSide


def _engine(ledger_root: str) -> PaperEngine:
    return PaperEngine(ledger=Ledger(ledger_root))


def cmd_signal(args: argparse.Namespace) -> int:
    engine = _engine(args.ledger)
    prices, receipt = feeds.fetch_prices(
        [args.symbol], cache_dir=args.cache, evidence_dir=args.evidence
    )
    if args.symbol not in prices:
        print(f"no public price for {args.symbol} — signal not submitted")
        return 2
    engine.update_prices(prices)
    receipts = (receipt,) if receipt else ()
    signal = Signal(
        symbol=args.symbol,
        side=SignalSide(args.side),
        entry=args.entry,
        stop=args.stop,
        target=args.target,
        thesis=args.thesis,
        receipts=receipts,
        inputs={"entry": args.entry, "stop": args.stop, "target": args.target,
                "price": prices[args.symbol], "source": "cli"},
    )
    result = engine.submit_signal(signal)
    if result.accepted:
        print(f"ACCEPTED {signal.signal_id} {args.symbol} {args.side} "
              f"qty={result.position.quantity:.6f} @ {result.fill_price:.4f}")
        return 0
    print(f"REJECTED: {result.reason}")
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    engine = _engine(args.ledger)
    prices, _ = feeds.fetch_prices(cache_dir=args.cache, evidence_dir=args.evidence)
    engine.update_prices(prices)
    snap = engine.snapshot_equity()
    print(json.dumps(snap, indent=2))
    for sym, pos in engine.portfolio.positions.items():
        px = prices.get(sym)
        upnl = pos.unrealized_pnl(px) if px else float("nan")
        print(f"  {sym} {pos.side.value} qty={pos.quantity:.6f} "
              f"avg={pos.avg_price:.4f} uPnL={upnl:,.2f}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    ledger = Ledger(args.ledger)
    failures = ledger.verify_receipts()
    if not failures:
        print("all stored receipt payloads verify OK")
        return 0
    for sig_id, bad in failures.items():
        print(f"FAILED {sig_id}: {bad}")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="paper")
    p.add_argument("--ledger", default="paper/ledger")
    p.add_argument("--cache", default="paper/cache")
    p.add_argument("--evidence", default="paper/evidence")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("signal")
    s.add_argument("symbol")
    s.add_argument("side", choices=["long", "short"])
    s.add_argument("--entry", type=float, required=True)
    s.add_argument("--stop", type=float, required=True)
    s.add_argument("--target", type=float, required=True)
    s.add_argument("--thesis", required=True)
    s.set_defaults(func=cmd_signal)

    st = sub.add_parser("status")
    st.set_defaults(func=cmd_status)

    v = sub.add_parser("verify")
    v.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
