#!/usr/bin/env python3
"""Coinbase "satoshi API" CLI.

Examples (run from the repo root):
    python cli/satoshi.py price
    python cli/satoshi.py stats --product BTC-USD
    python cli/satoshi.py candles --granularity ONE_HOUR --days 1
    python cli/satoshi.py accounts        # needs CDP credentials via env

Read-only by default. Order placement is NOT exposed here at all.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marketdata.satoshi_api import (  # noqa: E402
    CoinbaseBrokerageClient,
    CredentialsError,
    PublicMarketData,
    btc_sats_snapshot,
    live_trading_enabled,
)


def _fmt_usd(value: str) -> str:
    try:
        return f"${float(value):,.2f}"
    except ValueError:
        return value


def cmd_price(args: argparse.Namespace) -> int:
    snap = btc_sats_snapshot(product_id=args.product)
    print(f"{snap['product_id']}: {_fmt_usd(snap['price_usd'])}")
    print(f"  1 sat      = ${float(snap['usd_per_sat']):.8f}")
    print(f"  $1 buys    = {float(snap['sats_per_usd']):,.2f} sats")
    print(f"  live trade = {'ENABLED' if live_trading_enabled() else 'disabled (read-only)'}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    client = PublicMarketData()
    prod = client.product(args.product)
    tick = client.ticker(args.product, limit=1)
    price = prod.get("price", "?")
    print(f"{args.product} stats")
    print(f"  price            : {_fmt_usd(str(price))}")
    print(f"  24h change %     : {prod.get('price_percentage_change_24h', '?')}")
    print(f"  24h volume       : {prod.get('volume_24h', '?')}")
    print(f"  best bid / ask   : {tick.get('best_bid', '?')} / {tick.get('best_ask', '?')}")
    print(f"  status           : {prod.get('status', '?')}")
    try:
        sats = float(str(price).replace(",", "")) / 100_000_000 if price != "?" else None
        if sats:
            print(f"  usd per sat      : ${sats:.8f}")
    except ValueError:
        pass
    return 0


def cmd_candles(args: argparse.Namespace) -> int:
    client = PublicMarketData()
    end = int(time.time())
    start = end - args.days * 86400
    rows = client.candles(args.product, start=start, end=end,
                          granularity=args.granularity)
    print(f"{args.product} candles ({args.granularity}, last {args.days}d): {len(rows)} rows")
    for row in rows[:10]:
        print(f"  start={row.get('start')} o={row.get('open')} h={row.get('high')} "
              f"l={row.get('low')} c={row.get('close')} v={row.get('volume')}")
    if len(rows) > 10:
        print(f"  ... ({len(rows) - 10} more)")
    return 0


def cmd_accounts(args: argparse.Namespace) -> int:
    try:
        client = CoinbaseBrokerageClient()
        accounts = client.list_accounts()
    except CredentialsError as exc:
        print(f"credentials error: {exc}", file=sys.stderr)
        return 2
    print(f"{len(accounts)} account(s)")
    for acct in accounts:
        bal = acct.get("available_balance", {}) or {}
        print(f"  {acct.get('currency', '?'):6s} available={bal.get('value', '?')} "
              f"hold={acct.get('hold', {}).get('value', '0')}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Coinbase satoshi API (read-only by default)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("price", help="BTC price + satoshi stats")
    sp.add_argument("--product", default="BTC-USD")
    sp.set_defaults(func=cmd_price)

    ss = sub.add_parser("stats", help="Product stats + best bid/ask")
    ss.add_argument("--product", default="BTC-USD")
    ss.set_defaults(func=cmd_stats)

    sc = sub.add_parser("candles", help="Recent OHLCV candles")
    sc.add_argument("--product", default="BTC-USD")
    sc.add_argument("--granularity", default="ONE_DAY")
    sc.add_argument("--days", type=int, default=1)
    sc.set_defaults(func=cmd_candles)

    sa = sub.add_parser("accounts", help="Account balances (needs CDP credentials)")
    sa.set_defaults(func=cmd_accounts)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
