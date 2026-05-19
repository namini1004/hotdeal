Param(
    [string]$RepoPath = "C:\Users\namin\hotdeal-site",
    [string]$PythonCmd = "python",
    [string]$Branch = "main",
    [string]$PatFile = "C:\codex\pat.txt"
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

    # 1) 데이터 갱신
    $updateOut = & $PythonCmd "scripts/update_ppomppu_feed.py" 2>&1
    $updateText = ($updateOut | Out-String).Trim()
    Write-Log "update: $updateText"

    if ($updateText -like "NO_CHANGE*") {
        Write-Log "변경 없음, 종료"
        exit 0
    }

    # 2) 변경 감지 (데이터 파일/썸네일)
    $targetA = "assets/ppomppu_hotdeals_2days.json"
    $targetB = "assets/ppomppu_thumbs"

    & git add -- $targetA $targetB
    $staged = (& git diff --cached --name-only -- $targetA $targetB | Out-String).Trim()

    if ([string]::IsNullOrWhiteSpace($staged)) {
        Write-Log "스테이징된 변경 없음, 종료"
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

    # 3) 푸시
    # 기본: 저장된 자격증명 사용
    $pushOk = $true
    try {
        & git push origin $Branch | Out-Null
    }
    catch {
        $pushOk = $false
        Write-Log "origin push 실패, PAT 파일 방식 재시도"
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

    Write-Log "완료: 변경 커밋/푸시"
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
