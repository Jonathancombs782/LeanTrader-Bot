import time, csv
from traders_core.execution.fills_adapter import record_fill
from traders_core.services.pnl_daemon import start as start_pnl

def main():
    start_pnl()
    # Simulate: buy 0.01 @ 100, buy 0.01 @ 120, sell 0.015 @ 130
    record_fill("TESTUSDT", "buy", 100.0, 0.01, fee=0.0001, fee_ccy="USDT", strategy="test", exchange="sim")
    time.sleep(0.5)
    record_fill("TESTUSDT", "buy", 120.0, 0.01, fee=0.0001, fee_ccy="USDT", strategy="test", exchange="sim")
    time.sleep(0.5)
    record_fill("TESTUSDT", "sell", 130.0, 0.015, fee=0.0002, fee_ccy="USDT", strategy="test", exchange="sim")
    time.sleep(1.5)

    # Print last pnl row
    with open("runtime/logs/pnl.csv","r",encoding="utf-8") as f:
        rows = list(csv.reader(f))
    print("Last PnL row:", rows[-1])

if __name__ == "__main__":
    main()

