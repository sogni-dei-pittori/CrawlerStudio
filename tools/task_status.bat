@echo off
title crawler_daily status
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scheduler.ps1" -Action status
echo.
pause
