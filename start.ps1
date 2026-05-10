# KGTS - Knowledge Graph Teaching System Startup Script
$ErrorActionPreference = "Stop"

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

Write-Host "=========================================="
Write-Host "KGTS - Knowledge Graph Teaching System"
Write-Host "=========================================="
Write-Host ""

# Find Python. Prefer the repository virtual environment so dependencies stay isolated.
$VENV_DIR = Join-Path $ROOT ".venv"
$VENV_PYTHON = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_SCRIPTS = Join-Path $VENV_DIR "Scripts"
$PYTHON = $null

if (Test-Path $VENV_PYTHON) {
    $PYTHON = $VENV_PYTHON
    $env:VIRTUAL_ENV = $VENV_DIR
    $env:PATH = "$VENV_SCRIPTS;$env:PATH"
} else {
    foreach ($cmd in @("python", "py", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found -and ($found.Source -notmatch "\\WindowsApps\\")) {
            $PYTHON = $found.Source
            break
        }
    }
}

if (-not $PYTHON) {
    Write-Host "[ERROR] Python not found. Please install Python or add it to PATH." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Using Python: $PYTHON"
if ($env:VIRTUAL_ENV) {
    Write-Host "Using virtual environment: $env:VIRTUAL_ENV"
}
& $PYTHON --version

# Check frontend build
$frontendDist = Join-Path $ROOT "frontend\dist\index.html"
$frontendSrc = Join-Path $ROOT "frontend\src"
$frontendPublic = Join-Path $ROOT "frontend\public"
$frontendPackage = Join-Path $ROOT "frontend\package.json"
$frontendIndex = Join-Path $ROOT "frontend\index.html"
$frontendViteConfig = Join-Path $ROOT "frontend\vite.config.ts"
$needFrontendBuild = -not (Test-Path $frontendDist)
if (-not $needFrontendBuild) {
    $sourceFiles = @()
    if (Test-Path $frontendSrc) { $sourceFiles += Get-ChildItem $frontendSrc -Recurse -File }
    if (Test-Path $frontendPublic) { $sourceFiles += Get-ChildItem $frontendPublic -Recurse -File }
    foreach ($extra in @($frontendPackage, $frontendIndex, $frontendViteConfig)) {
        if (Test-Path $extra) { $sourceFiles += Get-Item $extra }
    }
    $latestSource = @($sourceFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1)[0]
    $latestSourceTime = $latestSource.LastWriteTime
    $needFrontendBuild = (Get-Item $frontendDist).LastWriteTime -lt $latestSourceTime
}
if ($needFrontendBuild) {
    Write-Host "Frontend build missing or outdated. Building now..."
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] npm not found. Please install Node.js, then run start.ps1 again." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Push-Location "frontend"
    if (-not (Test-Path "node_modules")) {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Pop-Location
            Write-Host "[ERROR] npm install failed." -ForegroundColor Red
            Read-Host "Press Enter to exit"
            exit 1
        }
    }
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "[ERROR] Frontend build failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Pop-Location
} else {
    Write-Host "Frontend build is up to date."
}

# Check dependencies
Write-Host "[1/2] Checking dependencies..."
try {
    & $PYTHON -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    Write-Host "Installing dependencies..."
    & $PYTHON -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Start server
Write-Host "[2/2] Starting server..."
Write-Host ""
Write-Host "Open http://127.0.0.1:8000 after server starts"
Write-Host "Press Ctrl+C to stop"
Write-Host ""

& $PYTHON render_app.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Server failed to start" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
