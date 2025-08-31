import subprocess
import json
import os
import sys

def run(cmd):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, universal_newlines=True)
        return out.strip()
    except subprocess.CalledProcessError as e:
        return f"ERR: {e.returncode} {e.output[:1000]}"

print('BRANCH:' , run('git rev-parse --abbrev-ref HEAD'))
print('COMMIT:' , run('git log -n1 --pretty=format:"%H | %an | %ad | %s"'))

p = os.path.join('runtime','smoke_result.json')
if os.path.exists(p):
    try:
        with open(p,'r',encoding='utf-8') as fh:
            data = json.load(fh)
        print('SMOKE_COUNT:', len(data))
        for i,s in enumerate(data[:3]):
            print('SMOKE_SIG', i, {k:v for k,v in s.items() if k in ('symbol','side','confidence','qty')})
    except Exception as e:
        print('SMOKE_ERR', type(e).__name__, str(e)[:200])
else:
    print('SMOKE_MISSING')

print('\nRUNNING_PYTEST: (first 100 lines)')
try:
    # run a focused pytest run
    out = subprocess.check_output(f"{sys.executable} -m pytest -q -k 'think or safe' -s", shell=True, stderr=subprocess.STDOUT, universal_newlines=True, timeout=120)
    for i,line in enumerate(out.splitlines()[:100]):
        print(line)
    print('PYTEST_EXIT: 0')
except subprocess.CalledProcessError as e:
    print('PYTEST_EXIT:', e.returncode)
    print(e.output.splitlines()[:100])
except Exception as e:
    print('PYTEST_ERR', type(e).__name__, str(e)[:200])
