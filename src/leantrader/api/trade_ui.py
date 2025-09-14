import html
import os

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, JSONResponse

from ..execution.broker_emulator import BrokerEmulator

BROKER_MODE = os.getenv("BROKER_MODE", "emu").lower()

router = APIRouter()

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>LeanTrader — Confirm Trade</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; }
    .card { max-width: 560px; margin: auto; border: 1px solid #ddd; border-radius: 12px; padding: 20px; box-shadow: 0 4px 18px rgba(0,0,0,0.05); }
    h1 { font-size: 20px; margin: 0 0 16px; }
    label { display:block; margin-top: 12px; font-weight: 600; }
    input, select { width: 100%; padding: 10px; border-radius: 10px; border: 1px solid #ccc; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .actions { margin-top: 16px; display:flex; gap: 12px; }
    button { padding: 10px 16px; border: none; border-radius: 10px; cursor: pointer; }
    .buy { background: #14b8a6; color: white; }
    .sell { background: #ef4444; color: white; }
    .ghost { background: #f3f4f6; }
    .note { font-size: 12px; color: #6b7280; margin-top: 6px; }
  </style>
  </head>
<body>
  <div class="card">
    <h1>Confirm Trade</h1>
    <form method="post" action="/trade/confirm">
      <div class="row">
        <div>
          <label>Pair</label>
          <input name="pair" value="{pair}" required />
        </div>
        <div>
          <label>Side</label>
          <select name="side">
            <option value="buy" {buy_sel}>Buy</option>
            <option value="sell" {sell_sel}>Sell</option>
          </select>
        </div>
      </div>

      <div class="row">
        <div>
          <label>Price (ref)</label>
          <input name="price" value="{price}" />
        </div>
        <div>
          <label>Quantity</label>
          <input name="qty" value="1.0" />
        </div>
      </div>

      <div class="row">
        <div>
          <label>Stop Loss</label>
          <input name="sl" placeholder="optional" />
        </div>
        <div>
          <label>Take Profit</label>
          <input name="tp" placeholder="optional" />
        </div>
      </div>

      <div class="note">This is a demo UI. In production, add authentication and connect to your broker.</div>

      <div class="actions">
        <button class="ghost" type="button" onclick="window.location='/'">Cancel</button>
        <button class="sell" name="confirm" value="1" type="submit">Place Order</button>
      </div>
    </form>
  </div>
</body>
</html>
"""


@router.get("/trade", response_class=HTMLResponse)
async def trade(pair: str = "EURUSD", side: str = "buy", price: float = 0.0):
    page = HTML_PAGE.format(
        pair=html.escape(pair),
        price=html.escape(f"{price:.5f}" if price else ""),
        buy_sel="selected" if side.lower() == "buy" else "",
        sell_sel="selected" if side.lower() == "sell" else "",
    )
    return HTMLResponse(page)


@router.post("/trade/confirm")
async def confirm_trade(
    pair: str = Form(...),
    side: str = Form(...),
    price: float = Form(0.0),
    qty: float = Form(1.0),
    sl: str = Form(""),
    tp: str = Form(""),
):
    # Route to execution layer (emulator by default)
    user = "demo"
    payload = {
        "user": user,
        "pair": pair,
        "side": side,
        "price": float(price or 0.0),
        "qty": float(qty or 0.0),
        "sl": sl,
        "tp": tp,
    }

    exec_res = None
    if BROKER_MODE == "emu":
        exec_res = BrokerEmulator().market(pair, side, payload["qty"], payload["price"])

    # Minimal response; storage/broadcasting can be added later
    return JSONResponse({"ok": True, "submitted": payload, "exec": exec_res})
