@echo off
setlocal ENABLEDELAYEDEXPANSION

echo ===========================================
echo   Kalshi Weather Bot Setup Wizard (Win)
echo ===========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  echo Install Python 3.11+ and rerun this script.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo [1/6] Creating virtual environment...
  python -m venv .venv
) else (
  echo [1/6] Virtual environment already exists.
)

echo [2/6] Activating virtual environment...
call .venv\Scripts\activate
if errorlevel 1 (
  echo [ERROR] Failed to activate virtual environment.
  pause
  exit /b 1
)

echo [3/6] Upgrading pip...
python -m pip install --upgrade pip

echo [4/6] Installing uv...
python -m pip install --upgrade uv

echo [5/6] Syncing project dependencies...
uv sync --extra dev
if errorlevel 1 (
  echo [WARN] uv sync failed; trying pip fallback.
  python -m pip install -e .[dev]
)

echo [6/6] Setting up environment file...
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example. Please edit API keys before live mode.
) else (
  echo Existing .env detected; leaving as-is.
)

echo.
echo Setup complete.
echo.
echo Launching GUI now in paper mode...
echo.
echo Reminder: edit .env before enabling live trading.
echo.
python -m bot.main --mode paper --gui
if errorlevel 1 (
  echo [WARN] GUI exited with an error code.
  echo You can retry with: python -m bot.main --mode paper --gui
  pause
)

