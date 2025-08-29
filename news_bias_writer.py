# news_bias_writer.py
import json, pathlib, math, time
from news_service import harvest_rss, build_clean, filtered_news_for

OUT = pathlib.Path("runtime/news_risk.json"); OUT.parent.mkdir(exist_ok=True)

def compute_bias() -> float:
    # crude: BTC & USD headlines sentiment → bias in [-1,+1]
    harvest_rss(); build_clean()
    btc = filtered_news_for("BTC/USDT", is_fx=False, top_n=25)
    usd = filtered_news_for("EURUSD", is_fx=True, top_n=25)
    def agg(rows):
        if not rows: return 0.0
        s = sum(r.get("sent",0.0) for r in rows)/max(1,len(rows))
        return max(-1.0, min(1.0, s))  # clamp
    # risk-on if BTC positive and USD negative (loosely)
    bias = 0.6*agg(btc) - 0.3*agg(usd)
    return max(-1.0, min(1.0, bias))

if __name__=="__main__":
    b = compute_bias()
    OUT.write_text(json.dumps({"bias": b, "ts": int(time.time())}, indent=2), encoding="utf-8")
    print(f"[news-bias] wrote bias={b:+.2f} -> {OUT}")
