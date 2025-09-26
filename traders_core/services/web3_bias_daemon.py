import threading
from traders_core.events.web3_consumer import subscribe
from traders_core.signals.bias_map import BiasMap

bias_map = BiasMap()
_thr = None

def _on_msg(msg: dict):
    if msg.get("type") != "web3.trending":
        return
    sym = (msg.get("symbol") or "").upper()
    score = int(msg.get("score", 0))
    if not sym:
        return
    bias_map.set(sym, min(1.0, score/100.0), ttl_ms=20*60*1000)

def start():
    global _thr
    if _thr and _thr.is_alive():
        return
    _thr = threading.Thread(target=subscribe, kwargs={"callback": _on_msg}, daemon=True)
    _thr.start()
