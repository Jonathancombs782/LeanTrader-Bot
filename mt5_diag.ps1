# mt5_diag.ps1
$env:MODE = $env:MODE -as [string]
Write-Host "MODE =" $env:MODE
Write-Host "MTS_PATH_DEMO =" $env:MTS_PATH_DEMO
Write-Host "MT5_PATH_DEMO =" $env:MT5_PATH_DEMO
Write-Host "MTS_PATH_LIVE =" $env:MTS_PATH_LIVE
Write-Host "MT5_PATH_LIVE =" $env:MT5_PATH_LIVE
python - << 'PY'
from mt5_adapter import _resolve_mt5_profile
p,login,pw,server = _resolve_mt5_profile()
print("Resolved path:", p)
print("Login:", login, "Server:", server)
PY
