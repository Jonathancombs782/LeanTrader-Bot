import os
import json
from typing import Dict, Any

def news_bias(symbol: str, market: str) -> Dict[str, Any]:
    """Read NEWS_RISK_PATH (JSON) and return a small bias in [-1,1] with reason.

    JSON format expected: { "symbols": {"BTC/USDT": {"bias": 0.2, "reason": "major news"}}, "default": {"bias":0}}
    """
    path = os.getenv('NEWS_RISK_PATH', 'runtime/news_risk.json')
    try:
        if not os.path.exists(path):
            return {"bias": 0.0, "reason": "no_news_file"}
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        sym = symbol or ''
        entry = (data.get('symbols') or {}).get(sym)
        if entry:
            b = float(entry.get('bias', 0.0))
            b = max(-1.0, min(1.0, b))
            return {"bias": b, "reason": entry.get('reason','news')}
        default = data.get('default') or {}
        b = float(default.get('bias', 0.0))
        return {"bias": max(-1.0, min(1.0, b)), "reason": default.get('reason','default')}
    except Exception as e:
        return {"bias":0.0, "reason": f"err:{e}"}
