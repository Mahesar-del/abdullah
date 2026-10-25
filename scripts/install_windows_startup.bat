@echo off
setlocal

echo ============================================================
echo   TradeSense Pro - Windows Auto-Start Installer
echo ============================================================
echo.

set SCRIPT_DIR=%~dp0
set VBS_TARGET=%SCRIPT_DIR%run_background_service.vbs
set STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_FOLDER%\TradeSense_Pro_Background.vbs

echo Registering TradeSense Pro into Windows Startup folder:
echo Target: %VBS_TARGET%
echo Startup Location: %STARTUP_FOLDER%
echo.

copy /Y "%VBS_TARGET%" "%SHORTCUT%" >nul

if %ERRORLEVEL% equ 0 (
    echo [SUCCESS] TradeSense Pro will now automatically run in the background
    echo           whenever you turn on your laptop or log in to Windows!
    echo.
    echo To start it right now without restarting, double click:
    echo   scripts\run_background_service.vbs
) else (
    echo [ERROR] Failed to copy shortcut to startup folder.
)

echo.
pause
