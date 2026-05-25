# KGTS staging graph trial startup script.
# Uses .runtime/staging/knowledge_graph.db without replacing the production DB.
$ErrorActionPreference = "Stop"

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PARENT = Split-Path -Parent $ROOT
Set-Location $ROOT

$STAGING_DB = Join-Path $ROOT ".runtime\staging\knowledge_graph.db"
$STAGING_VECTOR_DIR = Join-Path $ROOT ".runtime\staging\vector_index"
$STAGING_LOG_DIR = Join-Path $ROOT ".runtime\staging"
$STAGING_LOG = Join-Path $STAGING_LOG_DIR "start-staging.log"
$FRONTEND_INDEX = Join-Path $ROOT "frontend\dist\index.html"

function Wait-ForUser {
    param([string]$Message = "Press Enter to close this window")
    if ($env:KGTS_NO_PAUSE -eq "1") {
        return
    }
    try {
        [void](Read-Host $Message)
    } catch {
        # Some non-interactive shells cannot read input; the log still has details.
    }
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 1000
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-HttpEndpoint {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Find-FreePort {
    param(
        [int]$StartPort,
        [int]$MaxAttempts = 20
    )
    for ($offset = 0; $offset -lt $MaxAttempts; $offset++) {
        $candidate = $StartPort + $offset
        if (-not (Test-TcpPort -HostName "127.0.0.1" -Port $candidate)) {
            return $candidate
        }
    }
    throw "Could not find a free localhost port starting at $StartPort."
}

$exitCode = 0
$transcriptStarted = $false

try {
    New-Item -ItemType Directory -Force -Path $STAGING_LOG_DIR | Out-Null
    Start-Transcript -Path $STAGING_LOG -Append -Force | Out-Null
    $transcriptStarted = $true

    if (-not (Test-Path $STAGING_DB)) {
        Write-Host "[ERROR] Staging graph DB is missing: $STAGING_DB" -ForegroundColor Red
        Write-Host "Run the staging rebuild first, then start this script again."
        throw "Staging graph DB is missing."
    }

    if (-not (Test-Path $FRONTEND_INDEX)) {
        Write-Host "[ERROR] Frontend build is missing: $FRONTEND_INDEX" -ForegroundColor Red
        Write-Host "Run .\start.ps1 once to build the frontend, or run npm run build in frontend/."
        throw "Frontend build is missing."
    }

    if (-not (Test-Path (Join-Path $STAGING_VECTOR_DIR "metadata.json"))) {
        Write-Host "[WARN] Staging vector index metadata is missing. Tree browsing still works." -ForegroundColor Yellow
    }

    $portWasExplicit = -not [string]::IsNullOrWhiteSpace($env:APP_PORT)
    if (-not $portWasExplicit) {
        $env:APP_PORT = "8003"
    }

    $requestedPort = [int]$env:APP_PORT
    $prepareUrl = "http://127.0.0.1:$requestedPort/teacher/prepare"
    if (Test-TcpPort -HostName "127.0.0.1" -Port $requestedPort) {
        if (Test-HttpEndpoint -Url $prepareUrl) {
            Write-Host "=========================================="
            Write-Host "KGTS - Staging Graph Trial"
            Write-Host "=========================================="
            Write-Host "[INFO] A server is already responding on port $requestedPort." -ForegroundColor Yellow
            Write-Host "Try the staging prepare page here:"
            Write-Host "  $prepareUrl"
            Write-Host ""
            Write-Host "If this is not the staging server, close the other server or set APP_PORT to another port before starting."
            Write-Host "Log: $STAGING_LOG"
            Wait-ForUser
            return
        }

        if ($portWasExplicit) {
            Write-Host "[ERROR] Port $requestedPort is already in use, and APP_PORT was set explicitly." -ForegroundColor Red
            Write-Host "Close the process using that port or choose another APP_PORT."
            throw "Port $requestedPort is already in use."
        }

        $nextPort = Find-FreePort -StartPort ($requestedPort + 1)
        Write-Host "[WARN] Port $requestedPort is already in use. Using $nextPort instead." -ForegroundColor Yellow
        $env:APP_PORT = [string]$nextPort
    }

    $env:GRAPH_DB_PATH = $STAGING_DB
    $env:KGTS_VECTOR_INDEX_DIR = $STAGING_VECTOR_DIR
    $env:APP_RUNTIME_DIR = Join-Path $ROOT ".runtime"
    $env:APP_BOOTSTRAP_SEED_DATA = "0"
    $env:APP_RUN_STARTUP_MAINTENANCE = "0"
    $env:RENDER_AUTO_SYNC_STRUCTURED = "0"
    $env:KGTS_RETRIEVAL_MODE = "hybrid"
    $env:KGTS_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    $env:KGTS_EMBEDDING_LOCAL_FILES_ONLY = "1"
    $env:KGTS_PROJECT_LOCAL_ONLY = "1"
    $env:KGTS_ALLOW_EXTERNAL_PATHS = "0"
    $env:KGTS_EMBEDDING_CACHE_DIR = Join-Path $ROOT ".runtime\huggingface"
    $env:HF_HOME = Join-Path $ROOT ".runtime\huggingface"
    $env:HF_HUB_CACHE = Join-Path $ROOT ".runtime\huggingface"
    $env:SENTENCE_TRANSFORMERS_HOME = Join-Path $ROOT ".runtime\huggingface"
    $env:TRANSFORMERS_CACHE = Join-Path $ROOT ".runtime\huggingface"
    $env:PYTHONPATH = "$PARENT;$ROOT;$env:PYTHONPATH"

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
        throw "Python not found."
    }

    Write-Host "=========================================="
    Write-Host "KGTS - Staging Graph Trial"
    Write-Host "=========================================="
    Write-Host "Python: $PYTHON"
    Write-Host "Graph DB: $env:GRAPH_DB_PATH"
    Write-Host "Vector index: $env:KGTS_VECTOR_INDEX_DIR"
    Write-Host "Log: $STAGING_LOG"
    Write-Host "URL: http://127.0.0.1:$($env:APP_PORT)/"
    Write-Host "Prepare page: http://127.0.0.1:$($env:APP_PORT)/teacher/prepare"
    Write-Host "Press Ctrl+C to stop"
    Write-Host ""

    & $PYTHON -m uvicorn render_app:app --host 127.0.0.1 --port $env:APP_PORT
    if ($LASTEXITCODE -ne 0) {
        throw "Uvicorn exited with code $LASTEXITCODE."
    }
} catch {
    $exitCode = 1
    Write-Host ""
    Write-Host "[ERROR] Staging startup failed." -ForegroundColor Red
    Write-Host $_.Exception.Message
    Write-Host "Log: $STAGING_LOG"
} finally {
    if ($transcriptStarted) {
        try {
            Stop-Transcript | Out-Null
        } catch {
        }
    }
}

exit $exitCode
