from __future__ import annotations

import os  # noqa: F401  # intentionally kept

from dotenv import load_dotenv
import subprocess
import sys  # added for web3 publisher
from traders_core.services.web3_bias_daemon import start as start_bias
from traders_core.services.pnl_daemon import start as start_pnl
try:
    from traders_core.services.ratio_arb_daemon import start as start_ratio_arb
except Exception:
    start_ratio_arb = None
try:
    from ops.ramp import load_state, save_state, promote, demote, RampPolicy, Mode
    from ops.slack_notify import notify as slack_notify
except Exception:
    load_state = save_state = promote = demote = None  # type: ignore
    RampPolicy = None  # type: ignore
    Mode = None  # type: ignore
    def slack_notify(_: str) -> bool:  # type: ignore
        return False

load_dotenv()


def _daemons_enabled() -> bool:
    return os.getenv("RUN_DAEMONS", "true").strip().lower() in ("1", "true", "yes", "on")


def maybe_start_web3_publisher():
    if not _daemons_enabled():
        return
    if os.getenv("RUN_WEB3_PUBLISHER","false").lower() != "true":
        return
    cfg = os.getenv("WEB3_SIGNALS_CONFIG","lt_plugins/web3_signals/config.yaml")
    cmd = [sys.executable, "-m", "lt_plugins.web3_signals.publisher"]
    env = os.environ.copy()
    env["WEB3_SIGNALS_CONFIG"] = cfg
    subprocess.Popen(cmd, env=env)
    print("[bootstrap] Web3 publisher started")


def bootstrap():
    if _daemons_enabled():
        maybe_start_web3_publisher()
        start_bias()  # start Redis subscriber
        start_pnl()   # start PnL tailer
        # optionally start SOL/BTC ratio arb daemon
        if os.getenv("RUN_RATIO_ARB", "false").lower() == "true":
            if start_ratio_arb:
                start_ratio_arb()
            else:
                print("[bootstrap] ratio_arb_daemon unavailable (import failed)")
    # Ramp mode info
    try:
        if load_state:
            st = load_state()
            print(f"[ramp] current mode={st.mode.value} since {st.start_date}")
    except Exception:
        pass
    # ... existing bootstrap continues (market data, strategies, etc.)
MODE = os.getenv("MODE", "api").lower()  # api | loop

if MODE == "api":
    bootstrap()
    import uvicorn  # noqa: E402

    uvicorn.run(
        "traders_core.api.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=False,
    )
else:
    bootstrap()
    from traders_core.orchestration.jobs import run_forever  # noqa: E402

    run_forever()
