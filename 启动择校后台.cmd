@echo off
setlocal
set "SITE_ROOT=%~dp0"
rem 优先用 PATH 里的 pythonw；没有就退回本机已知位置（原路径 D:\workspace\... 已失效）
set "SITE_PYTHONW=pythonw.exe"
where pythonw.exe >nul 2>nul || set "SITE_PYTHONW=D:\python312\pythonw.exe"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ready=$false; try{$response=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:8767/api/exam-resources'; $ready=($response.StatusCode -eq 200)}catch{}; if(-not $ready){Start-Process -FilePath '%SITE_PYTHONW%' -ArgumentList @('serve.py','8767') -WorkingDirectory '%SITE_ROOT%' -WindowStyle Hidden; Start-Sleep -Milliseconds 900}"
start "" "http://127.0.0.1:8767/数据库/admin.html"

endlocal
