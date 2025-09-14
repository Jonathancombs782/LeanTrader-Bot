import py_compile
from pathlib import Path

errs = []
for p in Path('.').rglob('*.py'):
    # skip virtualenvs or common env dirs
    if any(part.startswith('.') or part in ('venv', '__pycache__', 'node_modules') for part in p.parts):
        continue
    try:
        py_compile.compile(str(p), doraise=True)
    except Exception as e:
        errs.append((str(p), str(e)))

if not errs:
    print('COMPILE_OK')
else:
    print('COMPILE_FAIL')
    for f, e in errs:
        print(f'{f}: {e}')
