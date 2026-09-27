Param(
    [string]$RepoPath = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = "",
    [string]$SupabaseUrlFile = "",
    [string]$SupabaseServiceRoleKeyFile = "",
    [string]$PushIngestSecretFile = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $SupabaseUrlFile) { $SupabaseUrlFile = Join-Path $RepoPath "supabase_url.txt" }
if (-not $SupabaseServiceRoleKeyFile) { $SupabaseServiceRoleKeyFile = Join-Path $RepoPath "supabase_service_role_key.txt" }
if (-not $PushIngestSecretFile) { $PushIngestSecretFile = Join-Path $RepoPath "push_ingest_secret.txt" }
if (-not $PythonPath) {
    $PythonPath = Join-Path $RepoPath ".tools\hotdeal-python\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($PythonCommand) { $PythonPath = $PythonCommand.Source }
    }
}

$LogDir = Join-Path $RepoPath ".artifacts\logs"
$TaskLog = Join-Path $LogDir "hotdeal_quasar_task.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-TaskLog($Message) {
    $Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $TaskLog -Value "[$Stamp] $Message" -Encoding UTF8
}

try {
    foreach ($RequiredPath in @($RepoPath, $SupabaseUrlFile, $SupabaseServiceRoleKeyFile)) {
        if (-not (Test-Path -LiteralPath $RequiredPath)) {
            throw "Required path not found: $RequiredPath"
        }
    }

    $PythonResolver = Join-Path $RepoPath "scripts\resolve_hotdeal_python.ps1"
    . $PythonResolver
    $PythonPath = Resolve-HotdealPython -RepoPath $RepoPath -BootstrapPythonPath $PythonPath

    $env:HOTDEAL_SUPABASE_URL_FILE = $SupabaseUrlFile
    $env:HOTDEAL_SUPABASE_SERVICE_ROLE_KEY_FILE = $SupabaseServiceRoleKeyFile
    $env:HOTDEAL_PUSH_INGEST_SECRET_FILE = $PushIngestSecretFile
    $env:HOTDEAL_QUASAR_MAX_PAGES = "1"
    $env:HOTDEAL_QUASAR_INGEST_LOG = (Join-Path $LogDir "hotdeal_quasar_ingest.log")

    Set-Location $RepoPath
    $env:PYTHONIOENCODING = "utf-8"
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    Write-TaskLog "start repo=$RepoPath python=$PythonPath pushSecret=$((Test-Path -LiteralPath $PushIngestSecretFile))"
    $ScriptPath = Join-Path $RepoPath "scripts\local_quasar_ingest.py"
    # Windows PowerShell must capture Python stderr without discarding the exit code.
    $ErrorActionPreference = "Continue"
    try {
        $Output = & $PythonPath $ScriptPath 2>&1
        $ExitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = "Stop" }
    if ($Output) {
        Add-Content -Path $TaskLog -Value (($Output | Out-String).TrimEnd()) -Encoding UTF8
    }
    Write-TaskLog "done exit=$ExitCode"
    exit $ExitCode
}
catch {
    Write-TaskLog "error $_"
    throw
}
