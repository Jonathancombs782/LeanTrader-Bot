Branch: feature/ultra-defensive-router-tests-ci

Summary:
- Add defensive router/order helpers tests and fix discovery.
- Add CI workflow improvements (deps install, pip cache, import_check, lint/mypy non-blocking, pytest).
- Add `tools/paper_run.py` harness with log rotation and heartbeat file.
- Add tests for Telegram notifier (mocked), synthetic OHLCV fallback, and OCO flows on `PaperBroker`.

Notes for reviewer:
- Tests are isolated and should not call external services. Telegram requests are mocked in tests.
- CI will install optional `requirements.txt` if present; otherwise installs pytest and requests-mock.
- Recommend running a GitHub Actions run to validate CI in the cloud.

How to test locally:
1. Activate venv
2. Run tests: `python -m pytest -q`
3. Run scanner in paper mode: `$env:ENABLE_LIVE='false'; $env:EXCHANGE_ID='paper'; python tools/run_scanner.py`
4. Run paper harness for short smoke-run: `$env:ENABLE_LIVE='false'; $env:EXCHANGE_ID='paper'; & '.venv/Scripts/python.exe' tools/paper_run.py --minutes 60`
