@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-staging.ps1"
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Staging startup failed with exit code %EXIT_CODE%.
    echo See .runtime\staging\start-staging.log for details.
    echo.
    pause
)
exit /b %EXIT_CODE%
