@echo off
title run crawler_daily now
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scheduler.ps1" -Action run
echo.
pause
