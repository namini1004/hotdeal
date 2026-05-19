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
  - Windows 작업 스케줄러용 자동 갱신/커밋/푸시 실행 스크립트
- `scripts/register_hotdeal_task_windows.ps1`
  - Windows 작업 스케줄러 원클릭 등록(교체 등록/즉시실행 옵션)
- `scripts/unregister_hotdeal_task_windows.ps1`
  - Windows 작업 스케줄러 작업 삭제 스크립트
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

Windows Codex 앱/Windows 단독 환경에서 자동 갱신을 돌리려면 아래 순서 권장:

1) 수동 1회 테스트 (실행 스크립트)
```powershell
cd C:\Users\namin\hotdeal-site
powershell -ExecutionPolicy Bypass -File .\scripts\refresh_hotdeals_windows.ps1
```

2) 원클릭 등록(매 60분, 기존 작업 있으면 교체)
```powershell
cd C:\Users\namin\hotdeal-site
powershell -ExecutionPolicy Bypass -File .\scripts\register_hotdeal_task_windows.ps1 -IntervalMinutes 60 -RunNow
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

5) 삭제(원클릭)
```powershell
cd C:\Users\namin\hotdeal-site
powershell -ExecutionPolicy Bypass -File .\scripts\unregister_hotdeal_task_windows.ps1
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
- 같은 컴퓨터면 pull 없이 바로 작업 가능(다른 컴퓨터는 pull 권장)
- 작업 맥락은 본 문서 + Git log로 복원 가능

끝.

---

## 10) 2026-05-20 모바일 이어작업 메모

내일 모바일에서 이어서 확인할 최신 상태입니다.

### 현재 최신 커밋

`hotdeal-site`:
- 최신 커밋: `9ab857d 요구사항: 스크롤 반응형 상단바와 글쓰기 버튼 적용`
- 원격 `main`에 푸시 완료
- 중간에 자동 갱신 커밋도 들어옴: `4c523f7 chore: hourly refresh ppomppu hotdeals feed`

`hotdeal-android`:
- 로컬 최신 커밋: `fc83640 요구사항: Android 공유 설명과 가격 메타 전달`
- Android 프로젝트는 현재 원격 저장소가 설정되어 있지 않아 로컬 커밋만 있음
- Debug APK 빌드 경로: `C:\users\namin\hotdeal-android\app\build\outputs\apk\debug\app-debug.apk`

주의:
- `hotdeal-android`에는 아직 커밋하지 않은 변경이 남아 있음
  - `app/src/main/java/com/hotdeal/app/MainActivity.java`: 상단 inset을 50%로 줄이는 실험성 변경
  - `app/src/main/res/drawable/ic_launcher_foreground.xml`: 이전부터 남아 있던 런처 아이콘 변경
  - 내일 시작 시 `git status --short`와 `git diff`로 확인 후 유지/커밋/되돌림 여부 결정 권장

### 주요 기능 변경 요약

브랜딩/레이아웃:
- 메인 타이틀은 `가지고 싶다`
- `가지`는 당근 스타일을 참고한 가지색 보라 톤
- PC에서도 보기 좋도록 메인/상세/작성 페이지 반응형 보강
- 메인 글쓰기 FAB는 PC/모바일 모두 우하단에 잘 보이도록 조정
- 최신 변경: 스크롤을 내려 목록을 읽으면 상단바가 숨고, 글쓰기 버튼은 보라색 원형 `+`로 축소됨
- 다시 위로 스크롤하면 상단바와 `+ 글쓰기` 버튼이 원래 상태로 복귀

목록/파싱:
- `오늘의 핫딜 / 어제의 핫딜` 구분은 제거
- 현재는 `오늘의 핫딜` 단일 목록만 표시
- 파서는 등록일 기준 최근 48시간 핫딜만 `assets/ppomppu_hotdeals_2days.json`에 저장
- 메인 리스트에 조회수/댓글수 표시
- 삭제된 게시물은 로컬 삭제키와 `assets/hidden_hotdeals.json` 기반으로 다시 보이지 않게 처리

작성/편집:
- 글쓰기 화면에서 사진 첨부 가능
- 이미지 URL 입력은 제거됨
- 대신 `핫딜주소` 필드가 추가됨
- 작성 완료 시 `핫딜주소`가 상세 페이지 하단 `사러가기` 버튼 링크가 됨
- 제목은 필수
- 설명은 빈 값 허용
- 가격은 비우면 자동으로 `0원`
- 상세 우상단 `...` 메뉴:
  - `편집하기`: 가지색 버튼, 삭제 위에 표시
  - `삭제하기`: 빨간색
  - `닫기`
- 편집은 `create.html?editId=...`로 기존 작성 화면을 재사용
- 편집된 글은 `source:'user'`, `edited:true`로 저장되어 다음 파싱 때도 원본 피드로 덮이지 않도록 처리

공유/Android:
- 상세 페이지 우상단 공유 버튼은 Android 브리지 `HotdealAndroid.share(title, url)` 우선 사용
- Android WebView에서 사진 첨부가 되도록 `onShowFileChooser` 구현 완료
- Android 앱이 외부 사이트의 `http/https` URL 공유를 받을 수 있도록 `ACTION_SEND text/plain` 등록
- 외부 사이트에서 가지 앱으로 URL 공유 시:
  - 작성창으로 이동
  - `핫딜주소` 자동 입력
  - `og:title` 또는 `<title>`을 제목에 자동 입력
  - `og:image`를 대표사진 미리보기에 자동 입력
  - `og:description` 또는 `meta description`을 상세내용에 자동 입력
  - 제목/상세내용에서 `12,900원` 같은 `숫자+원` 패턴을 찾아 가격에 자동 입력

### 내일 모바일에서 우선 확인할 것

- Android APK 설치 후 외부 쇼핑몰 페이지에서 공유하기 → 가지 앱 선택
- 작성창에 `핫딜주소`, 제목, 대표사진, 상세내용, 가격이 자동 입력되는지 확인
- 모바일에서 사진 첨부 버튼을 눌렀을 때 갤러리/파일 선택기가 열리는지 확인
- 작성 완료 후 메인 목록 첫 번째에 표시되는지 확인
- 상세에서 `사러가기` 버튼이 `핫딜주소`로 이동하는지 확인
- 상세 `...` 메뉴에서 편집/삭제/닫기 동작 확인
- 편집 후 파서가 다시 돌아도 편집 내용이 유지되는지 확인
- 메인 목록 스크롤 시 상단바 숨김/FAB 원형 축소가 실제 폰에서 자연스러운지 확인

### 로컬 실행/검증 명령

사이트:
```powershell
cd C:\users\namin\hotdeal-site
python -m http.server 4173
```

브라우저:
```text
http://localhost:4173/index.html
http://localhost:4173/create.html
```

Android 빌드:
```powershell
cd C:\users\namin\hotdeal-android
$env:JAVA_HOME="C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat assembleDebug
```

### 작업 습관 메모

- `hotdeal-site` 변경 시 사용자 요청에 따라 커밋과 푸시까지 함께 수행
- Android 프로젝트는 원격이 없으므로 로컬 커밋까지만 가능
- 내일 작업 시작 전:
```powershell
cd C:\users\namin\hotdeal-site
git status --short
git log --oneline -5

cd C:\users\namin\hotdeal-android
git status --short
git log --oneline -5
```
