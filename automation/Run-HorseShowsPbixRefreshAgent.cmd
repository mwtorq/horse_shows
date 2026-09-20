@echo off
REM Quote-safe launcher. cd into this folder so nothing needs a spaced -File path.
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Run-HorseShowsPbixRefreshAgent.ps1" %*
exit /b %ERRORLEVEL%
