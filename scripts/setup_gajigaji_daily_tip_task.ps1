Param(
    [string]$RepoPath = "C:\p4\hotdeal",
    [string]$TaskName = "GajigajiDailyTipPost",
    [string]$RunAt = "12:00"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RunnerPath = Join-Path $RepoPath "scripts\run_gajigaji_daily_tip_windows.ps1"
if (-not (Test-Path -LiteralPath $RunnerPath)) {
    throw "Daily tip runner not found: $RunnerPath"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerPath`"" `
    -WorkingDirectory $RepoPath
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Post one sourced, duplicate-checked Gajigaji shopping tip each day." `
    -Force | Out-Null

$Task = Get-ScheduledTask -TaskName $TaskName
$Info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    TaskName = $Task.TaskName
    State = $Task.State
    NextRunTime = $Info.NextRunTime
    StartWhenAvailable = $Task.Settings.StartWhenAvailable
    DisallowStartIfOnBatteries = $Task.Settings.DisallowStartIfOnBatteries
    RestartCount = $Task.Settings.RestartCount
    Action = $Task.Actions.Execute + " " + $Task.Actions.Arguments
}
