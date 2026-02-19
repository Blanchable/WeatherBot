@echo off
setlocal enabledelayedexpansion
title Kalshi Market Making Bot
color 0B

echo.
echo  ======================================================
echo  ^|       Kalshi Market Making Bot - Launcher           ^|
echo  ======================================================
echo.

cd /d "%~dp0"

:: ── Find Python ─────────────────────────────────────────
echo [1/4] Checking Python...

set "PYTHON="
for %%P in (python py python3) do (
    where %%P >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2 delims= " %%V in ('%%P --version 2^>^&1') do (
            for /f "tokens=1,2 delims=." %%A in ("%%V") do (
                if %%A GEQ 3 if %%B GEQ 10 (
                    set "PYTHON=%%P"
                    echo   Found %%P ^(%%V^)
                )
            )
        )
    )
    if defined PYTHON goto :found_python
)

echo.
echo   ERROR: Python 3.10+ is required but not found.
echo.
echo   Download it from: https://www.python.org/downloads/
echo   IMPORTANT: Check "Add Python to PATH" during install.
echo.
echo   After installing Python, double-click this file again.
echo.
pause
exit /b 1

:found_python

:: ── Create venv if needed ───────────────────────────────
echo [2/4] Setting up environment...

if not exist ".venv\Scripts\activate.bat" (
    echo   Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo   ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   Created .venv\
) else (
    echo   Environment already exists
)

call .venv\Scripts\activate.bat

:: ── Install dependencies if needed ──────────────────────
echo [3/4] Checking dependencies...

python -c "import requests; import websocket; import numpy" >nul 2>&1
if errorlevel 1 (
    echo   Installing dependencies...
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo   ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo   Dependencies installed
) else (
    echo   Dependencies OK
)

:: ── Verify ──────────────────────────────────────────────
echo [4/4] Verifying...
python -c "import requests; import websocket; import numpy; import tkinter; print('  All good')"
if errorlevel 1 (
    echo.
    echo   WARNING: Tkinter may not be available.
    echo   Reinstall Python from python.org and check
    echo   "tcl/tk and IDLE" in the optional features.
    echo.
)

:: ── Launch ──────────────────────────────────────────────
echo.
echo  ======================================================
echo  ^|               Launching Bot...                      ^|
echo  ======================================================
echo.

python -m kalshi_bot.main %*

if errorlevel 1 (
    echo.
    echo   Bot exited with an error. See above for details.
    pause
)
