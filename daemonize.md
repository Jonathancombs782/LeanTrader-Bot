
# Run as a Daemon (so it trades while you're offline)

## Option A: tmux (simple)
```bash
tmux new -s fxbot
python run_live_fx.py --adapter oanda --pairs "EUR/USD,GBP/USD" --timeframe 5m --risk_usd 5
# detach with: Ctrl+b, then d
# reattach: tmux attach -t fxbot
```

## Option B: systemd (Linux)
Create `/etc/systemd/system/fxbot.service`:
```
[Unit]
Description=LeanTrader Forex Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/your/LeanTrader
ExecStart=/path/to/venv/bin/python run_live_fx.py --adapter oanda --pairs "EUR/USD,GBP/USD" --timeframe 5m --risk_usd 5
Restart=always

[Install]
WantedBy=multi-user.target
```
Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fxbot
sudo systemctl start fxbot
sudo systemctl status fxbot
```

## Option C: Windows (NSSM)
- Install NSSM, then create a service that runs:
```
C:\path\to\python.exe C:\path\to\run_live_fx.py --adapter mt5 --pairs "EURUSD,GBPUSD" --timeframe 5m --risk_usd 5
```
