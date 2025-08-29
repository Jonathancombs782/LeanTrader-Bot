Paper run harness

Use `tools/paper_run.py` to run the bot in paper/dry-run mode for smoke testing.

Examples (PowerShell):

```powershell
$env:ENABLE_LIVE='false'; $env:EXCHANGE_ID='paper'; & '.venv/Scripts/python.exe' tools/paper_run.py --minutes 60
```

This runs `run_live.py` in a subprocess for the requested time and then terminates it. It's intended for short smoke-runs; for production continuous running use a process manager and logs.
