import os
import time
import yaml
from decimal import Decimal
from lt_plugins.common.bus import Bus
from .sources import dexscreener, geckoterminal, etherscan_pulse

CONFIG_PATH = os.getenv("WEB3_SIGNALS_CONFIG", "lt_plugins/web3_signals/config.yaml")

def load_cfg(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def normalize(sig: dict) -> dict:
    return {
        "type": "web3.trending",
        "source": sig.get("source"),
        "chain": sig.get("chain"),
        "symbol": sig.get("symbol"),
        "pair": sig.get("pair"),
        "score": int(sig.get("score", 0)),
        "url": sig.get("url"),
        "meta": {k:v for k,v in sig.items() if k not in {"source","chain","symbol","pair","score","url"}},
        "ts": int(time.time()*1000),
    }

def run():
    cfg = load_cfg(CONFIG_PATH)
    loop_sec = int(cfg.get("loop_sec", 120))
    bus = Bus(channel=cfg.get("publish", {}).get("channel","signal.web3.trending"))

    while True:
        try:
            out = []
            dexcfg = cfg.get("dexscreener", {})
            out += dexscreener.fetch(
                chains=dexcfg.get("chains", []),
                min_liq=Decimal(str(dexcfg.get("min_liquidity_usd", 20000))),
                min_vol5m=Decimal(str(dexcfg.get("min_vol5m_usd", 5000))),
                min_chg5m=Decimal(str(dexcfg.get("min_change5m_pct", 10))),
            )

            gcfg = cfg.get("geckoterminal", {})
            out += geckoterminal.fetch(
                networks=gcfg.get("networks", []),
                min_score=int(gcfg.get("min_score", 50)),
            )

            ecfg = cfg.get("etherscan", {})
            out += etherscan_pulse.fetch(
                api_key=os.getenv("ETHERSCAN_API_KEY", ecfg.get("api_key","")).strip(),
                contracts=ecfg.get("watch_contracts", []),
                blocks_lookback=int(ecfg.get("blocks_lookback", 5000)),
            )

            uniq = {}
            for s in out:
                key = (s.get("source"), s.get("pair"))
                if key not in uniq or s.get("score",0) > uniq[key].get("score",0):
                    uniq[key] = s
            top = sorted(uniq.values(), key=lambda s: s.get("score",0), reverse=True)[:20]

            for s in top:
                bus.publish(normalize(s))

        except Exception as e:
            print("[web3_signals] loop error:", e)
        time.sleep(loop_sec)

if __name__ == "__main__":
    run()

