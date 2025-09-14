import json, time
from services.web3_bias_daemon import bias_map, start as start_bias
from core.events.web3_consumer import subscribe

def _print(msg): print("[test]", msg)

def main():
    # Start consumer
    start_bias()
    # Simulate a message via stdin mode (no Redis): run this file and paste one JSON line
    _print("Paste a single JSON line and press Enter, e.g.:")
    _print('{"type":"web3.trending","symbol":"SOLUSDT","score":85}')
    subscribe(lambda m: None)  # blocks reading stdin

if __name__ == "__main__":
    main()

