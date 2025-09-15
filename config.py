# config.py — compatibility wrapper
import os
from settings import settings  # the file we created earlier

# Re-export as variables (or keep your previous names if you had them)
TRADING_MODE = settings.trading_mode
CRYPTO_TESTNET = settings.crypto_testnet
PYTHONUNBUFFERED = settings.python_unbuffered

BYBIT_API_KEY = settings.bybit_api_key
BYBIT_API_SECRET = settings.bybit_api_secret

BINANCE_API_KEY = settings.binance_api_key
BINANCE_API_SECRET = settings.binance_api_secret

TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
TELEGRAM_CHAT_ID = settings.telegram_chat_id

# MT5 (only works locally)
MT5_LOGIN = settings.mt5_login
MT5_PASSWORD = settings.mt5_password
MT5_SERVER = settings.mt5_server

# ---- Quantum integration flags ----
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, None)
    if raw is None:
        return bool(default)
    val = str(raw).strip().lower()
    return val in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return float(default)


Q_ENABLE_QUANTUM: bool = _env_bool("Q_ENABLE_QUANTUM", False)
Q_USE_RUNTIME: bool = _env_bool("Q_USE_RUNTIME", True)
IBM_QUANTUM_API_KEY: str = os.getenv("IBM_QUANTUM_API_KEY", "").strip()
IBM_MIN_QUBITS: int = _env_int("IBM_MIN_QUBITS", 127)

# ---- Risk guard flags ----
RISK_MAX_LOSS_PER_SYMBOL: float = _env_float("RISK_MAX_LOSS_PER_SYMBOL", 0.02)
RISK_MAX_DAILY_LOSS: float = _env_float("RISK_MAX_DAILY_LOSS", 0.03)
RISK_MAX_ACCOUNT_DD: float = _env_float("RISK_MAX_ACCOUNT_DD", 0.10)
RISK_LIMITS_PCT: bool = _env_bool("RISK_LIMITS_PCT", True)

# ---- Feature flags (routing/toggles) ----
FEATURE_GA_EVOLUTION: bool = _env_bool("FEATURE_GA_EVOLUTION", False)
FEATURE_SENTIMENT_FUSION: bool = _env_bool("FEATURE_SENTIMENT_FUSION", False)
FEATURE_ARBITRAGE: bool = _env_bool("FEATURE_ARBITRAGE", False)
FEATURE_ONCHAIN_FUSION: bool = _env_bool("FEATURE_ONCHAIN_FUSION", False)
FEATURE_DEX_GUARDS: bool = _env_bool("FEATURE_DEX_GUARDS", False)
FEATURE_MOON_RADAR: bool = _env_bool("FEATURE_MOON_RADAR", False)
FEATURE_IDEAS_SLACK: bool = _env_bool("FEATURE_IDEAS_SLACK", False)

# Optional: also re-export the settings object for new code
__all__ = [
    "settings",
    "TRADING_MODE",
    "CRYPTO_TESTNET",
    "PYTHONUNBUFFERED",
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "MT5_LOGIN",
    "MT5_PASSWORD",
    "MT5_SERVER",
    "Q_ENABLE_QUANTUM",
    "Q_USE_RUNTIME",
    "IBM_QUANTUM_API_KEY",
    "IBM_MIN_QUBITS",
    "RISK_MAX_LOSS_PER_SYMBOL",
    "RISK_MAX_DAILY_LOSS",
    "RISK_MAX_ACCOUNT_DD",
    "RISK_LIMITS_PCT",
    "FEATURE_GA_EVOLUTION",
    "FEATURE_SENTIMENT_FUSION",
    "FEATURE_ARBITRAGE",
    "FEATURE_ONCHAIN_FUSION",
    "FEATURE_DEX_GUARDS",
    "FEATURE_MOON_RADAR",
    "FEATURE_IDEAS_SLACK",
]
