# HANDOFF.md

이 문서는 **WSL(Hermes)에서 진행한 작업을 Windows Codex 앱으로 안전하게 이어받기 위한 인수인계 문서**입니다.

---

## 1) 프로젝트 개요

- 프로젝트명: `hotdeal-site`
- 원격 저장소: `https://github.com/namini1004/hotdeal.git`
- 기본 브랜치: `main`
- 배포: Vercel (`https://hotdeal-omega.vercel.app`)
- 데이터 소스: 뽐뿌 모바일 핫딜 `pop_bbs.php?id=ppomppu&bot_type=pop_bbs`

핵심 동작:
- 메인 페이지에서 `오늘의 핫딜 / 어제의 핫딜` 탭 표시
- 검색 아이콘으로 검색창 토글, 제목 기준 검색
- 상세 페이지에서 상단 `사러가기` 버튼으로 실제 구매 링크 이동
- 썸네일은 로컬 캐시(`assets/ppomppu_thumbs`) 우선 사용

---

## 2) 최근 반영된 작업(요약)

### UI
- 하단 카테고리형 네비 영역 제거
- 메인 우상단 검색 아이콘만 유지
- 상세페이지 하단 검은 CTA 제거, 상단 `사러가기`만 유지
- 배송 정보 문구 제거
- 상세 이미지/본문 경계선 1px 추가
- 메인 우상단 돋보기 아이콘 크기 확대(타이틀과 균형)

### 데이터 파싱/동기화
- 초기에는 1페이지 기준(최대 20개)이라 누락 발생
- 현재는 `page=1~5` 순회 수집 후 오늘/어제 필터링으로 확장
- 최근 결과 예시: `total=41 (today=16, yesterday=25)`

### 안정성
- 외부 썸네일 핫링크 깨짐 이슈를 로컬 캐시 방식으로 완화
- 1시간 주기 자동 갱신(변경 시 커밋/푸시) 구성

---

## 3) 핵심 파일 맵

- `index.html`
  - 메인 UI, 탭/검색/리스트 렌더링
  - 데이터 파일: `assets/ppomppu_hotdeals_2days.json`
- `detail.html`
  - 상세 UI, `사러가기` 버튼, 경계선 포함
- `scripts/update_ppomppu_feed.py`
  - 뽐뿌 수집/필터/구매링크 추출/썸네일 캐시/JSON 갱신
- `scripts/cron_refresh_hotdeals.sh`
  - 갱신 스크립트 실행 + 변경 시 커밋/푸시
- `scripts/refresh_hotdeals_windows.ps1`
  - Windows 작업 스케줄러용 자동 갱신/커밋/푸시 스크립트
- `assets/ppomppu_hotdeals_2days.json`
  - 실제 렌더링용 데이터
- `assets/ppomppu_thumbs/*`
  - 썸네일 로컬 캐시

주의:
- `codex_prompt.txt`는 현재 untracked 상태(의도적으로 커밋 제외 가능)

---

## 4) Windows Codex 앱에서 이어받는 베스트 절차

## A. 저장소 열기
1. Windows Codex 앱에서 폴더 열기:
   - `C:\Users\namin\hotdeal-site`
2. 터미널(Codex 내장 or PowerShell)에서 확인:
   - `git remote -v`
   - `git branch --show-current`

## B. 최신화 (상황별)
- **같은 컴퓨터(WSL + Windows가 같은 로컬 파일 공유)**:
  - 보통 pull 불필요 (같은 폴더 파일을 보고 있음)
  - 대신 아래 확인 권장:
    - `git status`
    - `git log --oneline -n 3`
- **다른 컴퓨터/새 환경**:
```bash
git pull origin main
```

## C. 의존 실행(필요 시)
파서는 Python 기반이므로 Python 3 설치 상태 확인:
```bash
python --version
# 또는
py --version
```

## D. 데이터 수동 갱신(즉시 반영 테스트)
```bash
python scripts/update_ppomppu_feed.py
```
예상 출력 형식:
- `UPDATED total=... today=... yesterday=...`
- 변경 없으면 `NO_CHANGES ...`

## E. 로컬 미리보기
```bash
python -m http.server 4173
```
브라우저에서:
- `http://localhost:4173/index.html`
- `http://localhost:4173/detail.html?id=...`

## F. 변경사항 반영(권장 워크플로)
```bash
git status
git add .
git commit
git push origin main
```

