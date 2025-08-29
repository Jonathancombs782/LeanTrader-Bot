# memory.py
import os, json, time
from typing import Dict, Any, List

MEM_PATH = os.path.join("runtime", "brain.json")

class Memory:
    def __init__(self, path: str = MEM_PATH):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"positions": {}, "trades": [], "stats": {}})
        self.state = self._read()

    def _read(self): 
        with open(self.path, "r", encoding="utf-8") as f: 
            return json.load(f)

    def _write(self, obj): 
        with open(self.path, "w", encoding="utf-8") as f: 
            json.dump(obj, f, indent=2)

    # ---- positions ----
    def add_position(self, pos: Dict[str, Any]) -> str:
        pid = pos.get("id") or f"pos_{int(time.time()*1000)}"
        pos["id"], pos["ts_open"], pos["status"] = pid, int(time.time()), "open"
        self.state["positions"][pid] = pos
        self.state["trades"].append({"event":"open", **pos})
        self._write(self.state)
        return pid

    def close_position(self, pid: str, px_close: float, reason: str, pnl: float):
        p = self.state["positions"].get(pid); 
        if not p: return
        p["status"], p["ts_close"], p["px_close"], p["reason"], p["pnl"] = "closed", int(time.time()), px_close, reason, pnl
        self.state["trades"].append({"event":"close", "id": pid, "px_close": px_close, "reason": reason, "pnl": pnl})
        self._write(self.state)

    def open_positions(self) -> List[Dict[str,Any]]:
        return [p for p in self.state["positions"].values() if p.get("status")=="open"]
