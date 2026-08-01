@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==========================
echo STARTING JARVIS
echo ==========================
echo.

set "PYTHON_EXE="

if exist "%ROOT%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
)

if defined PYTHON_EXE (
    "%PYTHON_EXE%" -c "import PySide6" >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Jarvis Python environment is missing PySide6 or is broken.
        echo Run "Repair Environment.bat" in this folder, then start Jarvis again.
        goto :fail
    )
    echo Starting Jarvis from virtual environment...
    "%PYTHON_EXE%" -m app.main
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Starting Jarvis with py launcher...
    py -m app.main
    goto :done
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Starting Jarvis with python...
    python -m app.main
    goto :done
)

echo ERROR: Python was not found and dist\Jarvis.exe does not exist.
echo Reinstall Python/virtual environment, or build dist\Jarvis.exe later for a final release.
echo You can run "Repair Environment.bat" to fix this automatically.
goto :fail

:fail
exit /b 1

:done
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Jarvis ended with an error: %ERRORLEVEL%
    pause
)
