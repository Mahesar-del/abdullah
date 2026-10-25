@echo off
echo Stopping TradeSense Pro background processes...

REM Find and kill process listening on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a on port 8000...
    taskkill /F /PID %%a >nul 2>&1
)

echo TradeSense Pro background service stopped cleanly.
pause
