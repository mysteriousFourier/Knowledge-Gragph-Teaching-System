param(
    [switch]$NoPause
)

$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $Root ".env"
$PidFile = Join-Path $Root ".runtime\knowledge-gragph-teaching-system-processes.json"
$Stopped = New-Object System.Collections.Generic.List[int]

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) {
            return
        }

        $idx = $line.IndexOf("=")
        if ($idx -le 0) {
            return
        }

        $name = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Get-EnvInt {
    param(
        [string]$Name,
        [int]$Default
    )

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    $parsed = 0
    if ([int]::TryParse($value, [ref]$parsed)) {
        return $parsed
    }
    return $Default
}

Import-DotEnv -Path $EnvFile

$Ports = @(
    (Get-EnvInt -Name "FRONTEND_PORT" -Default 3000),
    (Get-EnvInt -Name "EDUCATION_API_PORT" -Default 8001),
    (Get-EnvInt -Name "MAINTENANCE_API_PORT" -Default 8002),
    (Get-EnvInt -Name "BACKEND_ADMIN_PORT" -Default 8080)
) | Select-Object -Unique

function Stop-ByPid {
    param(
        [int]$ProcessId,
        [string]$Name
    )

    if ($ProcessId -le 0 -or $Stopped.Contains($ProcessId)) {
        return
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host "$Name is not running, PID: $ProcessId"
        return
    }

    try {
        Write-Host "Stopping $Name, PID: $ProcessId"
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        Wait-Process -Id $ProcessId -Timeout 5 -ErrorAction SilentlyContinue
        $Stopped.Add($ProcessId) | Out-Null
    } catch {
        Write-Host "[WARNING] Failed to stop $Name, PID: $ProcessId"
        Write-Host "          $($_.Exception.Message)"
    }
}

function Get-PortOwners {
    param([int[]]$TargetPorts)

    $owners = @()
    try {
        $owners = Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { $TargetPorts -contains [int]$_.LocalPort } |
            Select-Object LocalPort, OwningProcess
    } catch {
        Write-Host "[WARNING] Get-NetTCPConnection failed, falling back to netstat."
        $owners = netstat -ano |
            Select-String "LISTENING" |
            ForEach-Object {
                $parts = ($_ -replace "^\s+", "") -split "\s+"
                if ($parts.Count -ge 5) {
                    $localAddress = $parts[1]
                    $pidValue = $parts[4]
                    $lastColon = $localAddress.LastIndexOf(":")
                    if ($lastColon -ge 0) {
                        $portText = $localAddress.Substring($lastColon + 1)
                        if ($portText -match "^\d+$" -and $pidValue -match "^\d+$") {
                            [PSCustomObject]@{
                                LocalPort = [int]$portText
                                OwningProcess = [int]$pidValue
                            }
                        }
                    }
                }
            } |
            Where-Object { $TargetPorts -contains [int]$_.LocalPort }
    }

    return $owners
}

Write-Host "Stopping Knowledge-Gragph-Teaching-System services..."

if (Test-Path -LiteralPath $PidFile) {
    try {
        $items = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
        foreach ($item in @($items)) {
            Stop-ByPid -ProcessId ([int]$item.pid) -Name ([string]$item.name)
        }
    } catch {
        Write-Host "[WARNING] Failed to read pid file: $PidFile"
        Write-Host "          $($_.Exception.Message)"
    }
} else {
    Write-Host "No service pid file found. Checking default ports instead."
}

foreach ($owner in @(Get-PortOwners -TargetPorts $Ports)) {
    $port = [int]$owner.LocalPort
    $pidValue = [int]$owner.OwningProcess
    Stop-ByPid -ProcessId $pidValue -Name "process on port $port"
}

try {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
} catch {
    Write-Host "[WARNING] Failed to remove pid file: $PidFile"
}

$remaining = @(Get-PortOwners -TargetPorts $Ports)
if ($remaining.Count -eq 0) {
    Write-Host "[OK] All default service ports are stopped: $($Ports -join ', ')"
} else {
    Write-Host "[WARNING] Some service ports are still in use:"
    foreach ($item in $remaining) {
        Write-Host "  Port $($item.LocalPort), PID: $($item.OwningProcess)"
    }
}

if (-not $NoPause -and [Environment]::UserInteractive) {
    Write-Host ""
    Read-Host "Press Enter to close"
}
