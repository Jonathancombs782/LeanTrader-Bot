import os

import requests

# OANDA v20 REST market order (simple). Env required:
# - OANDA_API_TOKEN
# - OANDA_ACCOUNT_ID
# - OANDA_ENV = practice | live

HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


class OandaBroker:
    def __init__(self, api_token: str = None, account_id: str = None, env: str = None):
        self.token = api_token or os.getenv("OANDA_API_TOKEN", "")
        self.account = account_id or os.getenv("OANDA_ACCOUNT_ID", "")
        self.env = (env or os.getenv("OANDA_ENV", "practice")).lower()
        self.base = HOSTS.get(self.env, HOSTS["practice"])

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def market(self, symbol: str, side: str, qty: float) -> dict:
        # OANDA uses units (positive buy, negative sell), instruments like "EUR_USD" or "XAU_USD"
        instr = symbol.replace("/", "_")
        units = int(qty if side.lower() in ("buy", "long") else -qty)
        url = f"{self.base}/v3/accounts/{self.account}/orders"
        payload = {
            "order": {
                "instrument": instr,
                "units": str(units),
                "type": "MARKET",
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        r = requests.post(url, headers=self._headers(), json=payload, timeout=20)
        try:
            j = r.json()
        except Exception:
            j = {"status_code": r.status_code, "text": r.text}
        return {"ok": r.ok, "status_code": r.status_code, "data": j}
