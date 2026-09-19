@echo off
title remove autostart
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0autostart.ps1" -Action remove
echo.
pause
