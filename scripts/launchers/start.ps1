# KGTS - Knowledge Graph Teaching System Startup Script
$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ROOT = Split-Path -Parent (Split-Path -Parent $SCRIPT_DIR)
Set-Location $ROOT
$env:KGTS_RETRIEVAL_MODE = "hybrid"
$env:KGTS_VECTOR_INDEX_DIR = ".runtime/vector_index"
$env:KGTS_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
$env:KGTS_EMBEDDING_LOCAL_FILES_ONLY = "1"
$env:KGTS_PROJECT_LOCAL_ONLY = "1"
$env:KGTS_ALLOW_EXTERNAL_PATHS = "0"
$env:KGTS_EMBEDDING_CACHE_DIR = ".runtime/huggingface"
$env:HF_HOME = Join-Path $ROOT ".runtime\huggingface"
$env:HF_HUB_CACHE = Join-Path $ROOT ".runtime\huggingface"
$env:SENTENCE_TRANSFORMERS_HOME = Join-Path $ROOT ".runtime\huggingface"
$env:TRANSFORMERS_CACHE = Join-Path $ROOT ".runtime\huggingface"
$env:PYTHONPATH = "$ROOT;$env:PYTHONPATH"

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
try {
    & $PYTHON -c "import sentence_transformers, faiss" 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    Write-Host "[ERROR] Local KGTS_RETRIEVAL_MODE=hybrid requires optional vector dependencies." -ForegroundColor Red
    Write-Host "Install them with:"
    Write-Host "    & `"$PYTHON`" -m pip install -r requirements/vector.txt"
    Write-Host "Low-resource Azure deployments keep hybrid enabled by using requirements/vector-cpu.txt and KGTS_VECTOR_UNLOAD_AFTER_QUERY=1."
    Read-Host "Press Enter to exit"
    exit 1
}

foreach ($asset in @("third_party\Genie-TTS", "models\tts\GenieData", "models\tts\shu")) {
    if (-not (Test-Path (Join-Path $ROOT $asset))) {
        Write-Host "[WARN] Project-local asset missing: $asset" -ForegroundColor Yellow
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
