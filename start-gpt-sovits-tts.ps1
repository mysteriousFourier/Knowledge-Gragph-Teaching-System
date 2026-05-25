$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }
        $pair = $trimmed.Split("=", 2)
        if ($pair.Count -ne 2) {
            continue
        }
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), "Process")
    }
}

Import-DotEnv (Join-Path $ProjectRoot ".env")

$TtsRoot = $env:KGTS_TTS_GPT_SOVITS_ROOT
if (-not $TtsRoot) {
    $TtsRoot = ".runtime\tts\gpt-sovits"
}

$Python = Join-Path $TtsRoot ".conda-tts\python.exe"
$SovitsWeights = $env:KGTS_TTS_GPT_SOVITS_SOVITS_WEIGHTS
$GptWeights = $env:KGTS_TTS_GPT_SOVITS_GPT_WEIGHTS
$ReferenceAudio = $env:KGTS_TTS_REFERENCE_AUDIO
$ReferenceText = $env:KGTS_TTS_REFERENCE_TEXT
$ReferenceLanguage = $env:KGTS_TTS_REFERENCE_LANGUAGE
$Device = $env:KGTS_TTS_GPT_SOVITS_DEVICE

if (-not $SovitsWeights) {
    $SovitsWeights = "SoVITS_weights_v2\shu_e8_s368.pth"
}
if (-not $GptWeights) {
    $GptWeights = "GPT_weights_v2\shu-e15.ckpt"
}
if (-not $ReferenceAudio) {
    throw "KGTS_TTS_REFERENCE_AUDIO is required in .env"
}
if (-not $ReferenceText) {
    throw "KGTS_TTS_REFERENCE_TEXT is required in .env"
}
if (-not $ReferenceLanguage) {
    $ReferenceLanguage = "zh"
}
if (-not $Device) {
    $Device = "cuda"
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "GPT-SoVITS Python was not found: $Python"
}

$env:PATH = "$TtsRoot\.conda-tts\bin;$TtsRoot\.conda-tts\Library\bin;$TtsRoot\.conda-tts\Scripts;$TtsRoot\.conda-tts;$env:PATH"

Push-Location $TtsRoot
try {
    $args = @(
        "api.py",
        "-a", "127.0.0.1",
        "-p", "9880",
        "-s", $SovitsWeights,
        "-g", $GptWeights,
        "-dr", $ReferenceAudio,
        "-dt", $ReferenceText,
        "-dl", $ReferenceLanguage,
        "-d", $Device
    )
    if ($Device -eq "cpu") {
        $args += "-fp"
    }
    & $Python @args
}
finally {
    Pop-Location
}
