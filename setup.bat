@echo off
title Kalshi Weather Bot - Setup Wizard
echo.
echo  ============================================
echo   Kalshi Weather Bot - Setup Wizard
echo  ============================================
echo.

:: Try python first, fall back to python3, then py launcher
where python >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=python
    goto :found
)

where python3 >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=python3
    goto :found
)

where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=py -3
    goto :found
)

echo  [ERROR] Python not found on PATH.
echo.
echo  Please install Python 3.11+ from https://www.python.org/downloads/
echo  Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found
echo  Using: %PYTHON_CMD%

:: Verify version is 3.11+
%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python 3.11+ is required.
    %PYTHON_CMD% --version
    echo  Please upgrade from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% --version
echo.

:: Change to the directory where this batch file lives (project root)
cd /d "%~dp0"

:: Ensure pip is available
%PYTHON_CMD% -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  Installing pip...
    %PYTHON_CMD% -m ensurepip --upgrade
)

:: Launch the setup wizard — it will auto-install deps on first run
%PYTHON_CMD% "%~dp0src\ui\setup_wizard.py"

if %errorlevel% neq 0 (
    echo.
    echo  Setup wizard exited with an error.
    echo.
    pause
)
