import os
import sys


def test_ultra_minconf_gating(tmp_path, monkeypatch):
    # Enable Ultra Pro mode with strict minconf and no prior blending
    monkeypatch.setenv("ULTRA_PRO_MODE", "true")
    monkeypatch.setenv("ULTRA_PRO_MINCONF", "0.9")
    monkeypatch.setenv("ULTRA_PRO_PRIOR_WEIGHT", "0.0")
    # Ensure ASCII to avoid emoji issues in CI
    monkeypatch.setenv("TELEGRAM_ASCII", "true")
    # Disable telegram actually sending
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")

    from signals_publisher import publish_signal

    sig = {
        "market": "crypto",
        "symbol": "BTC/USDT",
        "tf": "5m",
        "side": "buy",
        "entry": 100.0,
        "tp1": 101.0,
        "tp2": 102.0,
        "tp3": 103.0,
        "sl": 99.0,
        "confidence": 0.5,  # below ULTRA minconf
        "ts": 1,
    }
    out = publish_signal(sig)
    assert out.get("ok") is False
    assert "conf<" in (out.get("skipped_reason") or "")


def test_ultra_prior_blend_allows(monkeypatch):
    # Enable Ultra with high minconf but weight prior heavily so we pass
    monkeypatch.setenv("ULTRA_PRO_MODE", "true")
    monkeypatch.setenv("ULTRA_PRO_MINCONF", "0.8")
    monkeypatch.setenv("ULTRA_PRO_PRIOR_WEIGHT", "1.0")
    monkeypatch.setenv("TELEGRAM_ASCII", "true")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")

    # Provide a fake pattern_memory.get_score that returns high winrate
    import types

    fake_pm = types.ModuleType("pattern_memory")

    def get_score(sig):
        return {"winrate": 0.95, "avg_out": 0.01, "n": 100}

    fake_pm.get_score = get_score
    sys.modules["pattern_memory"] = fake_pm

    from signals_publisher import publish_signal

    sig = {
        "market": "crypto",
        "symbol": "ETH/USDT",
        "tf": "5m",
        "side": "buy",
        "entry": 100.0,
        "tp1": 101.0,
        "tp2": 102.0,
        "tp3": 103.0,
        "sl": 99.0,
        "confidence": 0.2,  # low raw, prior should lift
        "ts": 1,
    }
    out = publish_signal(sig)
    assert out.get("ok") is True
    assert out.get("id")


def test_confirm_buttons_clean_ascii():
    from tg_utils import build_confirm_buttons_clean

    btns = build_confirm_buttons_clean("abc", include_simulate=True, include_subscribe=True)
    assert isinstance(btns, list) and btns
    assert all(isinstance(r, list) for r in btns)
    # first row has two buttons
    assert len(btns[0]) == 2
    assert "confirm:abc" in (btns[0][0].get("callback_data") or "")
    assert "cancel:abc" in (btns[0][1].get("callback_data") or "")
