@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
cd /d "%ROOT%"

echo ==========================================
echo KGTS - Knowledge Graph Teaching System
echo ==========================================
echo.

set "APP_PORT=8000"
set "APP_BIND_HOST=127.0.0.1"
set "APP_SCHEME=http"
set "APP_HOST=127.0.0.1"
set "APP_RUNTIME_DIR=%CD%\.runtime"
set "KGTS_HTTPS_CERT_FILE=%CD%\.runtime\certs\localhost.pem"
set "KGTS_HTTPS_KEY_FILE=%CD%\.runtime\certs\localhost-key.pem"
set "GRAPH_DB_PATH=%CD%\.runtime\staging\knowledge_graph.db"
set "KNOWLEDGE_GRAPH_DB_PATH=%GRAPH_DB_PATH%"
set "APP_BOOTSTRAP_SEED_DATA=0"
set "APP_RUN_STARTUP_MAINTENANCE=0"
set "RENDER_AUTO_SYNC_STRUCTURED=0"
set "KGTS_RETRIEVAL_MODE=hybrid"
set "KGTS_VECTOR_INDEX_DIR=%CD%\.runtime\staging\vector_index"
set "KGTS_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
set "KGTS_EMBEDDING_LOCAL_FILES_ONLY=1"
set "KGTS_PROJECT_LOCAL_ONLY=1"
set "KGTS_ALLOW_EXTERNAL_PATHS=0"
set "KGTS_EMBEDDING_CACHE_DIR=.runtime\huggingface"
set "HF_HOME=%CD%\.runtime\huggingface"
set "HF_HUB_CACHE=%CD%\.runtime\huggingface"
set "SENTENCE_TRANSFORMERS_HOME=%CD%\.runtime\huggingface"
set "TRANSFORMERS_CACHE=%CD%\.runtime\huggingface"
set "PYTHONPATH=%CD%;%PYTHONPATH%"
set "VENV_DIR=%CD%\.venv"

if not exist ".runtime\logs" mkdir ".runtime\logs"

set "URL_SCHEME=http"
if exist "%KGTS_HTTPS_CERT_FILE%" if exist "%KGTS_HTTPS_KEY_FILE%" (
    set "APP_SCHEME=https"
    set "URL_SCHEME=https"
)

if not exist "%GRAPH_DB_PATH%" (
    echo [ERROR] Staging graph DB is missing:
    echo         %GRAPH_DB_PATH%
    echo Run the staging rebuild before using scripts\launchers\start.bat.
    pause
    exit /b 1
)

if not exist "%KGTS_VECTOR_INDEX_DIR%\metadata.json" (
    echo [WARN] Staging vector index metadata is missing:
    echo        %KGTS_VECTOR_INDEX_DIR%\metadata.json
    echo        Tree browsing can still work, but hybrid search may be degraded.
)

set "PYTHON="
if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON=%VENV_DIR%\Scripts\python.exe"
    set "VIRTUAL_ENV=%VENV_DIR%"
    set "PATH=%VENV_DIR%\Scripts;%PATH%"
    goto :found_python
)

for %%P in (python py python3) do (
    where %%P >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%X in ('where %%P 2^>nul') do (
            echo %%X | findstr /i "\\WindowsApps\\" >nul
            if errorlevel 1 (
                set "PYTHON=%%X"
                goto :found_python
            )
        )
    )
)

echo [ERROR] Python not found.
echo Please install Python and add it to PATH.
pause
exit /b 1

:found_python
echo Using Python: %PYTHON%
if defined VIRTUAL_ENV echo Using virtual environment: %VIRTUAL_ENV%
"%PYTHON%" --version
if errorlevel 1 (
    echo [ERROR] Python failed to run.
    pause
    exit /b 1
)

echo.
echo [1/4] Checking Python dependencies...
"%PYTHON%" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo Installing Python dependencies...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
)

