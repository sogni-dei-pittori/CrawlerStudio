@echo off
title install crawler_daily task
echo === install scheduled task: 10:00 / 15:00 / 19:00 daily ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scheduler.ps1" -Action dryrun
echo.
set /p ans=Register this task now? [y/N] 
if /i not "%ans%"=="y" goto end
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scheduler.ps1" -Action install
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scheduler.ps1" -Action status
:end
echo.
pause
