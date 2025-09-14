import traceback
files = ['auto_pilot.py','news_adapter.py','run_live.py','run_live_fx.py','mobile_app.py','tg_heartbeat.py','run_live_meme.py']
for f in files:
    try:
        print('---', f)
        with open(f,'r',encoding='utf-8') as fh:
            src = fh.read()
        compile(src,f,'exec')
        print('OK')
    except Exception:
        traceback.print_exc()
