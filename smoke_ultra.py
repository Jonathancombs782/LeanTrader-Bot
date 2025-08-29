# smoke_ultra.py
# Quick dry-run smoke test: instantiate ExchangeRouter+UltraCore and run one god_mode_cycle

from dotenv import load_dotenv
from router import ExchangeRouter
from ultra_core import UltraCore

load_dotenv()

if __name__ == '__main__':
    ex = ExchangeRouter()
    print('router.info():', ex.info())
    try:
        ultra = UltraCore(ex, None)
        print('Running one dry-run god_mode_cycle()...')
        ultra.god_mode_cycle()
        print('god_mode_cycle completed (dry-run)')
    except Exception as e:
        print('UltraCore run failed:', e)
