import threading
from core.events.web3_consumer import subscribe
from core.signals.bias_map import BiasMap

bias_map = BiasMap()

def _on_msg(msg: dict):
    if msg.get("type") != "web3.trending":
        return
    sym = (msg.get("symbol") or "").upper()
    score = int(msg.get("score", 0))
    if not sym:
        return
    bias_map.set(sym, min(1.0, score/100.0), ttl_ms=20*60*1000)

def start():
    t = threading.Thread(target=subscribe, kwargs={"callback": _on_msg}, daemon=True)
    t.start()

