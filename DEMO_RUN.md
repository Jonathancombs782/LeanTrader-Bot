DEMO_RUN.md

Quick demo runner (paper mode)

Prerequisites
- Activate the project's venv (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

Ensure your `.env` contains safe values for demo/testing. Recommended:
- EXCHANGE_ID=paper
- ENABLE_LIVE=false
- TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (optional for notifications)

One-shot demo (safe, paper):

```powershell
.venv\Scripts\python.exe -m tools.demo_run
```

Run a short demo loop (3 cycles, 10s pause):

```powershell
.venv\Scripts\python.exe -c "import importlib,time; d=importlib.import_module('tools.demo_run'); [ (d.main(), time.sleep(10)) for _ in range(3) ]"
```

Reconcile & CTF manager (safe):

```powershell
.venv\Scripts\python.exe -m tools.reconcile_positions
.venv\Scripts\python.exe -m tools.ctf_manager
```

Smoke test (quick import + run):

```powershell
.venv\Scripts\python.exe -m tools.smoke_test
```

Notes
- The repo uses environment gating. Do not set `ENABLE_LIVE=true` or change `EXCHANGE_ID` to a real exchange unless you're intentionally going live.
- Paper broker state is persisted in `runtime/paper_state.json` so concurrent runs share holdings.
