@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=3000"

set "APP_RUNTIME_DIR=%ROOT_DIR%.runtime\render-local"
set "APP_DATA_DIR=%ROOT_DIR%.runtime\render-local-data"
set "AUTO_OPEN_BROWSER=0"
if "%DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS%"=="" set "DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS=0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv was not found in PATH.
    echo Install uv first, or run the manual command from docs\modules\render-deployment.md.
    pause
    exit /b 1
)

echo ================================================
echo Knowledge-Gragph-Teaching-System Render local test
echo ================================================
echo URL: http://127.0.0.1:%PORT%/
echo Health: http://127.0.0.1:%PORT%/api/health
echo Teacher: http://127.0.0.1:%PORT%/teacher.html
echo Student: http://127.0.0.1:%PORT%/student.html
echo Admin: http://127.0.0.1:%PORT%/admin
echo.
echo Press Ctrl+C to stop.
echo ================================================

start "" /min cmd /c "timeout /t 12 /nobreak >nul && start "" "http://127.0.0.1:%PORT%/""

cd /d "%ROOT_DIR%"
uv run --with fastapi --with "uvicorn[standard]" --with pydantic --with python-dotenv --with httpx uvicorn render_app:app --host 127.0.0.1 --port %PORT%

endlocal
