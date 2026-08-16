Param(
    [string]$RepoPath = "C:\p4\hotdeal",
    [string]$PythonPath = "C:\Users\namin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    [string]$CodexPath = "C:\Users\namin\.codex\.sandbox-bin\codex.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$LogDir = Join-Path $RepoPath ".artifacts\logs"
$TaskLog = Join-Path $LogDir "gajigaji_daily_tip_task.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-TaskLog($Message) {
    $Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $TaskLog -Value "[$Stamp] $Message" -Encoding UTF8
}

try {
    if (-not (Test-Path -LiteralPath $RepoPath)) {
        throw "RepoPath not found: $RepoPath"
    }
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        throw "PythonPath not found: $PythonPath"
    }
    if (-not (Test-Path -LiteralPath $CodexPath)) {
        throw "CodexPath not found: $CodexPath"
    }

    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:GAJI_CODEX_PATH = $CodexPath
    $env:NO_COLOR = "1"

    Set-Location $RepoPath
    Write-TaskLog "start repo=$RepoPath generator=trusted-rss+codex"

    $ScriptPath = Join-Path $RepoPath "scripts\post_daily_gajigaji_tip.py"
    $Output = & $PythonPath $ScriptPath 2>&1
    $ExitCode = $LASTEXITCODE

    if ($Output) {
        Add-Content -Path $TaskLog -Value ($Output | Out-String).TrimEnd() -Encoding UTF8
    }
    Write-TaskLog "done exit=$ExitCode"
    exit $ExitCode
}
catch {
    Write-TaskLog "error $_"
    throw
}
