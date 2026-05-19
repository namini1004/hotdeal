Param(
    [string]$TaskName = "HotdealHourlyRefresh"
)

$ErrorActionPreference = "Stop"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "삭제 완료: $TaskName"
} else {
    Write-Output "작업 없음: $TaskName"
}
