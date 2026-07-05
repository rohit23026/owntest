@echo off
REM Intent Automation - native Windows app
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found on PATH.
        echo Install Python from https://www.python.org/downloads/
        echo IMPORTANT: tick "Add python.exe to PATH" during install.
        pause
        exit /b 1
    )
    set PY=py
) else (
    set PY=python
)

echo Installing dependencies...
%PY% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed - see message above.
    pause
    exit /b 1
)

echo Starting Intent Automation...
%PY% app\desktop.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The app exited with an error - see message above.
)
pause
