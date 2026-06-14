@echo off
title Restore Database

cd /d "%~dp0"

echo ========================================
echo   Restore Database to Blank State
echo ========================================
echo.
echo IMPORTANT: Stop the Flask server first (Ctrl+C).
echo This will replace the current database with
echo the blank backup. All data will be lost!
echo.
set /p confirm="Are you sure? (yes/no): "
if /i not "%confirm%"=="yes" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
echo Copying blank database...

copy /y "db\drink_pool_blank.db" "db\drink_pool.db.tmp" >nul 2>&1
move /y "db\drink_pool.db.tmp" "db\drink_pool.db" >nul 2>&1

if %errorlevel% equ 0 (
    echo Database restored successfully.
    echo Please restart the Flask server if it was running.
) else (
    echo.
    echo ERROR: Restore failed. The database file may be locked.
    echo Make sure the Flask server is stopped, then try again.
)

pause
