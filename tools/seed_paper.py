"""Seed the PaperBroker holdings so reconciliation and partial closes can succeed.

This is safe in paper mode. It sets holdings for a few bases and persists state.
"""
from __future__ import annotations

from traders_core.router import ExchangeRouter
import json, pathlib

def main():
    r = ExchangeRouter()
    ex = r.ex
    print('paper mode:', getattr(r, 'paper', False))
    # seed holdings for bases mentioned in closed_trades.json
    ex.holdings['ADA'] = ex.holdings.get('ADA', 0.0) + 5.006067265650304
    ex.holdings['LTC'] = ex.holdings.get('LTC', 0.0) + 4.996899981789208
    ex.holdings['BTC'] = ex.holdings.get('BTC', 0.0) + 4.9948708214782985e-05
    ex.holdings['XRP'] = ex.holdings.get('XRP', 0.0) + 13.003625096821178
    # top up cash
    ex.cash = max(getattr(ex, 'cash', 0.0), 1000.0)
    # persist if available
    if hasattr(ex, '_persist'):
        try:
            ex._persist()
            print('persisted via ex._persist()')
        except Exception as e:
            print('persist failed:', e)
    else:
        # fallback: write runtime/paper_state.json
        try:
            path = pathlib.Path('runtime') / 'paper_state.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                'cash': getattr(ex, 'cash', 0.0),
                'history': getattr(ex, 'history', []),
                'holdings': getattr(ex, 'holdings', {}),
                'fut_pos': getattr(ex, 'fut_pos', {}),
                '_px': getattr(ex, '_px', {}),
            }
            path.write_text(json.dumps(state, indent=2), encoding='utf-8')
            print('persisted fallback to runtime/paper_state.json')
        except Exception as e:
            print('fallback persist failed:', e)

if __name__ == '__main__':
    main()
