# status_ping.py
from pathlib import Path
from notifier import TelegramNotifier

def tail(path: str, n=20):
    p = Path(path)
    if not p.exists(): return "(no log yet)"
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:])

if __name__ == "__main__":
    noti = TelegramNotifier.from_env()
    noti.send(
        "*Status*\n"
        "Crypto log tail:\n```\n" + tail("logs/live.log", 10) + "\n```\n"
        "FX log tail:\n```\n" + tail("logs/live_fx.log", 10) + "\n```"
    )
    print("Status ping sent (if enabled).")
# status_ping.py