"%PYTHON%" -c "import sentence_transformers, faiss" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Local KGTS_RETRIEVAL_MODE=hybrid requires optional vector dependencies.
    echo Install them with:
    echo     "%PYTHON%" -m pip install -r requirements\vector.txt
    echo.
    echo Azure or low-resource deployments should use requirements\vector-cpu.txt and unload-after-query settings.
    pause
    exit /b 1
)

if not exist "third_party\Genie-TTS" (
    echo [WARN] Project-local TTS source missing: third_party\Genie-TTS
    echo        Install local TTS assets there or set KGTS_TTS_PROVIDER=genie_server.
)
if not exist "models\tts\GenieData" (
    echo [WARN] Project-local TTS resources missing: models\tts\GenieData
)
if not exist "models\tts\shu" (
    echo [WARN] Project-local shu TTS model missing: models\tts\shu
)

echo.
echo [2/4] Checking frontend build...
set "NEED_FRONTEND_BUILD=0"
if not exist "frontend\dist\index.html" set "NEED_FRONTEND_BUILD=1"
if "%NEED_FRONTEND_BUILD%"=="0" (
    "%PYTHON%" -c "from pathlib import Path; import sys; dist=Path('frontend/dist/index.html'); roots=[Path('frontend/src'), Path('frontend/public')]; mtimes=[]; [mtimes.extend(p.stat().st_mtime for p in r.rglob('*') if p.is_file()) for r in roots if r.exists()]; mtimes += [Path('frontend/package.json').stat().st_mtime, Path('frontend/index.html').stat().st_mtime, Path('frontend/vite.config.ts').stat().st_mtime]; sys.exit(0 if dist.stat().st_mtime >= max(mtimes) else 1)"
    if errorlevel 1 set "NEED_FRONTEND_BUILD=1"
)
if "%NEED_FRONTEND_BUILD%"=="1" (
    echo Frontend build missing or outdated. Building now...
    where npm >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] npm not found. Please install Node.js, then run start.bat again.
        pause
        exit /b 1
    )
    pushd frontend
    if not exist "node_modules" (
        call npm install
        if errorlevel 1 (
            popd
            echo [ERROR] npm install failed.
            pause
            exit /b 1
        )
    )
    call npm run build
    if errorlevel 1 (
        popd
        echo [ERROR] Frontend build failed.
        pause
        exit /b 1
    )
    popd
) else (
    echo Frontend build is up to date.
)

echo.
echo [3/4] Preparing browser...
start "" /min cmd /c "timeout /t 5 /nobreak >nul && start "" %URL_SCHEME%://127.0.0.1:%APP_PORT%/"

echo.
echo [4/4] Starting KGTS single server...
echo.
echo URL: %URL_SCHEME%://127.0.0.1:%APP_PORT%/
echo Graph DB: %GRAPH_DB_PATH%
echo Vector index: %KGTS_VECTOR_INDEX_DIR%
echo Logs: .runtime\logs
if "%URL_SCHEME%"=="https" (
    echo HTTPS certificate: %KGTS_HTTPS_CERT_FILE%
) else (
    echo HTTPS: disabled. Put localhost.pem and localhost-key.pem under .runtime\certs to enable it.
)
echo Press Ctrl+C to stop the server.
echo.

if "%URL_SCHEME%"=="https" (
    "%PYTHON%" -m uvicorn render_app:app --host "%APP_BIND_HOST%" --port "%APP_PORT%" --ssl-certfile "%KGTS_HTTPS_CERT_FILE%" --ssl-keyfile "%KGTS_HTTPS_KEY_FILE%" 2> ".runtime\logs\start.err.log"
) else (
    "%PYTHON%" -m uvicorn render_app:app --host "%APP_BIND_HOST%" --port "%APP_PORT%" 2> ".runtime\logs\start.err.log"
)

echo.
echo [ERROR] Server stopped or failed to start.
echo If this was not intentional, check .runtime\logs\start.err.log
pause
exit /b 1
