Param(
    [string]$TaskName = "HotdealQuasarIngest30m",
    [string]$RepoPath = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = "",
    [string]$SupabaseUrlFile = "",
    [string]$SupabaseServiceRoleKeyFile = "",
    [string]$PushIngestSecretFile = "",
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$RepoPath = (Resolve-Path -LiteralPath $RepoPath).Path
$Runner = Join-Path $RepoPath "scripts\run_hotdeal_quasar_ingest_windows.ps1"
if (-not $SupabaseUrlFile) { $SupabaseUrlFile = Join-Path $RepoPath "supabase_url.txt" }
if (-not $SupabaseServiceRoleKeyFile) { $SupabaseServiceRoleKeyFile = Join-Path $RepoPath "supabase_service_role_key.txt" }
if (-not $PushIngestSecretFile) { $PushIngestSecretFile = Join-Path $RepoPath "push_ingest_secret.txt" }

foreach ($Path in @($Runner, $SupabaseUrlFile, $SupabaseServiceRoleKeyFile)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required path not found: $Path"
    }
}
. (Join-Path $RepoPath "scripts\resolve_hotdeal_python.ps1")
if (-not $PythonPath) {
    $PythonPath = Join-Path $RepoPath ".tools\hotdeal-python\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        $Command = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($Command) { $PythonPath = $Command.Source }
    }
}
$PythonPath = Resolve-HotdealPython -RepoPath $RepoPath -BootstrapPythonPath $PythonPath
$Argument = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -RepoPath "{1}" -PythonPath "{2}" -SupabaseUrlFile "{3}" -SupabaseServiceRoleKeyFile "{4}" -PushIngestSecretFile "{5}"' -f $Runner, $RepoPath, $PythonPath, $SupabaseUrlFile, $SupabaseServiceRoleKeyFile, $PushIngestSecretFile
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $Argument -WorkingDirectory $RepoPath
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing -and $Existing.State -eq "Running") {
    throw "Task is running; wait for it to finish before updating registration: $TaskName"
}

# Preserve an existing half-hour timetable so re-registration does not trigger a burst.
$Triggers = @()
if ($Existing) {
    $Triggers = @($Existing.Triggers | Where-Object { $_.Repetition.Interval -eq "PT30M" })
}
if ($Triggers.Count -ne 1) {
    $Now = Get-Date
    $Start = $Now.Date.AddHours($Now.Hour).AddMinutes(5)
    while ($Start -le $Now) { $Start = $Start.AddMinutes(30) }
    $Triggers = @(New-ScheduledTaskTrigger -Once -At $Start -RepetitionInterval (New-TimeSpan -Minutes 30))
}
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -Principal $Principal -Description "Quasar local hybrid ingest: one list page every 30 minutes, Supabase sync." -Force | Out-Null
if ($RunNow) { Start-ScheduledTask -TaskName $TaskName }
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object TaskName, LastRunTime, LastTaskResult, NextRunTime
