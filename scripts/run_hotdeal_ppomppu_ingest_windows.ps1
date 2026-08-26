Param(
    [string]$RepoPath = "C:\p4\hotdeal",
    [string]$PythonPath = "C:\Users\namin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    [string]$SupabaseUrlFile = "C:\p4\hotdeal\supabase_url.txt",
    [string]$SupabaseServiceRoleKeyFile = "C:\p4\hotdeal\supabase_service_role_key.txt",
    [string]$PushIngestSecretFile = "C:\p4\hotdeal\push_ingest_secret.txt"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$LogDir = Join-Path $RepoPath ".artifacts\logs"
$TaskLog = Join-Path $LogDir "hotdeal_ppomppu_task.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-TaskLog($Message) {
    $Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $TaskLog -Value "[$Stamp] $Message" -Encoding UTF8
}

try {
    foreach ($RequiredPath in @($RepoPath, $PythonPath, $SupabaseUrlFile, $SupabaseServiceRoleKeyFile)) {
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
    $env:HOTDEAL_PPOMPPU_MAX_PAGES = "1"
    $env:HOTDEAL_PPOMPPU_MAX_NEW_DETAILS = "15"
    $env:HOTDEAL_PPOMPPU_INGEST_LOG = (Join-Path $LogDir "hotdeal_ppomppu_ingest.log")

    Set-Location $RepoPath
    Write-TaskLog "start repo=$RepoPath python=$PythonPath pushSecret=$((Test-Path -LiteralPath $PushIngestSecretFile))"
    $ScriptPath = Join-Path $RepoPath "scripts\local_ppomppu_ingest.py"
    $Output = & $PythonPath $ScriptPath 2>&1
    $ExitCode = $LASTEXITCODE
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
