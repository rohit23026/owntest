@echo off
REM OwnTest Studio - browser mode
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (set PY=py) else (set PY=python)

%PY% -m pip install flask websockets
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed - see message above.
    pause
    exit /b 1
)

start "" http://127.0.0.1:8700
%PY% app\server.py
pause
