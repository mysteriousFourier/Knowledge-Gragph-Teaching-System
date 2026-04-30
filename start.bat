@echo off
setlocal EnableExtensions

chcp 65001 >nul

set "ROOT_DIR=%~dp0"
set "ENV_FILE=%ROOT_DIR%.env"

cd /d "%ROOT_DIR%"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if exist "%ENV_FILE%" (
    echo [INFO] Loading environment variables from .env
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        if not "%%~A"=="" set "%%~A=%%~B"
    )
)

if not defined PYTHON_EXE if defined CONDA_ENV_PYTHON set "PYTHON_EXE=%CONDA_ENV_PYTHON%"
if not defined CONDA_ENV_NAME if defined ENV_NAME set "CONDA_ENV_NAME=%ENV_NAME%"
if not defined PYTHON_EXE if defined CONDA_ROOT if defined CONDA_ENV_NAME set "PYTHON_EXE=%CONDA_ROOT%\envs\%CONDA_ENV_NAME%\python.exe"

if not defined PYTHON_EXE if exist "%ROOT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%ROOT_DIR%venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
    )
)

if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\resolve_python.ps1" 2^>nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python is not configured.
    echo Set one of these in .env:
    echo   PYTHON_EXE=C:\path\to\python.exe
    echo   CONDA_ENV_PYTHON=C:\path\to\env\python.exe
    echo   CONDA_ROOT=C:\path\to\conda
    echo   CONDA_ENV_NAME=your-env-name
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found: %PYTHON_EXE%
    pause
    exit /b 1
)

if defined CONDA_ROOT if defined CONDA_ENV_NAME (
    if exist "%CONDA_ROOT%\Scripts\activate.bat" (
        call "%CONDA_ROOT%\Scripts\activate.bat" "%CONDA_ROOT%\envs\%CONDA_ENV_NAME%" >nul 2>nul
    )
)

echo ==============================================
echo Knowledge-Gragph-Teaching-System launcher
echo Root: %ROOT_DIR%
echo Python: %PYTHON_EXE%
if defined CONDA_ENV_NAME echo Conda env: %CONDA_ENV_NAME%
echo ==============================================

"%PYTHON_EXE%" "%ROOT_DIR%backend\start_all.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Launcher exited with code %EXIT_CODE%
)

echo.
pause
exit /b %EXIT_CODE%
