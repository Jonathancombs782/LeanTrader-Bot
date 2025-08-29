# multi_runner.py
from __future__ import annotations
import os, sys, json, time, subprocess, shlex
from pathlib import Path
from typing import Dict, Any, List

import yaml  # pip install pyyaml
from geo import detect_country, preferred_exchanges

PY = sys.executable or "python"

def _read_json_list(path: str) -> List[str]:
    p = Path(path)
    if not p.exists(): 
        return []
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(j, dict) and "symbols" in j:
            return list(map(str, j["symbols"]))
        if isinstance(j, list):
            return list(map(str, j))
    except Exception:
        pass
    return []

def _pick_exchange(acc: Dict[str,Any], country: str) -> str:
    ex = str(acc.get("exchange","auto")).lower()
    if ex != "auto":
        return ex
    prefs = preferred_exchanges(country)
    # allow a per-account candidate list
    cands = [c.lower() for c in acc.get("candidates", [])] or prefs
    return cands[0]

def _to_env(d: Dict[str,Any]) -> Dict[str,str]:
    out = {}
    for k,v in d.items():
        if isinstance(v, (int,float)): v = str(v)
        elif v is None: continue
        out[str(k)] = str(v)
    return out

def _spawn(cmd: List[str], env: Dict[str,str]):
    e = os.environ.copy()
    e.update(env)
    return subprocess.Popen(cmd, env=e)

def run():
    """
    accounts.yml example below.
    Spawns multiple loops with per-account env + symbols.
    """
    country = detect_country()
    print(f"[multi] country={country}")

    acc_path = Path("accounts.yml")
    if not acc_path.exists():
        raise SystemExit("accounts.yml missing (see sample text in this file’s docstring).")

    cfg = yaml.safe_load(acc_path.read_text(encoding="utf-8"))
    procs = []

    for acc in cfg.get("accounts", []):
        kind = acc.get("kind","crypto")  # 'crypto' | 'meme' | 'fx'
        script = acc.get("script") or ("run_live_meme.py" if kind=="meme" else "run_live_fx.py" if kind=="fx" else "run_live.py")
        ex_id = _pick_exchange(acc, country)

        # symbols/pairs
        if kind == "fx":
            pairs = acc.get("pairs") or _read_json_list(acc.get("universe","")) or ["EURUSD","GBPUSD"]
            sym_arg = ["--pairs", ",".join(pairs)]
        else:
            symbols = acc.get("symbols") or _read_json_list(acc.get("universe","")) or ["BTC/USDT","DOGE/USDT"]
            sym_arg = ["--symbols", ",".join(symbols)]

        # shared args
        tf = acc.get("timeframe","1m")
        args = [PY, "-u", script] + (["--exchange", ex_id] if kind!="fx" else []) + sym_arg + ["--timeframe", tf]

        # optional cadence / balance ping
        if "balance_every" in acc:
            args += ["--balance_every", str(acc["balance_every"])]

        env = _to_env({
            "ENABLE_LIVE":          acc.get("enable_live","false"),
            "API_KEY":              acc.get("api_key"),
            "API_SECRET":           acc.get("api_secret"),
            "EXCHANGE_MODE":        acc.get("exchange_mode","spot"),
            "TELEGRAM_ENABLED":     acc.get("telegram_enabled","true"),
            "TELEGRAM_BOT_TOKEN":   acc.get("telegram_bot_token"),
            "TELEGRAM_CHAT_ID":     acc.get("telegram_chat_id"),
            "LOG_LEVEL":            acc.get("log_level","INFO"),
            "MT5_PATH":             acc.get("mt5_path"),
            "MT5_LOGIN":            acc.get("mt5_login"),
            "MT5_PASSWORD":         acc.get("mt5_password"),
            "HTTP_PROXY":           acc.get("proxy_url") or os.getenv("HTTP_PROXY"),
            "HTTPS_PROXY":          acc.get("proxy_url") or os.getenv("HTTPS_PROXY"),
            "PROXY_URL":            acc.get("proxy_url") or os.getenv("PROXY_URL"),
        })

        print(f"[multi] spawn {script} ({kind}) ex={ex_id} tf={tf} {sym_arg[-1]}")
        procs.append(_spawn(args, env))

    # supervise
    try:
        while True:
            time.sleep(5)
            dead = [p for p in procs if p.poll() is not None]
            if dead:
                print(f"[multi] {len(dead)} process(es) exited. Restart or exit manually.")
                break
    except KeyboardInterrupt:
        print("[multi] stopping...")
        for p in procs:
            try: p.terminate()
            except Exception: pass

if __name__ == "__main__":
    run()
