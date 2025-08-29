# lightweight runner to call signals_scanner.run_once under programmatic env
import os, sys
sys.path.insert(0, r'C:\Users\User\Downloads\LeanTrader_ForexPack')
# ensure dry-run paper exchange
os.environ['EXCHANGE_ID'] = 'paper'
os.environ['ENABLE_LIVE'] = 'false'
# import and run
from types import SimpleNamespace
import signals_scanner
args = SimpleNamespace(tf='1m', top=3, limit=50, publish=False)
res = signals_scanner.run_once(args)
print('SCAN RESULT COUNT:', len(res))
for s in res:
    print(s)
