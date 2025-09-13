import os
import pytest


@pytest.fixture(autouse=True)
def _env_dedupe_off(monkeypatch):
    # Disable signal dedupe across tests to avoid interference when publisher is exercised
    monkeypatch.setenv("SIGNALS_DEDUPE_WINDOW_SEC", "0")
    yield

