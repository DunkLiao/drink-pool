@echo off
title Drink Order Pool

cd /d "%~dp0"

echo ========================================
echo   Drink Order Pool - Starting Server
echo ========================================
echo.

echo [1/3] Installing dependencies...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [2/3] Initializing database...
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

echo [3/3] Starting Flask server...
echo.
echo Server is running at: http://localhost:5001
echo Press Ctrl+C to stop.
echo ========================================

python app.py

pause
