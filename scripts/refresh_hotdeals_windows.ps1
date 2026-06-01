Param(
    [string]$RepoPath = "C:\Users\namin\hotdeal-site",
    [string]$PythonCmd = "python",
    [string]$Branch = "main",
    [string]$PatFile = "C:\codex\pat.txt",
    [string]$PushIngestUrl = "https://gaji.run/api/push/ingest",
    [string]$PushIngestSecret = "rkwlrkwlskantrkwl",
    [string]$SupabaseUrlFile = "C:\codex\supabase_url.txt",
    [string]$SupabaseServiceRoleKeyFile = "C:\codex\supabase_service_role_key.txt",
    [string]$SupabaseJwtFile = "C:\codex\supabase_jwt.txt"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "[$ts] $msg"
}

try {
    if (-not (Test-Path $RepoPath)) {
        throw "RepoPath not found: $RepoPath"
    }

    Set-Location $RepoPath
    Write-Log "repo: $RepoPath"

    # 1) Feed update
    $feedScripts = @(
        "scripts/update_ppomppu_feed.py",
        "scripts/update_quasar_feed.py",
        "scripts/update_fmkorea_feed.py",
        "scripts/update_ruliweb_feed.py"
    )
    $failed = 0
    $changed = $false
    foreach ($script in $feedScripts) {
        try {
            $updateOut = & $PythonCmd $script 2>&1
            $updateText = ($updateOut | Out-String).Trim()
            Write-Log "update ${script}: $updateText"
            if ($updateText -notlike "NO_CHANGE*") {
                $changed = $true
            }
        }
        catch {
            $failed += 1
            Write-Log "update failed ${script}: $_"
        }
    }
    if ($failed -ge $feedScripts.Count) {
        throw "all feed updates failed"
    }

    # 1-1) Supabase sync + push ingest
    $serviceAccountPath = Join-Path $RepoPath "secrets\firebase-service-account.json"
    if (Test-Path $serviceAccountPath) {
        $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content $serviceAccountPath -Raw
    }
    $env:FIREBASE_PROJECT_ID = "gajigaji-bf2e8"
    $env:PUSH_INGEST_URL = $PushIngestUrl
    $env:PUSH_INGEST_SECRET = $PushIngestSecret

    if (Test-Path $SupabaseUrlFile) {
        $env:SUPABASE_URL = (Get-Content $SupabaseUrlFile -Raw).Trim()
    }
    if (Test-Path $SupabaseServiceRoleKeyFile) {
        $env:SUPABASE_SERVICE_ROLE_KEY = (Get-Content $SupabaseServiceRoleKeyFile -Raw).Trim()
    }
    elseif (Test-Path $SupabaseJwtFile) {
        $env:SUPABASE_SERVICE_ROLE_KEY = (Get-Content $SupabaseJwtFile -Raw).Trim()
        Write-Log "SUPABASE_SERVICE_ROLE_KEY loaded from SupabaseJwtFile"
    }

    if ([string]::IsNullOrWhiteSpace($env:SUPABASE_URL) -or [string]::IsNullOrWhiteSpace($env:SUPABASE_SERVICE_ROLE_KEY)) {
        Write-Log "sync skipped: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing"
    }
    else {
        if ([string]::IsNullOrWhiteSpace($env:PUSH_INGEST_SECRET)) {
            Write-Log "warning: PUSH_INGEST_SECRET missing (ingest may be skipped)"
        }
        $syncOut = & $PythonCmd "scripts/sync_hotdeals_to_supabase.py" 2>&1
        $syncText = ($syncOut | Out-String).Trim()
        Write-Log "sync: $syncText"
    }

    if (-not $changed) {
        Write-Log "no update changes"
        exit 0
    }

    # 2) Stage changed files
    $targets = @(
        "assets/ppomppu_hotdeals_2days.json",
        "assets/quasar_hotdeals_2days.json",
        "assets/fmkorea_hotdeals_2days.json",
        "assets/ruliweb_hotdeals_1day.json",
        "assets/ppomppu_thumbs",
        "assets/fmkorea_thumbs",
        "assets/ruliweb_thumbs"
    ) | Where-Object { Test-Path $_ }

    & git add -- $targets
    $staged = (& git diff --cached --name-only -- $targets | Out-String).Trim()

    if ([string]::IsNullOrWhiteSpace($staged)) {
        Write-Log "nothing staged"
        exit 0
    }

    $title = "요구사항: 윈도우 자동갱신 데이터 반영"
    $body = @"
- 요청사항
  - Windows 환경에서 정기 갱신 시 변경 데이터만 커밋/푸시

- 작업 내용
  - update_ppomppu_feed.py 실행 결과를 기준으로 변경 여부 판단
  - assets/ppomppu_hotdeals_2days.json 및 assets/ppomppu_thumbs 변경분만 스테이징
  - 변경 발생 시 자동 커밋 후 원격 main 브랜치 푸시

- 자동기록
  - 실행시각: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@

    & git commit -m $title -m $body | Out-Null

    # 3) Push
    $pushOk = $true
    try {
        & git push origin $Branch | Out-Null
    }
    catch {
        $pushOk = $false
        Write-Log "origin push failed, retry with PAT"
    }

    if (-not $pushOk) {
        if (-not (Test-Path $PatFile)) {
            throw "PAT file not found: $PatFile"
        }
        $token = (Get-Content $PatFile -Raw).Trim()
        if ([string]::IsNullOrWhiteSpace($token)) {
            throw "PAT file is empty: $PatFile"
        }
        $url = "https://x-access-token:$token@github.com/namini1004/hotdeal.git"
        & git push $url $Branch | Out-Null
    }

    Write-Log "done: committed and pushed"
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
