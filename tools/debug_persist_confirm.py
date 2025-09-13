from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import runtime.webhook_server as ws  # noqa: E402


def main():
    ws._persist_confirm_store("9999", "debug-sig-1")
    print("called _persist_confirm_store")


if __name__ == "__main__":
    main()
