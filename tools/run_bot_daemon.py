import datetime
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict

proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

STATE_PATH = os.path.join("reports", "circuit_state.json")


def guess_usdt_balance(bal: Dict[str, Any]) -> float:
    try:
        if isinstance(bal, dict):
            if "total" in bal and isinstance(bal["total"], dict):
                usdt = bal["total"].get("USDT")
                if isinstance(usdt, dict):
                    return float(usdt.get("free") or usdt.get("total") or 0.0)
                try:
                    return float(usdt or 0.0)
                except Exception:
                    pass
            if "free" in bal and isinstance(bal["free"], dict):
                return float(bal["free"].get("USDT") or 0.0)
            fut = bal.get("futures") or {}
            if isinstance(fut, dict) and "free_cash" in fut:
                return float(fut.get("free_cash") or 0.0)
    except Exception:
        pass
    return 0.0


def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"date": str(datetime.date.today()), "cumulative_loss": 0.0}


def save_state(s: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


def run_live_once() -> Dict[str, Any]:
    """
    Call the live runner as a subprocess and return parsed JSON output.
    """
    cmd = [sys.executable, os.path.join("tools", "run_bot_live.py")]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = proc.stdout.strip()
        if not out:
            return {
                "error": "no stdout from run_bot_live",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        try:
            return json.loads(out)
        except Exception:
            return {
                "error": "failed to parse JSON",
                "stdout": out,
                "stderr": proc.stderr,
            }
    except Exception as e:
        return {"error": f"subprocess failed: {e}"}


def get_balance_estimate() -> float:
    # import ExchangeRouter locally to avoid import when not needed
    try:
        from router import ExchangeRouter

        ex = ExchangeRouter()
        bal = ex.safe_fetch_balance()
        return guess_usdt_balance(bal)
    except Exception:
        return 0.0


def main():
    poll_interval = float(os.getenv("POLL_INTERVAL", "60"))  # seconds between cycles
    daily_max_loss = float(os.getenv("DAILY_MAX_LOSS", "100.0"))  # USD
    circuit_enabled = os.getenv("CIRCUIT_BREAKER_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    state = load_state()
    today = str(datetime.date.today())
    if state.get("date") != today:
        state = {"date": today, "cumulative_loss": 0.0}
        save_state(state)

    prev_balance = get_balance_estimate()
    print(f"[daemon] starting: prev_balance_estimate={prev_balance} USD, daily_loss={state['cumulative_loss']} USD")

    try:
        while True:
            # Safety: if circuit enabled and cumulative loss exceeded, stop
            if circuit_enabled and state.get("cumulative_loss", 0.0) >= daily_max_loss:
                print(
                    f"[daemon] circuit-breaker active: cumulative_loss={state.get('cumulative_loss')} >= DAILY_MAX_LOSS={daily_max_loss}"
                )
                break

            result = run_live_once()
            ts = datetime.datetime.utcnow().isoformat()
            entry = {"ts": ts, "result": result}
            # persist a brief log
            log_path = os.path.join("reports", "daemon_log.jsonl")
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(json.dumps(entry) + "\n")

            # compute new balance and delta
            curr_balance = get_balance_estimate()
            delta = prev_balance - curr_balance  # positive if we lost USD
            if delta > 0:
                state["cumulative_loss"] = round(float(state.get("cumulative_loss", 0.0)) + float(delta), 8)
                state["last_delta"] = float(delta)
                state["date"] = today
                save_state(state)
                print(f"[daemon] loss this run: {delta:.6f} USD -> cumulative {state['cumulative_loss']:.6f} USD")
            else:
                print(f"[daemon] no loss this run (delta={delta:.6f})")
            prev_balance = curr_balance

            # check after update
            if circuit_enabled and state.get("cumulative_loss", 0.0) >= daily_max_loss:
                print(f"[daemon] circuit-breaker tripped after run: cumulative_loss={state['cumulative_loss']}")
                break

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("[daemon] interrupted by user, exiting")
    except Exception as e:
        print(f"[daemon] unexpected error: {e}")


if __name__ == "__main__":
    main()
