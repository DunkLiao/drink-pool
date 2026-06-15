@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Drink Order Pool

cd /d "%~dp0"

echo ========================================
echo   Drink Order Pool - Starting Server
echo ========================================
echo.

echo [1/4] Preparing local UAT environment...
if not exist ".env" (
    echo Creating .env for local settings.
    type nul > ".env"
)

findstr /r /c:"^ADMIN_ENTRY_PASSWORD=." ".env" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Please set the local UAT admin entry password.
    set /p ADMIN_ENTRY_PASSWORD_INPUT=ADMIN_ENTRY_PASSWORD: 
    if "!ADMIN_ENTRY_PASSWORD_INPUT!"=="" (
        echo ERROR: ADMIN_ENTRY_PASSWORD cannot be empty.
        pause
        exit /b 1
    )
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='.env'; $lines=@(); if (Test-Path $p) { $lines=Get-Content -Encoding UTF8 $p | Where-Object { $_ -notmatch '^ADMIN_ENTRY_PASSWORD=' } }; $lines + ('ADMIN_ENTRY_PASSWORD=' + $env:ADMIN_ENTRY_PASSWORD_INPUT) | Set-Content -Encoding UTF8 $p"
    if errorlevel 1 (
        echo ERROR: Failed to update .env.
        pause
        exit /b 1
    )
    echo Saved ADMIN_ENTRY_PASSWORD to .env
) else (
    echo .env already contains ADMIN_ENTRY_PASSWORD.
)
echo.

echo [2/4] Installing dependencies...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/4] Initializing database...
if not exist "db\drink_pool.db" (
    python setup_db.py
    if %errorlevel% neq 0 (
        echo ERROR: Failed to initialize database.
        pause
        exit /b 1
    )
) else (
    echo Database already exists, skipping.
)

echo [4/4] Starting Flask server...
echo.
echo Server is running at: http://localhost:5001
echo Admin entry password is loaded from .env
echo Press Ctrl+C to stop.
echo ========================================

python app.py

pause
