import importlib
import traceback
import sys

mods = [
    'tg_utils',
    'signals_scanner',
    'signals_scanner_debug',
    'brain_loop',
    'router',
    'signals_publisher',
    'run_live',
]
ok = True
for m in mods:
    try:
        importlib.invalidate_caches()
        importlib.import_module(m)
        print(m + ' OK')
    except Exception:
        traceback.print_exc()
        ok = False
if not ok:
    sys.exit(2)
print('ALL_IMPORTS_OK')
