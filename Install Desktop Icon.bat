@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_desktop_icon.ps1"

echo.
pause
