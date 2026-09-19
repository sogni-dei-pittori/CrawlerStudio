@echo off
title remove crawler_daily task
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scheduler.ps1" -Action remove
echo.
pause