커밋 메시지 규칙(사용자 선호):
- 제목 첫 줄: `요구사항: ...`
- 본문: 요청사항 + 실제 작업 내용 요약

예시:
```text
요구사항: 페이지정리

- 요청사항
  - ...

- 작업 내용
  - ...
```

---

## 5) 자동 갱신(크론) 관련

Hermes 환경에서 등록된 작업:
- job name: `ppomppu-hotdeals-hourly-refresh`
- 주기: `every 60m`
- 실행 스크립트: `~/.hermes/scripts/cron_refresh_hotdeals.sh`

중요:
- 이 크론은 **Hermes/WSL 측 스케줄러**입니다.
- Windows Codex 앱만 켜둔다고 자동으로 돌지 않습니다.
- Windows에서도 동일 자동화를 원하면, 별도로 작업 스케줄러(Windows Task Scheduler) 구성 필요.

### Windows Task Scheduler 구성(추가)

Windows Codex 앱/Windows 단독 환경에서 자동 갱신을 돌리려면 아래처럼 등록:

1) 수동 1회 테스트 (PowerShell)
```powershell
cd C:\Users\namin\hotdeal-site
powershell -ExecutionPolicy Bypass -File .\scripts\refresh_hotdeals_windows.ps1
```

2) 작업 스케줄러 등록(매 60분)
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\Users\namin\hotdeal-site\scripts\refresh_hotdeals_windows.ps1"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 60)
Register-ScheduledTask -TaskName "HotdealHourlyRefresh" -Action $action -Trigger $trigger -Description "뽐뿌 핫딜 1시간 자동갱신/커밋/푸시"
```

3) 동작 확인
```powershell
Get-ScheduledTask -TaskName "HotdealHourlyRefresh"
Get-ScheduledTaskInfo -TaskName "HotdealHourlyRefresh"
```

4) 수동 실행/중지
```powershell
Start-ScheduledTask -TaskName "HotdealHourlyRefresh"
Stop-ScheduledTask -TaskName "HotdealHourlyRefresh"
```

5) 삭제
```powershell
Unregister-ScheduledTask -TaskName "HotdealHourlyRefresh" -Confirm:$false
```

---

## 6) 자주 발생 가능한 이슈와 대응

### 이슈 1) 실제 사이트보다 항목이 적게 보임
원인:
- 단일 페이지 수집 시 누락
대응:
- `scripts/update_ppomppu_feed.py`의 페이지 순회 범위 확인(`1~5`)
- 수동 실행 후 결과 개수 확인

### 이슈 2) 썸네일 깨짐
원인:
- 원본 외부 이미지 링크 불안정
대응:
- 로컬 캐시(`assets/ppomppu_thumbs`) 재생성 여부 확인
- 파서 재실행

### 이슈 3) 상세 `사러가기` 이동 이상
원인:
- 원문 링크/제휴 리다이렉트 파싱 실패
대응:
- `update_ppomppu_feed.py`의 buyLink 추출 로직 점검
- 문제 게시글 샘플 URL로 단건 재현 테스트

### 이슈 4) 푸시 인증 실패
대응:
- 로컬 자격증명 관리자 확인
- 필요 시 PAT 방식으로 push 구성 재확인

---

## 7) 빠른 점검 체크리스트

작업 시작 전:
- [ ] (같은 컴퓨터) `git status` / `git log --oneline -n 3` 확인
- [ ] (다른 컴퓨터) `git pull origin main`
- [ ] `git status` 깨끗한지 확인

변경 후:
- [ ] 오늘/어제 탭 정상 동작
- [ ] 검색창 토글/검색 정상
- [ ] 상세페이지 이미지/본문 경계선 보임
- [ ] `사러가기` 링크 이동 정상
- [ ] 썸네일 깨짐 없음
- [ ] `git commit` 메시지 형식 준수(`요구사항: ...`)
- [ ] `git push origin main`

---

## 8) 권장 다음 개선

- 페이지 순회 범위를 설정값으로 분리(하드코딩 제거)
- 파싱 실패/시간초과 시 fallback 로깅 강화
- 데이터 스키마 검증(필수 키 누락 시 경고)
- 간단한 스냅샷 테스트(오늘/어제 개수, 링크 유효성) 자동화

---

## 9) 인계 메모

현재는 **Git 중심 이어받기 전략**이 가장 안전합니다.
- 이미 main에 최신 변경 푸시됨
- Windows Codex 앱에서 pull 후 바로 작업 가능
- 작업 맥락은 본 문서 + Git log로 복원 가능

끝.