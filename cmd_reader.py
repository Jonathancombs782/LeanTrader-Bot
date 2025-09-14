# cmd_reader.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

INBOX = Path("reports/telegram_cmds.jsonl")


def read_commands() -> List[str]:
    """
    Atomically read & clear the commands inbox.
    Returns normalized strings like:
      "/balance"
      "/buy BTC/USDT 25"
      "/sell EURUSD 0.02"
      "/flat DOGE/USD"
    """
    if not INBOX.exists():
        return []
    try:
        data = INBOX.read_text(encoding="utf-8")
    except Exception:
        return []

    try:
        INBOX.write_text("", encoding="utf-8")  # clear
    except Exception:
        pass

    out: List[str] = []
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            cmd = str(obj.get("cmd", "")).strip()
            if cmd:
                out.append(cmd)
        except Exception:
            # ignore bad lines
            continue
    return out


def drain_commands(max_lines: int = 50) -> List[Dict[str, Any]]:
    """Return most recent command objects (JSON) and truncate the inbox file.

    Returns a list of dicts parsed from the last `max_lines` JSONL entries.
    """
    if not INBOX.exists():
        return []
    try:
        lines: List[str] = INBOX.read_text(encoding="utf-8").splitlines()[-max_lines:]
        INBOX.write_text("", encoding="utf-8")
        return [json.loads(x) for x in lines if x.strip()]
    except Exception:
        return []


def parse_command(cmd: str) -> Tuple[str, List[str]]:
    """
    Splits '/buy BTC/USDT 25' -> ('/buy', ['BTC/USDT','25'])
    """
    parts = cmd.split()
    if not parts:
        return "", []
    return parts[0].lower(), parts[1:]


# cmd_reader.py — reads JSONL commands written by Telegram poller
def read_new(max_lines: int = 100) -> List[Dict[str, Any]]:
    if not INBOX.exists():
        return []
    lines = INBOX.read_text(encoding="utf-8").splitlines()[-max_lines:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
