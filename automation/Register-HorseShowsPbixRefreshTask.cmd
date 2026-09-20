@echo off
REM Quote-safe launcher for OneDrive paths that contain spaces.
setlocal
set "SCRIPT=%~dp0Register-HorseShowsPbixRefreshTask.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
