param(
    [string]$SourceRoot = "D:\download\TTS\GPT-SoVITS-20240821v2",
    [string]$TargetRoot = ".runtime\tts\gpt-sovits"
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string]$PathValue)
    $executionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PathValue)
}

function Copy-RequiredItem {
    param(
        [string]$RelativePath,
        [bool]$Directory = $false
    )
    $source = Join-Path $SourceRootFull $RelativePath
    $target = Join-Path $TargetRootFull $RelativePath
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing required source: $source"
    }
    $targetParent = Split-Path -Parent $target
    if ($targetParent -and -not (Test-Path -LiteralPath $targetParent)) {
        New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
    }
    if ($Directory) {
        Copy-DirectoryFiltered -Source $source -Target $target
    } else {
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
}

function Test-ExcludedRuntimeItem {
    param([System.IO.FileSystemInfo]$Item)
    if ($Item.Name -eq "__pycache__") {
        return $true
    }
    if ($Item.Name -eq ".gitignore") {
        return $true
    }
    if ($Item.Name -eq "G2PWModel_1.1.zip") {
        return $true
    }
    if ($Item.Extension -in @(".pyc", ".pyo")) {
        return $true
    }
    return $false
}

function Copy-DirectoryFiltered {
    param(
        [string]$Source,
        [string]$Target
    )
    if (-not (Test-Path -LiteralPath $Target)) {
        New-Item -ItemType Directory -Force -Path $Target | Out-Null
    }
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        if (Test-ExcludedRuntimeItem -Item $_) {
            return
        }
        $childTarget = Join-Path $Target $_.Name
        if ($_.PSIsContainer) {
            Copy-DirectoryFiltered -Source $_.FullName -Target $childTarget
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $childTarget -Force
        }
    }
}

function Get-ManifestEntry {
    param([string]$RelativePath)
    $path = Join-Path $TargetRootFull $RelativePath
    $item = Get-Item -LiteralPath $path
    $entry = [ordered]@{
        path = $RelativePath.Replace("\", "/")
        type = $(if ($item.PSIsContainer) { "directory" } else { "file" })
        exists = $true
    }
    if (-not $item.PSIsContainer) {
        $entry.length = $item.Length
        $entry.sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    }
    return $entry
}

$SourceRootFull = Resolve-FullPath $SourceRoot
$TargetRootFull = Resolve-FullPath $TargetRoot

if (-not (Test-Path -LiteralPath $SourceRootFull)) {
    throw "Source GPT-SoVITS root does not exist: $SourceRootFull"
}
if (-not (Test-Path -LiteralPath $TargetRootFull)) {
    New-Item -ItemType Directory -Force -Path $TargetRootFull | Out-Null
}

$requiredDirectories = @(
    "GPT_SoVITS\AR",
    "GPT_SoVITS\feature_extractor",
    "GPT_SoVITS\module",
    "GPT_SoVITS\text",
    "GPT_SoVITS\TTS_infer_pack",
    "GPT_SoVITS\pretrained_models\chinese-hubert-base",
    "GPT_SoVITS\pretrained_models\chinese-roberta-wwm-ext-large",
    "GPT_SoVITS\pretrained_models\gsv-v2final-pretrained",
    "tools\i18n"
)

$requiredFiles = @(
    "GPT_SoVITS\configs\tts_infer.yaml",
    "GPT_SoVITS\utils.py",
    "tools\my_utils.py",
    "GPT_weights_v2\shu-e15.ckpt",
    "SoVITS_weights_v2\shu_e8_s368.pth"
)

foreach ($relative in $requiredDirectories) {
    Copy-RequiredItem -RelativePath $relative -Directory $true
}
foreach ($relative in $requiredFiles) {
    Copy-RequiredItem -RelativePath $relative -Directory $false
}

$referenceSourceDir = Join-Path $SourceRootFull "logs\shu\5-wav32k"
$referenceSource = Get-ChildItem -LiteralPath $referenceSourceDir -File |
    Where-Object { $_.Name -like "*_0000000000_0000142080.wav" } |
    Select-Object -First 1
if (-not $referenceSource) {
    throw "Missing required shu reference audio in $referenceSourceDir"
}
$referenceRelativePath = "logs\shu\5-wav32k\$($referenceSource.Name)"
$referenceTarget = Join-Path $TargetRootFull $referenceRelativePath
$referenceTargetParent = Split-Path -Parent $referenceTarget
if (-not (Test-Path -LiteralPath $referenceTargetParent)) {
    New-Item -ItemType Directory -Force -Path $referenceTargetParent | Out-Null
}
Copy-Item -LiteralPath $referenceSource.FullName -Destination $referenceTarget -Force

$referenceAliasRelativePath = "reference\shu.wav"
$referenceAliasTarget = Join-Path $TargetRootFull $referenceAliasRelativePath
$referenceAliasParent = Split-Path -Parent $referenceAliasTarget
if (-not (Test-Path -LiteralPath $referenceAliasParent)) {
    New-Item -ItemType Directory -Force -Path $referenceAliasParent | Out-Null
}
Copy-Item -LiteralPath $referenceSource.FullName -Destination $referenceAliasTarget -Force

$manifestItems = @()
foreach ($relative in $requiredDirectories + $requiredFiles + @($referenceRelativePath, $referenceAliasRelativePath)) {
    $manifestItems += Get-ManifestEntry -RelativePath $relative
}

$manifest = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    source_root = $SourceRootFull
    target_root = $TargetRootFull
    provider = "gpt_sovits_local"
    character = "shu"
    gpt_weights = "GPT_weights_v2/shu-e15.ckpt"
    sovits_weights = "SoVITS_weights_v2/shu_e8_s368.pth"
    reference_audio = $referenceAliasRelativePath.Replace("\", "/")
    original_reference_audio = $referenceRelativePath.Replace("\", "/")
    items = $manifestItems
}

$manifestPath = Join-Path $TargetRootFull "manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -Path $manifestPath

Write-Host "Migrated GPT-SoVITS shu runtime to $TargetRootFull"
Write-Host "Manifest: $manifestPath"
