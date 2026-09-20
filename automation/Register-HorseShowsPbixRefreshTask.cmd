@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Register-HorseShowsPbixRefreshTask.ps1" -InvokeNow %*
exit /b %ERRORLEVEL%
