import importlib, inspect
import sys
print('PYTHONPATH', __import__('os').environ.get('PYTHONPATH'))
try:
    m = importlib.import_module('trade_planner')
    print('module file=', getattr(m, '__file__', None))
    print('has attach_plan=', hasattr(m, 'attach_plan'))
    if hasattr(m, 'attach_plan'):
        src = inspect.getsource(m.attach_plan)
        print('attach_plan src first line:\n', src.splitlines()[0])
except Exception as e:
    import traceback
    print('ERROR', e)
    traceback.print_exc()
