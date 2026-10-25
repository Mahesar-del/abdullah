@echo off
echo ============================================================
echo   TradeSense Pro - Service Status Checker
echo ============================================================
echo.

netstat -aon | findstr ":8000" | findstr "LISTENING" >nul
if %ERRORLEVEL% equ 0 (
    echo [RUNNING] TradeSense Pro server is ACTIVE and listening on port 8000!
    echo URL: http://127.0.0.1:8000/
) else (
    echo [STOPPED] TradeSense Pro server is NOT running.
    echo To start in background, run: scripts\run_background_service.vbs
)

echo.
pause
