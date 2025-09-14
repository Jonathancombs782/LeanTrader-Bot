import threading, time
from traders_core.analytics.pnl import tail_fills_and_update_pnl

_stop = threading.Event()
_thr = None

def start():
    global _thr
    if _thr and _thr.is_alive(): return
    _thr = threading.Thread(target=tail_fills_and_update_pnl, args=(_stop,), kwargs={"interval_sec":1.0}, daemon=True)
    _thr.start()
    print("[pnl_daemon] started")

def stop():
    _stop.set()
    time.sleep(0.2)

