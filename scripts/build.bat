@echo off
chcp 65001 >nul

cd /d "%~dp0\.."

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

echo [1/3] Deleting previous build folders...
if exist "build" rd /s /q build
if exist "dist" rd /s /q dist
if exist "Jarvis.spec" del /q "Jarvis.spec"

echo [2/3] Installing dependencies...
"%PYTHON_EXE%" -m pip install -r requirements.txt

echo [3/3] Building the executable...
"%PYTHON_EXE%" -m PyInstaller app\main.py ^
  --onefile ^
  --noconsole ^
  --name Jarvis ^
  --collect-all encodings ^
  --collect-all PySide6 ^
  --collect-all speech_recognition ^
  --collect-all gtts ^
  --collect-all playsound ^
  --collect-all requests ^
  --hidden-import core.agent ^
  --hidden-import app.gui

if exist "dist\Jarvis.exe" (
    echo SUCCESS: dist\Jarvis.exe was created successfully!
) else (
    echo ERROR: Build failed.
)

pause
