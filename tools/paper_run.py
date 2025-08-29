"""Simple paper-run harness that runs `run_live.py` in paper mode for a short smoke-run.

Usage:
    $env:ENABLE_LIVE='false'; $env:EXCHANGE_ID='paper'; python tools/paper_run.py --minutes 60
"""
import os, sys, time, argparse, subprocess, logging
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.getcwd())

parser = argparse.ArgumentParser()
parser.add_argument('--minutes', type=int, default=5, help='How many minutes to run')
args = parser.parse_args()

os.environ['ENABLE_LIVE'] = 'false'
os.environ['EXCHANGE_ID'] = 'paper'

print('Starting paper-run for', args.minutes, 'minutes')
end = time.time() + args.minutes * 60
# setup logging to rotate
log_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, 'paper_run.log')
logger = logging.getLogger('paper_run')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=3)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logger.addHandler(handler)
# heartbeat file path
hb_path = os.path.join(os.getcwd(), 'runtime', 'paper_run.hb')
os.makedirs(os.path.dirname(hb_path), exist_ok=True)
# run the main loop in a subprocess to keep this harness simple
p = subprocess.Popen([sys.executable, os.path.join(os.getcwd(), 'run_live.py')])
try:
    logger.info('paper_run started subprocess pid=%s', p.pid)
    while time.time() < end:
        # write heartbeat
        try:
            with open(hb_path, 'w', encoding='utf-8') as f:
                f.write(str(int(time.time())))
        except Exception:
            logger.exception('heartbeat write failed')
        time.sleep(5)
    logger.info('Time elapsed; terminating run_live')
    p.terminate()
    p.wait(timeout=10)
except KeyboardInterrupt:
    logger.info('Interrupted; terminating')
    p.terminate()
    p.wait()

logger.info('paper-run finished')
print('paper-run finished; logs at', log_path)
