param(
    [Parameter(Mandatory = $true)]
    [string]$PublishProfilePath,

    [string]$KnowledgeGraphPath = ".runtime\knowledge_graph.db",
    [string]$CoursesPath = ".runtime\courses.json",
    [string]$ChaptersPath = ".runtime\chapters.json",
    [string]$MetadataPath = ".runtime\vector_index\metadata.json",
    [string]$FaissPath = ".runtime\vector_index\vector_index.faiss",
    [string]$RemoteRuntimeRoot = "site/kgts-runtime"
)

$ErrorActionPreference = "Stop"

function Resolve-ExistingFile {
    param([string]$Path)
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Not a file: $Path"
    }
    return $resolved.ProviderPath
}

function Get-KuduProfile {
    param([xml]$PublishProfile)
    $profiles = @($PublishProfile.publishData.publishProfile)
    $profile = $profiles |
        Where-Object { $_.publishUrl -like "*.scm.azurewebsites.net*" -and $_.userName -and $_.userPWD } |
        Select-Object -First 1
    if (-not $profile) {
        throw "No Kudu/SCM profile found in publish profile XML. Download the App Service publish profile from Azure Portal."
    }
    return $profile
}

function Join-KuduVfsPath {
    param(
        [string]$Root,
        [string]$RelativePath
    )
    return ($Root.Trim("/") + "/" + $RelativePath.Replace("\", "/").TrimStart("/"))
}

function Invoke-KuduCommand {
    param(
        [string]$BaseUri,
        [hashtable]$Headers,
        [string]$Command
    )
    $body = @{ command = $Command; dir = "/home" } | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$BaseUri/api/command" -Method Post -Headers $Headers -Body $body -ContentType "application/json" | Out-Null
}

function Send-KuduFile {
    param(
        [string]$BaseUri,
        [hashtable]$Headers,
        [string]$LocalPath,
        [string]$RemoteVfsPath
    )
    $size = (Get-Item -LiteralPath $LocalPath).Length
    Write-Host "Uploading $LocalPath -> /home/$RemoteVfsPath ($size bytes)"
    Invoke-WebRequest -Uri "$BaseUri/api/vfs/$RemoteVfsPath" -Method Put -Headers $Headers -InFile $LocalPath -ContentType "application/octet-stream" | Out-Null
}

$publishProfileFile = Resolve-ExistingFile $PublishProfilePath
$knowledgeGraphFile = Resolve-ExistingFile $KnowledgeGraphPath
$coursesFile = Resolve-ExistingFile $CoursesPath
$chaptersFile = Resolve-ExistingFile $ChaptersPath
$metadataFile = Resolve-ExistingFile $MetadataPath
$faissFile = Resolve-ExistingFile $FaissPath

[xml]$publishProfile = Get-Content -Raw -Encoding UTF8 -LiteralPath $publishProfileFile
$kuduProfile = Get-KuduProfile -PublishProfile $publishProfile
$publishHost = ($kuduProfile.publishUrl -replace "^https?://", "").Split("/")[0]
$baseUri = "https://$publishHost"

$pair = "{0}:{1}" -f $kuduProfile.userName, $kuduProfile.userPWD
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
$headers = @{
    Authorization = "Basic $basic"
    "If-Match" = "*"
}

$remoteRoot = $RemoteRuntimeRoot.Trim("/")
$remoteVectorRoot = "$remoteRoot/vector_index"
Invoke-KuduCommand -BaseUri $baseUri -Headers $headers -Command "mkdir -p /home/$remoteRoot /home/$remoteVectorRoot"

Send-KuduFile -BaseUri $baseUri -Headers $headers -LocalPath $knowledgeGraphFile -RemoteVfsPath (Join-KuduVfsPath $remoteRoot "knowledge_graph.db")
Send-KuduFile -BaseUri $baseUri -Headers $headers -LocalPath $coursesFile -RemoteVfsPath (Join-KuduVfsPath $remoteRoot "courses.json")
Send-KuduFile -BaseUri $baseUri -Headers $headers -LocalPath $chaptersFile -RemoteVfsPath (Join-KuduVfsPath $remoteRoot "chapters.json")
Send-KuduFile -BaseUri $baseUri -Headers $headers -LocalPath $metadataFile -RemoteVfsPath (Join-KuduVfsPath $remoteVectorRoot "metadata.json")
Send-KuduFile -BaseUri $baseUri -Headers $headers -LocalPath $faissFile -RemoteVfsPath (Join-KuduVfsPath $remoteVectorRoot "vector_index.faiss")

Write-Host ""
Write-Host "Runtime data uploaded under /home/$remoteRoot."
Write-Host "Set App Service application settings:"
Write-Host "  APP_RUNTIME_DIR=/home/site/kgts-runtime"
Write-Host "  GRAPH_DB_PATH=/home/site/kgts-runtime/knowledge_graph.db"
Write-Host "  KGTS_VECTOR_INDEX_DIR=/home/site/kgts-runtime/vector_index"
