@echo off
REM Quote-safe launcher for OneDrive paths that contain spaces.
REM cd into this folder first so -File is a relative path with no spaces.
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Register-HorseShowsPbixRefreshTask.ps1" %*
exit /b %ERRORLEVEL%
