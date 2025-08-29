# mt5_list_symbols.py
from __future__ import annotations
import argparse
from typing import List, Tuple

from mt5_adapter import mt5_init
import MetaTrader5 as mt5


def get_symbols_map() -> dict[str, mt5.SymbolInfo]:
    """Return a dict name -> SymbolInfo for quick lookups."""
    arr = mt5.symbols_get()
    return {s.name: s for s in (arr or [])}


def ensure_visible(names: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """
    For each symbol in names:
      - if it exists and hidden -> show it (symbol_select True)
      - collect three lists: shown_now, already_visible, not_found
    """
    shown_now, already_visible, not_found = [], [], []
    m = get_symbols_map()

    for name in names:
        info = m.get(name)
        if info is None:
            not_found.append(name)
            continue
        if info.visible:
            already_visible.append(name)
        else:
            if mt5.symbol_select(name, True):
                shown_now.append(name)
            else:
                # Sometimes symbol_select needs the exact broker name (e.g., EURUSD.i).
                # Try a case-insensitive fuzzy match as a last resort.
                alt = next((k for k in m if k.lower() == name.lower()), None)
                if alt and alt != name and mt5.symbol_select(alt, True):
                    shown_now.append(f"{name} -> {alt}")
                else:
                    not_found.append(name)
    return shown_now, already_visible, not_found


def main():
    ap = argparse.ArgumentParser(description="List and (optionally) auto-show MT5 symbols.")
    ap.add_argument("--want", type=str, default="",
                    help="Comma-separated symbols to ensure visible (e.g. EURUSD,XAUUSD,USDJPY)")
    ap.add_argument("--print", dest="print_count", type=int, default=50,
                    help="How many symbols to print (default 50). Use 0 to skip printing list.")
    args = ap.parse_args()

    # Initialize via your .env (MT5_PATH, MT5_LOGIN, etc.)
    mt5_init()

    # List symbols
    syms = mt5.symbols_get()
    total = len(syms or [])
    print(f"Total broker symbols: {total}")

    if args.print_count:
        print_n = min(args.print_count, total)
        print(f"\nFirst {print_n} symbols:")
        for s in syms[:print_n]:
            print(f"{s.name:18} | visible={str(s.visible):5} | {s.description}")

    # Ensure requested symbols are visible
    want = [x.strip() for x in args.want.split(",") if x.strip()]
    if want:
        print("\nEnsuring these symbols are visible in Market Watch:", ", ".join(want))
        shown, already, missing = ensure_visible(want)

        if shown:
            print("✅ Made visible:", ", ".join(shown))
        if already:
            print("ℹ️ Already visible:", ", ".join(already))
        if missing:
            print("⚠️ Not found / broker naming differs:", ", ".join(missing))
            print("   Tip: open MT5 → Market Watch (Ctrl+M) → right-click → Symbols (Ctrl+U),")
            print("   search for each name; some brokers append suffixes like .i, .m, _pro, etc.")

    print("\nDone.")


if __name__ == "__main__":
    main()
    
