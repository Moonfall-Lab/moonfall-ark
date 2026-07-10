@echo off
setlocal
cd /d %~dp0

if "%RUNTIME_HOST%"=="" set RUNTIME_HOST=0.0.0.0
if "%RUNTIME_PORT%"=="" set RUNTIME_PORT=8000

if not exist ".venv\Scripts\python.exe" (
    echo [Moonfall] Creating Python virtual environment in backend\.venv ...
    py -3.12 -m venv .venv 2>nul
    if errorlevel 1 py -3.11 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
    if errorlevel 1 (
        echo [Moonfall] Failed to create .venv. Please install Python 3.11 or newer.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [Moonfall] Installing backend dependencies ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [Moonfall] Failed to install dependencies.
        pause
        exit /b 1
    )
)

echo [Moonfall] Starting Runtime on http://%RUNTIME_HOST%:%RUNTIME_PORT%
".venv\Scripts\python.exe" -m uvicorn app.main:app --host %RUNTIME_HOST% --port %RUNTIME_PORT% --reload
endlocal
