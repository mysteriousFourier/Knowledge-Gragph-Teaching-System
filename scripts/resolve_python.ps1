$ErrorActionPreference = "SilentlyContinue"

$roots = Get-PSDrive -PSProvider FileSystem |
    ForEach-Object {
        Get-ChildItem -LiteralPath $_.Root -Directory
    } |
    Where-Object {
        $_.Name -match "^(mini|ana|mamba|micro|miniforge|conda)"
    }

$envs = foreach ($root in $roots) {
    $envRoot = Join-Path $root.FullName "envs"
    if (Test-Path -LiteralPath $envRoot) {
        Get-ChildItem -LiteralPath $envRoot -Directory |
            Where-Object {
                Test-Path -LiteralPath (Join-Path $_.FullName "python.exe")
            }
    }
}

$preferred = $envs |
    Where-Object {
        $_.Name -match "graphrag|unless|paper|memory"
    } |
    Select-Object -First 1

if (-not $preferred) {
    $preferred = $envs | Select-Object -First 1
}

if ($preferred) {
    Join-Path $preferred.FullName "python.exe"
}
