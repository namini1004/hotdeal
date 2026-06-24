Param(
    [string]$RepoPath = "C:\p4\hotdeal",
    [string]$PythonPath = "C:\Users\namin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    [string]$SupabaseUrlFile = "C:\p4\hotdeal\supabase_url.txt",
    [string]$SupabaseServiceRoleKeyFile = "C:\p4\hotdeal\supabase_service_role_key.txt",
    [int]$TimeoutSeconds = 900,
    [int]$PageDelaySeconds = 8
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$LogDir = Join-Path $RepoPath ".artifacts\logs"
$StateDir = Join-Path $RepoPath ".artifacts"
$TaskLog = Join-Path $LogDir "hotdeal_fmkorea_task.log"
$IngestLog = Join-Path $LogDir "hotdeal_fmkorea_ingest.log"
$BackoffState = Join-Path $StateDir "fmkorea_backoff_state.json"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-TaskLog($Message) {
    $Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $TaskLog -Value "[$Stamp] $Message" -Encoding UTF8
}

function Send-RecoveryNotification {
    Param([string]$Message)

    try {
        $UserName = [Environment]::UserName
        & msg.exe $UserName $Message 2>$null
        Write-TaskLog "notification sent user=$UserName"
    }
    catch {
        Write-TaskLog "notification failed $_"
    }
}

try {
    if (-not (Test-Path $RepoPath)) {
        throw "RepoPath not found: $RepoPath"
    }
    if (-not (Test-Path $PythonPath)) {
        throw "PythonPath not found: $PythonPath"
    }
    if (-not (Test-Path $SupabaseUrlFile)) {
        throw "SupabaseUrlFile not found: $SupabaseUrlFile"
    }
    if (-not (Test-Path $SupabaseServiceRoleKeyFile)) {
        throw "SupabaseServiceRoleKeyFile not found: $SupabaseServiceRoleKeyFile"
    }

    $env:HOTDEAL_REPO_DIR = $RepoPath
    $env:HOTDEAL_FMKOREA_INGEST_TIMEOUT = [string]$TimeoutSeconds
    $env:HOTDEAL_HERMES_FMKOREA_LOG = $IngestLog
    $env:HOTDEAL_SUPABASE_URL_FILE = $SupabaseUrlFile
    $env:HOTDEAL_SUPABASE_SERVICE_ROLE_KEY_FILE = $SupabaseServiceRoleKeyFile
    $env:HOTDEAL_FMKOREA_INCREMENTAL = "1"
    $env:HOTDEAL_FMKOREA_INCREMENTAL_MAX_PAGES = "1"
    $env:HOTDEAL_FMKOREA_PAGE_DELAY_SECONDS = [string]$PageDelaySeconds
    $env:HOTDEAL_FMKOREA_BACKOFF_STATE = $BackoffState
    $env:HOTDEAL_FMKOREA_BROWSER_FALLBACK = "1"
    $env:HOTDEAL_FMKOREA_BROWSER_FALLBACK_MAX_PAGES = "1"
    $env:HOTDEAL_FMKOREA_BROWSER_HEADLESS = "0"
    $env:HOTDEAL_FMKOREA_BROWSER_CHANNEL = "chrome"
    $env:HOTDEAL_FMKOREA_BROWSER_PROFILE_DIR = (Join-Path $StateDir "fmkorea-browser-profile")

    Set-Location $RepoPath
    Write-TaskLog "start repo=$RepoPath timeout=$TimeoutSeconds pageDelay=$PageDelaySeconds backoffState=$BackoffState"

    $ScriptPath = Join-Path $RepoPath "scripts\hotdeal_fmkorea_ingest.py"
    $Output = & $PythonPath $ScriptPath 2>&1
    $ExitCode = $LASTEXITCODE

    if ($Output) {
        $OutputText = ($Output | Out-String).TrimEnd()
        Add-Content -Path $TaskLog -Value $OutputText -Encoding UTF8
        if ($OutputText -match "FMKOREA_BACKOFF_RECOVERED") {
            Send-RecoveryNotification "FMKorea hotdeal parsing recovered and backoff was cleared."
        }
    }
    Write-TaskLog "done exit=$ExitCode"
    exit $ExitCode
}
catch {
    Write-TaskLog "error $_"
    throw
}
