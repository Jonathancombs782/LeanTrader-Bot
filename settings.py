import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env file if present (local dev); in Codex, Secrets are already env vars
load_dotenv()


@dataclass
class Settings:
    # === Trading mode ===
    trading_mode: str = os.getenv("TRADING_MODE", "paper")
    crypto_testnet: bool = os.getenv("CRYPTO_TESTNET", "true").lower() == "true"

    # === Bybit API ===
    bybit_api_key: str = os.getenv("BYBIT_API_KEY", "")
    bybit_api_secret: str = os.getenv("BYBIT_API_SECRET", "")

    # === Binance API (optional) ===
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")

    # === Telegram Bot ===
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # === MetaTrader 5 (local only, not in Codex cloud) ===
    mt5_login: str = os.getenv("MT5_LOGIN", "")
    mt5_password: str = os.getenv("MT5_PASSWORD", "")
    mt5_server: str = os.getenv("MT5_SERVER", "")

    # === System ===
    python_unbuffered: int = int(os.getenv("PYTHONUNBUFFERED", "1"))


# Create global settings object
settings = Settings()

# Quick debug (optional; safe to remove later)
if __name__ == "__main__":
    print("Trading Mode:", settings.trading_mode)
    print("Crypto Testnet:", settings.crypto_testnet)
    print("Bybit Key Present:", bool(settings.bybit_api_key))
    print("Telegram Configured:", bool(settings.telegram_bot_token and settings.telegram_chat_id))
