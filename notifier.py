# notifier.py  (unchanged from my last message)
from __future__ import annotations
import os, json, time, textwrap, requests
from pathlib import Path
from typing import List, Dict, Any, Optional
DATA_DIR = Path("reports"); DATA_DIR.mkdir(parents=True, exist_ok=True)
CMD_INBOX = DATA_DIR / "telegram_cmds.jsonl"
OFFSET_FILE = DATA_DIR / "tg_offset.txt"
def _envb(name: str, default: str="") -> str:
    v = os.getenv(name, default)
    return v if v is not None else default
class TelegramNotifier:
    def __init__(self):
        self.enabled = (_envb("TELEGRAM_ENABLED","false").lower() == "true")
        self.token   = _envb("TELEGRAM_BOT_TOKEN","")
        self.chat_id = _envb("TELEGRAM_CHAT_ID","")
        self.base_send = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.base_updates = f"https://api.telegram.org/bot{self.token}/getUpdates"
        self.username = None
    def _send(self, text: str, preview: bool=False):
        if not (self.enabled and self.token and self.chat_id):
            return
        try:
            r = requests.post(self.base_send, data={
                "chat_id": self.chat_id,
                "text": textwrap.dedent(text),
                "parse_mode": "Markdown",
                "disable_web_page_preview": (not preview)
            }, timeout=10)
            # Optionally expose debug output when TELEGRAM_DEBUG=true
            if os.getenv("TELEGRAM_DEBUG","false").lower() == "true":
                try:
                    body = r.json()
                except Exception:
                    body = r.text
                print(f"[tg debug] status={r.status_code} ok={r.ok} body={body}")
            return r
        except Exception:
            if os.getenv("TELEGRAM_DEBUG","false").lower() == "true":
                import traceback
                traceback.print_exc()
            return None
    def hello(self, venue: str, symbols: List[str] | str, tf: str):
        if isinstance(symbols, list): symbols = ", ".join(symbols)
        self._send(f"✅ Hello! Your trading bot is alive.\n"
                   f"*Live {venue}* tf=`{tf}`\nSymbols: {symbols}")
    def signal(self, symbol: str, side: str, entry: float, qty: float, stop: float,
               reasons: Optional[List[str]] = None, quality: float | None = None,
               take_profit: float | None = None, chart_path: Optional[str] = None):
        lines = [f"🚀 *Signal* `{symbol}` — *{side.upper()}*",
                 f"Entry: `{entry:.6f}` | Size: `{qty}` | SL: `{stop:.6f}`"]
        if take_profit:
            lines.append(f"TP: `{take_profit:.6f}`")
        if quality is not None:
            qemoji = "🔥" if quality >= 0.85 else "✨" if quality >= 0.7 else "🟡"
            lines.append(f"Quality: {qemoji} `{quality:.2f}`")
        if reasons:
            lines.append("*Context*")
            for b in reasons[:3]:
                lines.append(f"• {b}")
        lines.append("\nTap: `/buy {s} <qty>` `/sell {s} <qty>` `/flat {s}` `/balance`".replace("{s}", symbol))
        self._send("\n".join(lines))

    def send_photo(self, photo_path: str, caption: Optional[str] = None):
        """Send a photo file to the configured chat via sendPhoto endpoint."""
        if not (self.enabled and self.token and self.chat_id):
            return
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        try:
            with open(photo_path, 'rb') as f:
                files = {'photo': f}
                data = {"chat_id": self.chat_id}
                if caption:
                    data["caption"] = caption
                    data["parse_mode"] = "Markdown"
                r = requests.post(url, data=data, files=files, timeout=15)
            if os.getenv("TELEGRAM_DEBUG","false").lower() == "true":
                try:
                    body = r.json()
                except Exception:
                    body = r.text
                print(f"[tg debug photo] status={r.status_code} ok={r.ok} body={body}")
            return r
        except Exception:
            if os.getenv("TELEGRAM_DEBUG","false").lower() == "true":
                import traceback; traceback.print_exc()
            return None
    def balance_snapshot(self, balances: List[str]):
        msg = "💼 *Portfolio*\n" + "\n".join(f"• {b}" for b in balances)
        self._send(msg)
    def daily_pnl(self, report_text: str):
        self._send("📊 " + report_text)
    def note(self, text: str):
        self._send("ℹ️ " + text)
    def _read_offset(self) -> int:
        try:
            return int(OFFSET_FILE.read_text().strip())
        except Exception:
            return 0
    def _write_offset(self, off: int):
        try:
            OFFSET_FILE.write_text(str(off))
        except Exception:
            pass
    def poll_commands(self, throttle_ms: int = 0):
        if not (self.enabled and self.token):
            time.sleep(max(0, throttle_ms)/1000); return
        params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
        off = self._read_offset()
        if off: params["offset"] = off + 1
        try:
            r = requests.get(self.base_updates, params=params, timeout=5)
            data = r.json()
        except Exception:
            time.sleep(max(0, throttle_ms)/1000); return
        results = data.get("result", [])
        if not results:
            time.sleep(max(0, throttle_ms)/1000); return
        with open(CMD_INBOX, "a", encoding="utf-8") as f:
            for upd in results:
                up_id = upd.get("update_id")
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip()
                if not text: continue
                parts = text.split()
                if parts and parts[0].startswith("/"):
                    cmd = parts[0]
                    if "@" in cmd:
                        cmd = cmd.split("@",1)[0]; parts[0] = cmd
                    text = " ".join(parts)
                    f.write(json.dumps({"ts": int(time.time()), "cmd": text}) + "\n")
                if up_id is not None:
                    off = up_id
        self._write_offset(off)
        time.sleep(max(0, throttle_ms)/1000)

def _write_command(cmd: str):
    CMD_INBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(CMD_INBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time()), "cmd": cmd}) + "\n")
