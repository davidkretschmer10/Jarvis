@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\repair_environment.ps1"

echo.
pause
