Param(
    [string]$TaskName = "HotdealHourlyRefresh",
    [string]$RepoPath = "C:\Users\namin\hotdeal-site",
    [int]$IntervalMinutes = 60,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "[$ts] $msg"
}

$runner = Join-Path $RepoPath "scripts\refresh_hotdeals_windows.ps1"
if (-not (Test-Path $runner)) {
    throw "실행 스크립트를 찾을 수 없습니다: $runner"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File \"$runner\""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# 기존 작업이 있으면 교체
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Log "기존 작업 삭제: $TaskName"
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "뽐뿌 핫딜 자동갱신/커밋/푸시 (매 $IntervalMinutes분)" | Out-Null
Log "작업 등록 완료: $TaskName"

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Log "작업 즉시 실행: $TaskName"
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Log "다음 실행 시각: $($info.NextRunTime)"
