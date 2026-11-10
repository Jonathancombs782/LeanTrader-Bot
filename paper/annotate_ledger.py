"""One-time ledger annotation for the Nov 9, 2026 fix.

Usage:
  python -m paper.annotate_ledger [--ledger paper/ledger] [--dry-run]

Jonathan's decision (Nov 9, 2026): annotate ALL bogus rows, never delete
anything. This script adds classification fields to existing ledger records
and appends one baseline_correction event. It never changes an original
field value and never removes a record.

What it annotates (verified from the files, Nov 9, 2026):
  - The 4 phantom SOL fills of Nov 4, 2026, 16:15:35Z (identical qty
    249.87506246876563 @ $100.05, only signal_id differs): legitimacy
    "phantom", so replay skips them.
  - The Oct 13, 2026 equity row and every equity row whose day_start is
    broken: frozen at the $100,000 initial funding Oct 5-13 (no day_roll
    was ever recorded, so daily PnL read as since-inception); computed
    with the GOOG leg missing Oct 24-26 and Oct 28-Nov 3 (baseline is
    cash + SOL only — Nov 3's $70,094.32 is exactly that); negative
    Nov 4-8 (computed from a replay that included the phantom fills).
    Classification: mark_state "indeterminate" plus a note naming the
    defect. Rows that already carry a mark_state keep their original
    value; the corrected value goes in the annotation instead.
  - The 15 broken day_roll events (same dates): legitimacy "superseded".
  - Appends one baseline_correction event resetting the baseline to the
    verified Nov 3 close, $89,422.15 (the plan number; the $8.32 gap was
    a 4-cent SOL mark move between two snapshots seven seconds apart).

Idempotent: records that already carry an "annotation" are skipped, and
the baseline_correction is appended only once.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ledger import Ledger
from .receipts import utcnow_iso

PHANTOM_SIGNAL_IDS = {
    "348e5027f454",
    "49fb5b7912b2",
    "f98971af8b76",
    "9d67cc3417e0",
}

# Days whose day_start baseline was computed with the GOOG leg missing
# (baseline is cash + SOL only).
MISSING_LEG_DAYS = {
    "2026-10-24", "2026-10-25", "2026-10-26",
    "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31",
    "2026-11-01", "2026-11-02", "2026-11-03",
}

# Days whose baseline is negative (computed from a replay that included
# the four phantom SOL fills).
NEGATIVE_DAYS = {
    "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08",
}

BASELINE_CORRECTION_EQUITY = 89422.15
BASELINE_CORRECTION_DAY = "2026-11-03"

DECISION = "annotate, never delete — Jonathan, 2026-11-09"


def _annotation(reason: str, **extra) -> dict:
    note = {
        "at": utcnow_iso(),
        "by": "ledger-fix 2026-11-09",
        "reason": reason,
        "decision": DECISION,
    }
    note.update(extra)
    return note


def _annotate_fills(rows: list[dict]) -> tuple[int, int]:
    """Returns (total phantom fills, newly annotated)."""
    total = 0
    changed = 0
    for rec in rows:
        if rec.get("signal_id") not in PHANTOM_SIGNAL_IDS:
            continue
        total += 1
        if "annotation" in rec:
            continue
        rec["legitimacy"] = "phantom"
        rec["annotation"] = _annotation(
            "Duplicate re-entry 2026-11-04T16:15:35Z: the loop re-entered "
            "SOL while long 208.159832 was already open. Identical qty, "
            "price, notional and fee to its three siblings; only signal_id "
            "differs. Replay must skip this fill.")
        changed += 1
    return total, changed


def _equity_defect(rec: dict) -> tuple[str, str, str] | None:
    """(legitimacy, mark_state, note) for a broken equity row, else None."""
    day = rec.get("trading_day", "")
    start = float(rec.get("day_start_equity", 0.0))
    if day in NEGATIVE_DAYS or start < 0:
        return ("phantom-contaminated",
                "indeterminate: day_start negative — baseline computed "
                "from a replay including the 4 phantom SOL fills; equity "
                "row is bogus",
                "Negative day_start baseline; equity computed from a "
                "replay including the 4 phantom SOL fills.")
    if day in MISSING_LEG_DAYS:
        return ("legit",
                "indeterminate: day_start computed with GOOG leg missing "
                "(baseline is cash + SOL only)",
                "day_start baseline computed with GOOG leg missing.")
    if day <= "2026-10-13" and start == 100_000.0:
        note = ("day_start frozen at $100,000 initial funding (no day_roll "
                "recorded); daily PnL is since-inception, not daily")
        if day == "2026-10-13":
            note += ("; equity also excludes the GOOG leg (GOOG mark "
                     "missing at snapshot)")
        return ("legit", "indeterminate: " + note, note)
    return None


def _annotate_equity(rows: list[dict]) -> tuple[int, int]:
    """Returns (total broken equity rows, newly annotated)."""
    total = 0
    changed = 0
    for rec in rows:
        defect = _equity_defect(rec)
        if defect is None:
            continue
        total += 1
        if "annotation" in rec:
            continue
        legitimacy, mark_state, note = defect
        rec["legitimacy"] = legitimacy
        if "mark_state" in rec:
            # Original field values are never rewritten; the corrected
            # classification goes in the annotation instead.
            rec["annotation"] = _annotation(
                note, corrected_mark_state=mark_state)
        else:
            rec["mark_state"] = mark_state
            rec["annotation"] = _annotation(note)
        changed += 1
    return total, changed


def _annotate_day_rolls(rows: list[dict]) -> tuple[int, int]:
    """Returns (total broken day_roll events, newly annotated)."""
    total = 0
    changed = 0
    for rec in rows:
        if rec.get("event") != "day_roll":
            continue
        day = rec.get("trading_day", "")
        if day in MISSING_LEG_DAYS:
            reason = ("Baseline computed with GOOG leg missing "
                      "(cash + SOL only).")
        elif day in NEGATIVE_DAYS or float(rec.get("day_start_equity", 0.0)) < 0:
            reason = ("Baseline negative — computed from a replay "
                      "including the 4 phantom SOL fills.")
        else:
            continue
        total += 1
        if "annotation" in rec:
            continue
        rec["legitimacy"] = "superseded"
        rec["annotation"] = _annotation(
            reason, superseded_by=(
                f"baseline_correction {BASELINE_CORRECTION_DAY} "
                f"${BASELINE_CORRECTION_EQUITY:,.2f}"))
        changed += 1
    return total, changed


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()
            if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="paper.annotate_ledger")
    p.add_argument("--ledger", default="paper/ledger")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.ledger)

    fills = _read(root / "fills.ndjson")
    equity = _read(root / "equity.ndjson")
    events = _read(root / "risk_events.ndjson")

    n_fills, new_fills = _annotate_fills(fills)
    n_equity, new_equity = _annotate_equity(equity)
    n_rolls, new_rolls = _annotate_day_rolls(events)
    has_correction = any(
        e.get("event") == "baseline_correction"
        and float(e.get("day_start_equity", 0.0)) == BASELINE_CORRECTION_EQUITY
        for e in events)

    print(f"phantom fills: {n_fills} total, {new_fills} newly annotated "
          f"(expected 4)")
    print(f"broken equity rows: {n_equity} total, {new_equity} newly "
          f"annotated (expected 31)")
    print(f"broken day_roll events: {n_rolls} total, {new_rolls} newly "
          f"annotated (expected 15)")
    print(f"baseline_correction already present: {has_correction}")
    if n_fills != 4 or n_equity != 31 or n_rolls != 15:
        print("MISMATCH with the verified counts — refusing to write. "
              "Check the ledger before re-running.")
        return 1
    if args.dry_run:
        print("dry run — nothing written")
        return 0

    _write(root / "fills.ndjson", fills)
    _write(root / "equity.ndjson", equity)
    _write(root / "risk_events.ndjson", events)
    if not has_correction:
        Ledger(args.ledger).append("risk_events", {
            "event": "baseline_correction",
            "trading_day": BASELINE_CORRECTION_DAY,
            "day_start_equity": BASELINE_CORRECTION_EQUITY,
            "reason": ("Reset to verified Nov 3 close $89,422.15 (plan "
                       "number; the $8.32 gap was a 4-cent SOL mark move "
                       "between two snapshots seven seconds apart). "
                       "Supersedes broken day_roll baselines Oct 24–Nov 8."),
            "mark_state": "ok",
            "legitimacy": "legit",
        })
        print(f"baseline_correction appended: {BASELINE_CORRECTION_DAY} "
              f"${BASELINE_CORRECTION_EQUITY:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
