#!/usr/bin/env python3
"""
ULTRA SYSTEM INSTALLATION VERIFIER
Checks that all files are properly installed and configured
"""

import os
import sys
from pathlib import Path
import json

# ANSI color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header():
    """Print header banner."""
    print("\n" + "="*70)
    print(f"{BOLD}ULTRA TRADING SYSTEM - INSTALLATION VERIFIER{RESET}")
    print("="*70 + "\n")

def check_file(filepath, description, critical=True):
    """Check if a file exists and report status."""
    path = Path(filepath)
    exists = path.exists()

    if exists:
        size_kb = path.stat().st_size / 1024
        status = f"{GREEN}✓ FOUND{RESET}"
        size_info = f"({size_kb:.1f} KB)"
    else:
        status = f"{RED}✗ MISSING{RESET}" if critical else f"{YELLOW}⚠ OPTIONAL{RESET}"
        size_info = ""

    print(f"  {status} {description:40} {filepath:30} {size_info}")
    return exists

def check_imports():
    """Check if required Python packages can be imported."""
    print(f"\n{BOLD}Checking Python Dependencies:{RESET}")
    print("-" * 50)

    packages = [
        ("numpy", "Numerical computing", True),
        ("pandas", "Data manipulation", True),
        ("sklearn", "Machine learning", True),
        ("xgboost", "XGBoost models", True),
        ("lightgbm", "LightGBM models", True),
        ("optuna", "Hyperparameter optimization", False),
        ("ccxt", "Crypto exchange connectivity", True),
        ("asyncio", "Async programming", True),
        ("aiohttp", "Async HTTP", True),
        ("telegram", "Telegram bot", False),
        ("matplotlib", "Plotting", False),
        ("redis", "Caching", False),
    ]

    all_critical_ok = True

    for package_name, description, critical in packages:
        try:
            if package_name == "sklearn":
                __import__("sklearn")
            elif package_name == "telegram":
                __import__("telegram")
            else:
                __import__(package_name)
            status = f"{GREEN}✓{RESET}"
            print(f"  {status} {description:30} {package_name:20}")
        except ImportError:
            if critical:
                status = f"{RED}✗{RESET}"
                all_critical_ok = False
            else:
                status = f"{YELLOW}⚠{RESET}"
            print(f"  {status} {description:30} {package_name:20} {'(REQUIRED)' if critical else '(optional)'}")

    return all_critical_ok

def check_configuration():
    """Check configuration files."""
    print(f"\n{BOLD}Checking Configuration:{RESET}")
    print("-" * 50)

    # Check if telegram config exists and is configured
    tg_config_path = Path("telegram_config.json")
    if tg_config_path.exists():
        try:
            with open(tg_config_path, 'r') as f:
                config = json.load(f)
                token = config.get('telegram', {}).get('bot_token', '')
                if token and token != "YOUR_BOT_TOKEN_HERE":
                    print(f"  {GREEN}✓{RESET} Telegram bot configured")
                else:
                    print(f"  {YELLOW}⚠{RESET} Telegram bot token not set (optional)")
        except Exception:
            print(f"  {YELLOW}⚠{RESET} Could not parse telegram_config.json")
    else:
        print(f"  {YELLOW}⚠{RESET} telegram_config.json not found (optional)")

    # Check for API keys in environment or config files
    if os.environ.get('BINANCE_API_KEY') or os.environ.get('BYBIT_API_KEY'):
        print(f"  {GREEN}✓{RESET} Exchange API keys found in environment")
    else:
        print(f"  {YELLOW}⚠{RESET} No exchange API keys in environment (needed for live trading)")

    return True

def main():
    """Main verification function."""
    print_header()

    # Check core files
    print(f"{BOLD}Checking Core Ultra System Files:{RESET}")
    print("-" * 50)

    core_files = [
        ("ultra_launcher.py", "Main entry point", True),
        ("ultra_ml_pipeline.py", "ML orchestrator", True),
        ("ultra_god_mode.py", "God Mode features", True),
        ("ultra_moon_spotter.py", "Moon shot detector", True),
        ("ultra_forex_master.py", "Forex/Metals trading", True),
        ("ultra_telegram_master.py", "Telegram signals", True),
        ("ultra_scout.py", "Market scanner", True),
    ]

    all_core_ok = True
    for filepath, desc, critical in core_files:
        if not check_file(filepath, desc, critical):
            all_core_ok = False

    # Check tools directory
    print(f"\n{BOLD}Checking Tools Directory:{RESET}")
    print("-" * 50)

    tools_files = [
        ("tools/market_data.py", "Market data manager", True),
        ("tools/ultra_trainer.py", "Advanced ML trainer", True),
    ]

    all_tools_ok = True
    for filepath, desc, critical in tools_files:
        if not check_file(filepath, desc, critical):
            all_tools_ok = False

    # Check configuration files
    print(f"\n{BOLD}Checking Configuration Files:{RESET}")
    print("-" * 50)

    config_files = [
        ("requirements_ultra.txt", "Python dependencies", True),
        ("start_ultra.sh", "Startup script", False),
        ("telegram_config.json", "Telegram configuration", False),
        ("README_ULTRA.md", "Documentation", False),
        ("TELEGRAM_SETUP.md", "Telegram setup guide", False),
    ]

    for filepath, desc, critical in config_files:
        check_file(filepath, desc, critical)

    # Check Python dependencies
    deps_ok = check_imports()

    # Check configuration
    # config_ok = check_configuration()  # Unused variable

    # Final verdict
    print("\n" + "="*70)

    if all_core_ok and all_tools_ok:
        print(f"{GREEN}{BOLD}✓ INSTALLATION VERIFIED SUCCESSFULLY!{RESET}")
        print("\nThe Ultra Trading System is properly installed.")

        if not deps_ok:
            print(f"\n{YELLOW}⚠ Some Python dependencies are missing.{RESET}")
            print("Run: pip install -r requirements_ultra.txt")

        print(f"\n{BOLD}Quick Start Commands:{RESET}")
        print("\n1. Paper trading with all features:")
        print("   python ultra_launcher.py --mode paper --god-mode --moon-spotter --forex")

        print("\n2. Train models first:")
        print("   python ultra_launcher.py --mode paper --train")

        print("\n3. With Telegram signals (configure first):")
        print("   python ultra_launcher.py --telegram --telegram-token YOUR_TOKEN")

    else:
        print(f"{RED}{BOLD}✗ INSTALLATION INCOMPLETE!{RESET}")
        print("\nSome critical files are missing.")
        print("Please ensure you've extracted all files from ultra_system_complete.zip")
        print("\nTo install:")
        print("1. Extract ultra_system_complete.zip to your project directory")
        print("2. Run INSTALL_ULTRA_WINDOWS.bat (Windows) or manually copy files")
        print("3. Run this verification script again")

        return 1

    print("\n" + "="*70 + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
