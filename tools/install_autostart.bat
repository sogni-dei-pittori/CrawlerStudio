@echo off
title install autostart
echo === install autostart: CrawlerStudio.exe --minimized ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0autostart.ps1" -Action dryrun
echo.
set /p ans=Install autostart now? [y/N] 
if /i not "%ans%"=="y" goto end
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0autostart.ps1" -Action install
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0autostart.ps1" -Action status
:end
echo.
pause
