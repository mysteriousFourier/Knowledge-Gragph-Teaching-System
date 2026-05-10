@echo off
chcp 65001 >nul
setlocal

set "RENDER_APP_HOST=0.0.0.0"
set "RENDER_APP_PORT=8000"
set "RENDER_AUTO_SYNC_STRUCTURED=0"
set "APP_BOOTSTRAP_SEED_DATA=0"
set "PYTHONIOENCODING=utf-8"

cd /d "%~dp0"
set "REPO_ROOT=%CD%\.."
set "VENV_DIR=%REPO_ROOT%\.venv"
set "PYTHON_CMD=python"

if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON_CMD=%VENV_DIR%\Scripts\python.exe"
    set "VIRTUAL_ENV=%VENV_DIR%"
    set "PATH=%VENV_DIR%\Scripts;%PATH%"
)

:: Ensure dist exists
if not exist "dist\index.html" (
    echo Building frontend...
    call npm run build
    if errorlevel 1 (
        echo Build failed!
        pause
        exit /b 1
    )
)

:: Start server
echo Starting server on http://%RENDER_APP_HOST%:%RENDER_APP_PORT%
pushd "%REPO_ROOT%"
echo Using Python: %PYTHON_CMD%
if defined VIRTUAL_ENV echo Using virtual environment: %VIRTUAL_ENV%
"%PYTHON_CMD%" -m uvicorn render_app:app --host %RENDER_APP_HOST% --port %RENDER_APP_PORT% --reload
popd

pause
