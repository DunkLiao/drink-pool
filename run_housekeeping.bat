@echo off
setlocal EnableExtensions
title Drink Order Pool - Upload Housekeeping

cd /d "%~dp0"

echo ========================================
echo   Drink Order Pool - Upload Housekeeping
echo ========================================
echo.
echo This tool cleans uploaded menu photos.
echo It first runs a dry-run preview. No files
echo will be deleted until you type yes.
echo.

echo [1/3] Checking cleanup script...
if not exist "cleanup_uploads.py" (
    echo ERROR: cleanup_uploads.py was not found.
    pause
    exit /b 1
)

echo [2/3] Running dry-run preview...
echo.
python cleanup_uploads.py --dry-run
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Dry-run failed. No files were deleted.
    pause
    exit /b 1
)

echo.
echo [3/3] Confirm cleanup
echo.
echo Type yes to delete the listed expired/orphan photos.
set /p confirm="Run cleanup now? (yes/no): "
if /i not "%confirm%"=="yes" (
    echo Cancelled. No files were deleted.
    pause
    exit /b 0
)

echo.
echo Running cleanup...
python cleanup_uploads.py --yes
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Cleanup finished with errors. Check the output above.
    pause
    exit /b 1
)

echo.
echo Upload housekeeping completed.
pause
