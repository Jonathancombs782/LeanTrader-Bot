from mt5_adapter import mt5_init
mt5 = mt5_init()
ti = mt5.terminal_info()
ai = mt5.account_info()
print("terminal:", {k:getattr(ti,k) for k in ("trade_allowed","connected","community_account") if hasattr(ti,k)})
print("account :", {k:getattr(ai,k) for k in ("trade_allowed","trade_mode","login","server") if hasattr(ai,k)})
