"""PaperEngine: the brain's beating heart.

submit_signal() -> risk gate -> size -> simulate fill -> portfolio -> ledger.
Every step is recorded; a breached limit stops the trade and logs why.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import universe as universe_mod
from .fills import simulate_fill
from .ledger import Ledger
from .portfolio import PaperPortfolio, Position
from .receipts import utcnow_iso
from .risk import RiskBreach, RiskLimits, check_new_trade, size_position
from .signals import Signal, SignalSide

# Fail-closed mark age: a mark older than this means the position's risk can
# no longer be validated from a fresh quote, so new orders are blocked until
# the mark is refreshed. 36h covers the daily loop cadence plus one missed
# refresh; a second missed day trips the gate.
MAX_MARK_AGE_S = 36 * 3600

# Two-axis row classification (Nov 9, 2026 — Jonathan: annotate, never delete).
# Axis 1, fill legitimacy: "legit" or "phantom". A phantom fill is a recorded
# fill that never represented a real position entry (Nov 4, 2026: the loop
# re-entered SOL four times in one second while a long was already open).
# Replay skips phantom fills; nothing is ever deleted from the ledger.
# Axis 2, mark state: "ok" or "indeterminate: ...". Every equity row and every
# day_roll baseline carries both axes.
LEGITIMACY_LEGIT = "legit"
LEGITIMACY_PHANTOM = "phantom"


class ReplayError(ValueError):
    """A ledger record that cannot be replayed.

    Raised (fail-closed) for malformed fill/close records — a missing
    field or an unparseable number — instead of the bare KeyError /
    ValueError the old code produced. The message names the record and
    the field, so a bad line can be found and annotated, never silently
    skipped or guessed at.
    """


def _require_fields(rec: dict, fields: list[str], what: str) -> None:
    """Raise ReplayError naming the first missing field of `rec`."""
    for f in fields:
        if rec.get(f) is None:
            raise ReplayError(
                f"malformed {what}: missing required field {f!r} "
                f"in record {rec!r}")


def _as_float(rec: dict, field: str, what: str) -> float:
    """Parse rec[field] as a float or raise ReplayError naming it."""
    try:
        return float(rec[field])
    except (TypeError, ValueError, KeyError) as e:
        raise ReplayError(
            f"malformed {what}: field {field!r} is not a number "
            f"({rec.get(field)!r}) in record {rec!r}") from e


def _note_diagnostic(diagnostics: list[dict], entry: dict) -> None:
    """Append a replay diagnostic once (identical findings are not repeated
    on every refresh pass)."""
    if entry not in diagnostics:
        diagnostics.append(entry)


def _fill_key(rec: dict) -> str:
    """Stable identity for a fill record, for replay/refresh dedupe.

    Callers must validate the record first (_validate_fill_record):
    a close key reads symbol/logged_at/exit_price, which a malformed
    record may not have.
    """
    if rec.get("event") == "close":
        return ("close:%(symbol)s:%(logged_at)s:%(exit_price)s" % rec)
    return "fill:%s" % rec.get("signal_id")


def _validate_fill_record(rec: dict) -> str:
    """Validate one fills-stream record before anything reads it.

    Returns "close" or "fill". Raises ReplayError with a clear diagnostic
    for a missing field, an unparseable number, an unknown event, or an
    invalid side — the cases that used to crash replay with a bare
    KeyError in _fill_key before any guard could run.
    """
    event = rec.get("event") or "fill"
    if event == "close":
        _require_fields(rec, ["symbol", "logged_at", "exit_price", "fee"],
                        "close record")
        _as_float(rec, "exit_price", "close record")
        _as_float(rec, "fee", "close record")
        return "close"
    if event != "fill":
        raise ReplayError(
            f"malformed fill record: unknown event {event!r} in record {rec!r}")
    _require_fields(rec, ["signal_id", "symbol", "side", "quantity",
                          "fill_price", "notional", "fee"], "fill record")
    for f in ("quantity", "fill_price", "notional", "fee"):
        _as_float(rec, f, "fill record")
    if "risk_amount" in rec:
        _as_float(rec, "risk_amount", "fill record")
    try:
        SignalSide(rec["side"])
    except ValueError as e:
        raise ReplayError(
            f"malformed fill record: invalid side {rec.get('side')!r} "
            f"in record {rec!r}") from e
    return "fill"


def _apply_fill_record(engine, rec: dict, accepted: dict,
                       applied: set, diagnostics: list | None = None,
                       seen: set | None = None) -> bool:
    """Apply one ledger fill to an engine. Returns True if it changed state.

    Shared by replay_ledger and PaperEngine.refresh_from_ledger so both see
    the same history. Phantom fills are marked seen but never reconstruct a
    position. Problems are surfaced, never swallowed:
    - malformed records raise ReplayError (fail-closed, clear diagnostic);
    - a duplicate signal_id in one pass, a fill for a symbol that already
      has an open position (a different signal_id overwriting it — the
      Nov 4, 2026 SOL pattern), a fill with no accepted signal, and a
      close with no open position are recorded in `diagnostics` and
      skipped. `diagnostics` defaults to the engine's replay_diagnostics.
    A key already in `applied` is a legit re-read by refresh_from_ledger
    and stays silent; `seen` (one set per pass) is what catches a
    duplicate line inside a single replay.
    """
    if diagnostics is None:
        diagnostics = engine.replay_diagnostics
    kind = _validate_fill_record(rec)
    key = _fill_key(rec)
    if seen is not None:
        if key in seen:
            _note_diagnostic(diagnostics, {
                "kind": "duplicate_fill",
                "key": key,
                "signal_id": rec.get("signal_id"),
                "symbol": rec.get("symbol"),
                "detail": ("duplicate fill record in one replay pass — "
                           "second copy skipped, first copy stands"),
            })
            return False
        seen.add(key)
    if key in applied:
        return False
    applied.add(key)
    if rec.get("legitimacy") == LEGITIMACY_PHANTOM:
        return False
    if kind == "close":
        if rec.get("symbol") not in engine.portfolio.positions:
            _note_diagnostic(diagnostics, {
                "kind": "orphan_close",
                "key": key,
                "symbol": rec.get("symbol"),
                "detail": ("close record for a symbol with no open "
                           "position — skipped, nothing settled"),
            })
            return False
        engine.portfolio.close_position(
            rec["symbol"], float(rec["exit_price"]), float(rec["fee"]))
        return True
    sig = accepted.get(rec.get("signal_id"))
    if sig is None:
        _note_diagnostic(diagnostics, {
            "kind": "orphan_fill",
            "key": key,
            "signal_id": rec.get("signal_id"),
            "symbol": rec.get("symbol"),
            "detail": ("fill with no accepted signal in the ledger — "
                       "skipped, no position reconstructed"),
        })
        return False
    side = SignalSide(rec["side"])
    # A second fill for a symbol that already holds a position would
    # silently overwrite the first Position while keeping its cash debit
    # (the Nov 4, 2026 SOL pattern). Refuse it instead.
    if rec["symbol"] in engine.portfolio.positions:
        _note_diagnostic(diagnostics, {
            "kind": "duplicate_position",
            "key": key,
            "signal_id": rec.get("signal_id"),
            "symbol": rec.get("symbol"),
            "detail": ("fill for a symbol with an open position — "
                       "skipped, first position and its cash debit stand"),
        })
        return False
    # risk_amount is ledgered at fill time (quantity x fill-to-stop
    # distance); fall back to entry-based for older ledgers.
    if "risk_amount" in rec:
        risk_amount = float(rec["risk_amount"])
    else:
        risk_per_unit = abs(_as_float(sig, "entry", "accepted signal")
                            - _as_float(sig, "stop", "accepted signal"))
        risk_amount = float(rec["quantity"]) * risk_per_unit
    position = Position(
        symbol=rec["symbol"],
        side=side,
        quantity=float(rec["quantity"]),
        avg_price=float(rec["fill_price"]),
        stop=_as_float(sig, "stop", "accepted signal"),
        target=_as_float(sig, "target", "accepted signal"),
        risk_amount=risk_amount,
        fees_paid=float(rec["fee"]),
    )
    if side == SignalSide.LONG:
        engine.portfolio.open_position(
            position, float(rec["notional"]) + float(rec["fee"]))
    else:  # short: fee only; proceeds are credited inside open_position
        engine.portfolio.open_position(position, float(rec["fee"]))
    return True


@dataclass
class EngineResult:
    accepted: bool
    reason: str = ""
    position: Position | None = None
    fill_price: float = 0.0


class PaperEngine:
    def __init__(
        self,
        starting_equity: float = 100_000.0,
        limits: RiskLimits | None = None,
        ledger: Ledger | None = None,
        universe: list | None = None,
    ):
        self.limits = limits or RiskLimits()
        self.portfolio = PaperPortfolio.funded(starting_equity)
        self.ledger = ledger or Ledger()
        self.universe = universe or universe_mod.BLUE_CHIPS
        self.prices: dict[str, float] = {}  # last known mids, set via update_prices
        # Per-symbol mark metadata: {"price", "source_observed_at", "received_at"}
        # (both timestamps ISO-8601 UTC). A price WITHOUT a fresh mark is a
        # number the risk gates must not trust — see mark_problems().
        self.marks: dict[str, dict] = {}
        # Ledger fill identities already applied to this engine's portfolio,
        # so refresh_from_ledger() never double-applies a fill.
        self._applied_fill_ids: set[str] = set()
        # Replay findings: orphan fills/closes, duplicate fills, duplicate
        # positions (see _apply_fill_record). In-memory only — replay never
        # writes to the ledger. Malformed records raise ReplayError instead
        # of landing here: a bad line must stop a replay, not be logged past.
        self.replay_diagnostics: list[dict] = []

    # -- market data -----------------------------------------------------
    def update_prices(self, prices: dict[str, float], marks: dict | None = None) -> None:
        """Record last-known mids plus their provenance.

        marks maps symbol -> {"source_observed_at": iso|None, "received_at": iso}.
        Callers that pass no marks get received_at=now; source stays unknown.
        """
        now = utcnow_iso()
        for k, v in prices.items():
            if v > 0:
                self.prices[k] = v
                m = (marks or {}).get(k) or {}
                self.marks[k] = {
                    "price": v,
                    "source_observed_at": m.get("source_observed_at"),
                    "received_at": m.get("received_at") or now,
                }

    def mark_problems(self, max_age_s: int = MAX_MARK_AGE_S) -> list[tuple[str, str]]:
        """Symbols whose risk cannot currently be validated.

        Every open position needs a mark no older than max_age_s. A missing
        mark used to silently drop the position from equity (understating a
        LONG's loss, overstating a SHORT's) — now it is reported instead.
        """
        now = datetime.now(timezone.utc)
        problems: list[tuple[str, str]] = []
        for sym in sorted(self.portfolio.positions):
            m = self.marks.get(sym)
            if m is None:
                problems.append((sym, "missing mark"))
                continue
            try:
                age = (now - datetime.fromisoformat(m["received_at"])).total_seconds()
            except (ValueError, TypeError):
                problems.append((sym, "unparseable mark time"))
                continue
            if age > max_age_s:
                problems.append((sym, f"stale mark ({age / 3600:.1f}h old)"))
        return problems

    def refresh_from_ledger(self) -> int:
        """Apply ledger fills logged since this engine was constructed.

        The fill path must read its own writes. A second process — or a fresh
        engine that never replayed — may have logged fills after this engine
        read the ledger; without this refresh the single-position gate sees
        an empty portfolio and re-enters a symbol it already holds. That is
        how Nov 4, 2026 produced four SOL fills in one second. Returns how
        many fills changed portfolio state.
        """
        accepted = {
            s["signal_id"]: s
            for s in self.ledger.read("signals")
            if s.get("disposition") == "accepted"
        }
        applied = 0
        seen: set[str] = set()
        for rec in self.ledger.read("fills"):
            if _apply_fill_record(self, rec, accepted,
                                  self._applied_fill_ids,
                                  self.replay_diagnostics, seen):
                applied += 1
        return applied

    def roll_day_if_new(self, today: str | None = None) -> bool:
        """Advance the daily PnL baseline when the UTC date has changed.

        The baseline is the current mark-to-market equity; a day_roll event is
        appended so ledger replay can restore the marker. Returns True when a
        roll happened.

        Fail-closed: when any open position's mark is missing or stale, the
        baseline would be computed from an incomplete mark set — Nov 3, 2026
        recorded a $70,094.32 baseline that was cash + SOL only, the GOOG leg
        missing, and printed a fake +27.56% day. Refuse instead, record the
        refusal once per trading day, and leave the old baseline in place.
        """
        today = today or utcnow_iso()[:10]
        if today == self.portfolio.trading_day:
            return False
        problems = self.mark_problems()
        if problems:
            detail = ("day_roll refused — baseline would be computed from an "
                      "indeterminate mark set: "
                      + ", ".join(f"{s} ({r})" for s, r in problems))
            already = any(
                e.get("event") == "day_roll_refused"
                and e.get("trading_day") == today
                for e in self.ledger.read("risk_events"))
            if not already:
                self.ledger.append("risk_events", {
                    "event": "day_roll_refused", "trading_day": today,
                    "reason": detail,
                    "mark_state": ("indeterminate: "
                                   + ",".join(s for s, _ in problems)),
                    "legitimacy": LEGITIMACY_LEGIT,
                })
            return False
        baseline = self.portfolio.equity(self.prices)
        self.portfolio.trading_day = today
        self.portfolio.day_start_equity = baseline
        self.ledger.append("risk_events", {
            "event": "day_roll", "trading_day": today,
            "day_start_equity": baseline,
            "mark_state": "ok",
            "legitimacy": LEGITIMACY_LEGIT,
        })
        return True

    def _reject(self, signal: Signal, limit: str, detail: str) -> EngineResult:
        self.ledger.append("risk_events", {
            "event": "breach", "limit": limit, "detail": detail,
            "signal_id": signal.signal_id, "symbol": signal.symbol,
        })
        self.ledger.append("signals", {**signal.to_dict(), "disposition": "rejected"})
        return EngineResult(False, f"[{limit}] {detail}")

    # -- trading ---------------------------------------------------------
    def submit_signal(self, signal: Signal) -> EngineResult:
        """Validate a signal against risk gates and simulate the fill."""
        # Read our own writes first: fills logged by another process (or by
        # this engine before its last replay) must be visible to the gates
        # below, or the single-position check runs against stale state.
        self.refresh_from_ledger()
        if signal.symbol not in self.prices:
            return EngineResult(False, f"no price for {signal.symbol}")
        price = self.prices[signal.symbol]
        self.roll_day_if_new()
        equity = self.portfolio.equity(self.prices)

        # Fail-closed: every open position needs a fresh, validated mark
        # before ANY new order is gated. A stale or missing mark means the
        # position's true risk is unknown — blocking is safer than pricing
        # the book on a number we cannot validate.
        problems = self.mark_problems()
        if problems:
            detail = ("risk indeterminate — no new orders until marks are "
                      "validated: " + ", ".join(f"{s} ({r})" for s, r in problems))
            return self._reject(signal, "risk_indeterminate", detail)

        # One open position per symbol: a second fill would silently discard
        # the first Position while keeping its cash debit.
        if signal.symbol in self.portfolio.positions:
            return self._reject(
                signal, "single_position_per_symbol",
                f"position already open in {signal.symbol} — "
                "close it before opening another",
            )

        try:
            asset = universe_mod.by_symbol(signal.symbol, self.universe)
            tier = asset.tier
        except KeyError:
            tier = "mid"

        # Size from the actual fill, not the declared entry. The fill price is
        # quantity-independent, so probe it with a unit fill first, then size
        # quantity and risk from the fill-to-stop distance.
        probe = simulate_fill(signal.symbol, signal.side, 1.0, price, tier)
        risk_per_unit = abs(probe.fill_price - signal.stop)
        if risk_per_unit <= 0:
            return self._reject(
                signal, "per_trade_risk",
                "stop equals the simulated fill price — risk is undefined",
            )

        quantity = size_position(equity, self.limits, risk_per_unit,
                                 probe.fill_price)
        trade_risk = quantity * risk_per_unit
        trade_notional = quantity * probe.fill_price

        try:
            check_new_trade(
                self.limits,
                equity=equity,
                trade_risk_amount=trade_risk,
                trade_notional=trade_notional,
                open_risk_amount=self.portfolio.open_risk(),
                symbol_open_notional=self.portfolio.open_notional(signal.symbol, self.prices),
                daily_pnl_pct=self.portfolio.daily_pnl_pct(self.prices),
                drawdown_pct=self.portfolio.drawdown_pct(self.prices),
            )
        except RiskBreach as e:
            self.ledger.append("risk_events", {
                "event": "breach", "limit": e.limit, "detail": str(e),
                "signal_id": signal.signal_id, "symbol": signal.symbol,
            })
            self.ledger.append("signals", {**signal.to_dict(), "disposition": "rejected"})
            return EngineResult(False, str(e))

        fill = simulate_fill(signal.symbol, signal.side, quantity, price, tier)

        position = Position(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            avg_price=fill.fill_price,
            stop=signal.stop,
            target=signal.target,
            risk_amount=trade_risk,
            fees_paid=fill.fee,
        )
        if signal.side.value == "long":
            self.portfolio.open_position(position, fill.notional + fill.fee)
        else:
            self.portfolio.open_position(position, fill.fee)  # fee only; proceeds credited inside

        self.ledger.append("signals", {**signal.to_dict(), "disposition": "accepted"})
        self.ledger.append("fills", {
            "signal_id": signal.signal_id, **fill.to_dict(),
            # the actual risk taken: quantity x fill-to-stop distance
            "risk_amount": trade_risk,
            # axis 1 of the two-axis classification: every new fill is legit;
            # a fill later proven phantom is annotated, never deleted, and
            # replay skips it.
            "legitimacy": LEGITIMACY_LEGIT,
            "at": utcnow_iso(),
        })
        # The fill is already in this engine's portfolio; mark it applied so
        # refresh_from_ledger() never applies it a second time.
        self._applied_fill_ids.add(_fill_key({"signal_id": signal.signal_id}))
        return EngineResult(True, "filled", position, fill.fill_price)

    def close(self, symbol: str) -> float:
        """Close a position with simulated slippage. Returns realized PnL."""
        self.refresh_from_ledger()
        if symbol not in self.prices:
            raise ValueError(f"no price for {symbol}")
        if symbol not in self.portfolio.positions:
            raise ValueError(f"no open position in {symbol}")
        price = self.prices[symbol]
        pos = self.portfolio.positions[symbol]
        try:
            tier = universe_mod.by_symbol(symbol, self.universe).tier
        except KeyError:
            tier = "mid"
        # Closing is the opposite-side order: a long sells into the bid,
        # a short buys back at the offer. Entries pay slippage, so exits do too.
        close_side = SignalSide.LONG if pos.side == SignalSide.SHORT else SignalSide.SHORT
        fill = simulate_fill(symbol, close_side, pos.quantity, price, tier)
        pnl = self.portfolio.close_position(symbol, fill.fill_price, fill.fee)
        rec = self.ledger.append("fills", {
            "event": "close", "symbol": symbol, "exit_price": fill.fill_price,
            "quantity": pos.quantity, "fee": fill.fee,
            "slippage_bps": fill.slippage_bps, "realized_pnl": pnl,
            "at": utcnow_iso(),
        })
        # Already settled in this engine's portfolio; mark it applied so a
        # later refresh never settles it a second time.
        self._applied_fill_ids.add(_fill_key(rec))
        return pnl

    def snapshot_equity(self, record: bool = True) -> dict:
        eq = self.portfolio.equity(self.prices)
        problems = self.mark_problems()
        # Axis 1 (fill legitimacy): replay skips phantom fills, so the
        # positions valued here are legit-only. Name any phantom fills the
        # replay excluded, so the row stays auditable against the ledger.
        phantom_ids = sorted({f.get("signal_id")
                              for f in self.ledger.read("fills")
                              if f.get("legitimacy") == LEGITIMACY_PHANTOM})
        snap = {
            "equity": eq,
            "cash": self.portfolio.cash,
            "realized_pnl": self.portfolio.realized_pnl,
            "open_positions": len(self.portfolio.positions),
            "daily_pnl_pct": self.portfolio.daily_pnl_pct(self.prices),
            "drawdown_pct": self.portfolio.drawdown_pct(self.prices),
            "trading_day": self.portfolio.trading_day,
            "day_start_equity": self.portfolio.day_start_equity,
            # Axis 2 (mark state): ok only when every open position has a
            # fresh, validated mark.
            "mark_state": ("ok" if not problems
                           else "indeterminate: " + ",".join(s for s, _ in problems)),
            # Axis 1 (fill legitimacy) for this row.
            "legitimacy": LEGITIMACY_LEGIT,
            # The mark snapshot this row was valued from: one snapshot per
            # run, so a plan and its equity row can never disagree the way
            # the Nov 3 plan ($89,422.15, SOL $93.47) and row ($89,413.83,
            # SOL $93.43) did — two snapshots seven seconds apart.
            "marks": {sym: dict(self.marks[sym])
                      for sym in sorted(self.prices) if sym in self.marks},
        }
        if phantom_ids:
            snap["phantom_fills_excluded"] = phantom_ids
        # One row per day, written by the evening loop only. A status
        # readout computes the same snapshot but must not record it
        # (record=False) — otherwise every `paper status` call adds a
        # second row for the day.
        if record:
            self.ledger.append("equity", snap)
        return snap


def replay_ledger(ledger: Ledger, starting_equity: float = 100_000.0) -> PaperEngine:
    """Rebuild engine state by replaying the ledger's recorded fills.

    Milestone 1 correctness: commands like `paper.cli status` must reflect the
    recorded trading history, not a freshly funded portfolio. Replay applies
    each recorded fill in ledger order — entry fills reconstruct their
    positions (stop/target/risk come from the matching *accepted* signal),
    close fills settle cash and realized PnL. Peak equity is restored from the
    max recorded equity snapshot so drawdown stays meaningful.

    The replay is read-only with respect to the ledger: nothing is appended.
    """
    engine = PaperEngine(starting_equity=starting_equity, ledger=ledger)

    # Restore the trading-day marker: day_start_equity is meaningless without
    # the date it belongs to. The last day_roll wins; a baseline_correction
    # (appended by a ledger fix, never by the loop) wins over every day_roll
    # before it. Later fills do not move the baseline.
    saw_roll = False
    for ev in ledger.read("risk_events"):
        if ev.get("event") in ("day_roll", "baseline_correction"):
            saw_roll = True
            engine.portfolio.trading_day = ev["trading_day"]
            engine.portfolio.day_start_equity = float(ev["day_start_equity"])
    if not saw_roll:
        # No day_roll has ever been recorded. The freshly funded portfolio
        # claims trading_day=today, which would make roll_day_if_new() a
        # permanent no-op and freeze day_start_equity at the initial funding —
        # so "daily PnL" would read as since-inception forever. Clear the
        # marker so the next roll_day_if_new() performs a genuine bootstrap
        # roll at today's mark-to-market equity and persists the first
        # day_roll event.
        engine.portfolio.trading_day = ""

    accepted = {
        s["signal_id"]: s
        for s in ledger.read("signals")
        if s.get("disposition") == "accepted"
    }
    seen: set[str] = set()
    for rec in ledger.read("fills"):
        _apply_fill_record(engine, rec, accepted, engine._applied_fill_ids,
                           engine.replay_diagnostics, seen)
    peaks = [e.get("equity", 0.0) for e in ledger.read("equity")]
    if peaks:
        engine.portfolio.peak_equity = max(starting_equity, max(peaks))
    return engine
