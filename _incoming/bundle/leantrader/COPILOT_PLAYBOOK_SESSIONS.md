# Copilot Playbook — Sessions, Learning & Mastery

1) **Bandit rewards**  
Hook real trade outcomes into `learners/bandit.py` updates: use R-multiple or net PnL per trade as reward. Add decay for old data.

2) **Session stats → routing**  
Use `sessions/manager.py` to bias the router toward policies that historically win in that session for the current pair.

3) **Replay-driven improvements**  
Implement a trainer that regularly scans `ReplayBuffer` and adjusts thresholds (e.g., ADX, ATR multiples) per session/regime.

4) **Curriculum unlocks**  
Compute rolling Sharpe-like metric per session; call `curriculum.gate(metric)` to enable advanced skills (orderflow/FVG, news scalp).

5) **Attribution audit**  
Fill `analytics/attribution.py` with real entry/exit SL/TP decomposition; log to journal; add tests.

6) **Safety net**  
If session hit-rate or equity dips below thresholds, auto-throttle risk or pause signals for that session until recovered.
