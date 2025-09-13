# mt5_single_shot.py
from __future__ import annotations

import argparse
from typing import Any, Dict, Optional  # noqa: F401  # intentionally kept


# Lazy import mt5_adapter functions at runtime so importing this module
# doesn't fail in environments without MetaTrader5 installed.
def _import_mt5_helpers():
    try:
        import importlib

        mod = importlib.import_module("mt5_adapter")
        return (
            getattr(mod, "account_summary_lines", lambda: []),
            getattr(mod, "bars_df", lambda *a, **k: __import__("pandas").DataFrame()),
            getattr(mod, "mt5_init", lambda: None),
            getattr(mod, "order_send_market", lambda *a, **k: {"ok": False, "comment": "mt5 unavailable"}),
        )
    except Exception:
        # try file-based import as a fallback
        try:
            import importlib.util
            import sys
            from pathlib import Path

            repo_root = Path(__file__).resolve().parent
            candidate = repo_root / "mt5_adapter.py"
            if candidate.exists():
                spec = importlib.util.spec_from_file_location("mt5_adapter", str(candidate))
                mod = importlib.util.module_from_spec(spec)
                sys.modules["mt5_adapter"] = mod
                spec.loader.exec_module(mod)  # type: ignore
                return (
                    getattr(mod, "account_summary_lines", lambda: []),
                    getattr(mod, "bars_df", lambda *a, **k: __import__("pandas").DataFrame()),
                    getattr(mod, "mt5_init", lambda: None),
                    getattr(mod, "order_send_market", lambda *a, **k: {"ok": False, "comment": "mt5 unavailable"}),
                )
        except Exception:
            pass

        def account_summary_lines():
            return []

        def bars_df(symbol, timeframe, limit=50):
            import pandas as _pd

            return _pd.DataFrame()

        def mt5_init():
            return None

        def order_send_market(*args, **kwargs):
            return {"ok": False, "comment": "mt5 unavailable"}

        return account_summary_lines, bars_df, mt5_init, order_send_market


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Place a single MT5 market order (demo-safe)")
    ap.add_argument("--symbol", required=True, help="e.g. EURUSD, XAUUSD")
    ap.add_argument("--timeframe", default="M5", help="M1,M5,M15,M30,H1,H4,D1,W1,MN1")
    ap.add_argument("--side", choices=["buy", "sell"], required=True)
    ap.add_argument("--lots", type=float, default=0.01)

    ap.add_argument("--dry_run", default="no", help="yes/no — if yes, only prints the request")
    # Optional explicit SL/TP prices (skip to let broker accept 0.0)
    ap.add_argument("--sl", type=float, default=None)
    ap.add_argument("--tp", type=float, default=None)

    return ap.parse_args()


def print_tail(symbol: str, timeframe: str) -> None:
    try:
        _, bars_df, _, _ = _import_mt5_helpers()
        df = bars_df(symbol, timeframe, limit=50)
        tail = df.tail(5)
        want = [
            "time",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread",
            "real_volume",
        ]
        cols = [c for c in want if c in tail.columns]
        print("\nTail (last bars):")
        if tail.empty or not cols:
            print("(no bars to display)")
        else:
            print(tail[cols].to_string(index=False))
    except Exception as e:
        print(f"[warn] bars df error: {e}")


def main() -> None:
    args = parse_args()
    account_summary_lines, _, mt5_init, _ = _import_mt5_helpers()
    mt5_init()
    for line in account_summary_lines():
        print(line)

    print_tail(args.symbol, args.timeframe)

    # Build and (optionally) send order
    print("\nRequest:", end=" ")
    print(f"{args.side.upper()} {args.symbol} lots={args.lots:.2f} " f"SL={args.sl or '-'}  TP={args.tp or '-'}")

    if str(args.dry_run).lower() in ("yes", "y", "true", "1"):
        print("[dry-run] not sending order.")
        return

    _, _, _, order_send_market = _import_mt5_helpers()
    res: Dict[str, Any] = order_send_market(
        symbol=args.symbol,
        side=args.side,
        lots=args.lots,
        sl=args.sl,
        tp=args.tp,
        deviation=20,
    )

    print("request:", res.get("request"))
    print(
        "retcode:",
        res.get("retcode"),
        "comment:",
        res.get("comment"),
        "deal:",
        res.get("deal"),
        "order:",
        res.get("order"),
    )


if __name__ == "__main__":
    main()
