@echo off
REM Quote-safe: cd into this folder, then relative -File only (never full OneDrive -File).
setlocal
cd /d "%~dp0"
echo Running Refresh-HorseShowsPbix-Simple.ps1 ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Refresh-HorseShowsPbix-Simple.ps1" %*
set ERR=%ERRORLEVEL%
echo Exit code: %ERR%
echo Log: C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\refresh.log
exit /b %ERR%
