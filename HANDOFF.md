# HANDOFF.md

이 문서는 **hotdeal-site / gaji.run 작업을 Windows Codex 앱, WSL(Hermes), 다른 에이전트가 안전하게 이어받기 위한 인수인계 문서**입니다.

- 마지막 업데이트: 2026-06-05 22:28 KST
- 실제 로컬 작업 폴더: `C:\Users\namin\hotdeal-site` (`/mnt/c/Users/namin/hotdeal-site`)
- 원격 저장소: `https://github.com/namini1004/hotdeal.git`
- 기본 브랜치: `main`
- 현재 최신 커밋: `dbc6cb5 요구사항: 펨딜 이미지 품질 및 사용자 이미지 640px 정규화`
- 주의: Git push는 기본 수행하되, **Vercel production deploy는 사용자가 명시 요청할 때만 실행**한다.

---

## 1) 현재 서비스 구조 요약

### 서비스/도메인

- 웹 서비스: `gaji.run` / Vercel 프로젝트 `hotdeal`, `hotdeal-site` 계열
- GitHub 원격: `namini1004/hotdeal`
- 데이터 저장: Supabase `deals`, `board_posts`, comments/profile 관련 API
- 이미지 저장:
  - feed 이미지: Supabase Storage `deal-images/<source>/...webp`
  - user 업로드 이미지: Supabase Storage `hotdeal-images/user/...jpg` 또는 640px 변환 URL

### 핵심 화면

- `index.html`: 핫딜 홈
- `indexdetail.html`: 핫딜 상세
- `indexcreate.html`: 핫딜 작성/수정
- `gajigaji.html`: 가지가지/쇼핑팁 화면
- `my-gaji.html`: 내 가지/계정 화면
- `favorites.html`: 찜/저장 관련 화면

### 현재 노출 정책

- 웹 상단 메뉴는 현재 **홈 / 가지가지 / 내 가지** 3개 중심이다.
- 채팅은 사용자가 다시 요청할 때까지 숨김 상태로 유지한다.
- 하단 네비게이션 탭은 메인(index)에서만 노출하고 상세(detail)에는 넣지 않는다.
- 사용자가 명시 요청하지 않은 Vercel prod 배포는 절대 하지 않는다.

---

## 2) 이번 주 핵심 변경 요약

이번 주 작업의 중심은 **피드 안정화, FMKorea(펨딜) 수집 구조 분리, 이미지 품질 개선, 가지가지 팁 운영 자동화, PWA/설치성 개선, 새로고침 안정화**입니다.

최근 주요 커밋:

```text
dbc6cb5 요구사항: 펨딜 이미지 품질 및 사용자 이미지 640px 정규화
ca45642 요구사항: 펨코 수집을 Hermes 로컬 업서트로 분리
87af25b 요구사항: 가지가지 팁 탭 단일화
ce05638 요구사항: PWA 설치 이름과 아이콘 변경
a20fc53 요구사항: PWA 설치 유도와 펨딜 파싱 보강
63ce5fd 요구사항: 새로고침 artifact 병합 보정
e51c991 요구사항: 핫딜 새로고침 안정화
ce9abe4 요구사항: 펨딜 stale fallback 삭제 방지
749839a 요구사항: 최신딜 새로고침 및 정렬 보정
d39ceb7 요구사항: 썸네일 오매칭 및 중복 딜 정리
51f428c 요구사항: 부정 댓글 및 비추천 온도 패널티 강화
bbd92cc 요구사항: 뽐뿌 경고 이미지 fallback 반영
```

---

## 3) 데이터 수집/동기화 현재 구조

### Feed 소스

현재 핫딜 feed 주요 source:

- `ppomppu`: 뽐딜
- `quasar`: 퀘딜
- `fmkorea`: 펨딜
- `ruliweb`: 루딜
- `user`: 사용자 등록 가지딜

### 중요 스크립트

- `scripts/update_ppomppu_feed.py`
  - 뽐뿌 48시간 수집
  - 뽐뿌 CDN hotlink 경고 이미지 방어와 Storage 미러링 계약과 연결

- `scripts/update_quasar_feed.py`
  - 퀘이사존 수집
  - rendered markdown fallback / pagination / thumbnail cache pollution 방어가 중요

- `scripts/update_fmkorea_feed.py`
  - FMKorea 수집
  - 로컬에서는 정상 수집 가능
  - GitHub hosted runner에서는 430 보안/Turnstile/IP 평판 문제로 0건이 될 수 있음
  - 최신순/default URL 기준으로 48시간, 최대 10페이지 순회
  - 상세에서 `buyLink`, `desc`, `likes`, comment quality, 실제 상품 이미지 보강

- `scripts/update_ruliweb_feed.py`
  - 루리웹 수집
  - 목록 제목 파싱은 `subject_link` 범용 매칭 주의
  - `buyLink`는 본문 하단 `출처: http...` 우선

- `scripts/sync_hotdeals_to_supabase.py`
  - 수집 JSON들을 Supabase `deals` 테이블로 upsert
  - soft-delete / restore 처리
  - `img` / `detail_img` Storage WebP 미러링 처리
  - 뽐뿌/루리웹/펨딜 이미지는 동기화 시 Storage로 미러링 대상

- `scripts/hermes_fmkorea_ingest.py`
  - FMKorea만 로컬 Hermes/WSL에서 수집 후 Supabase에 source-scoped upsert
  - hosted runner 차단 우회 목적
  - 수동 실행 성공 확인됨

### Supabase credential 파일 위치

절대 토큰 값을 문서/응답에 노출하지 않는다.

```text
/mnt/c/codex/supabase_url.txt
/mnt/c/codex/supabase_jwt.txt
/mnt/c/codex/supabase_service_role_key.txt
/mnt/c/codex/supabase_usagetoken.txt
```

---

## 4) 이번 주 중요 이슈와 해결 내용

### 4-1. FMKorea hosted runner 차단 / 로컬 ingest 분리

확인된 사실:

- GitHub hosted runner(Azure IP)는 FMKorea에서 `430` 보안 페이지/Turnstile 계열 차단을 받을 수 있다.
- 로컬 WSL/Hermes에서는 `requests`/Playwright 경로로 FMKorea 목록 수집이 가능하다.
- Actions에서 0건이 나왔을 때 기존 row를 soft-delete하면 펨딜이 운영에서 사라질 수 있으므로, stale fallback/zero source guard가 중요하다.

현재 방향:

- 일반 all-source GitHub Actions 갱신과 별개로, FMKorea는 로컬 Hermes ingest로 source-scoped upsert하는 구조를 사용.
- `scripts/hermes_fmkorea_ingest.py --verbose` 수동 실행 결과:
  - 2026-06-05 기준 162건 수집
  - `UPSERT_OK total=162 changed=162 deleted=0 ingest=SKIP`

주의:

- Hermes cron `hotdeal-fmkorea-local-ingest`는 등록돼 있으나 2026-06-05 22시 기준 최근 상태가 `error`로 표시됐다.
- 반면 repo 내 `python3 scripts/hermes_fmkorea_ingest.py --verbose` 수동 실행은 성공했다.
- 다음 인계자는 `~/.hermes/scripts/hotdeal_fmkorea_ingest.py` 래퍼 경로/환경변수/working directory를 점검해야 한다.

### 4-2. AWS Lambda/EventBridge 검토

이전 대화 결론:

- Firebase 단독, 특히 Spark 무료 플랜은 Cloud Functions 운영에 적합하지 않음.
- AWS Lambda + EventBridge가 소형 실험 후보로 더 낫다.
- 단, FMKorea가 GitHub IP만 막는 것이 아니라 클라우드/데이터센터 IP 전반을 막는다면 AWS도 실패할 수 있다.
- 따라서 곧장 이전하지 말고 **AWS Lambda probe**로 먼저 확인한다.

Probe 기준:

- Lambda에서 `https://m.fmkorea.com/index.php?mid=hotdeal&listStyle=webzine&page=1` 요청
- status 200 여부
- `보안 시스템`/Turnstile 페이지 여부
- `쇼핑몰:`/`가격:`/`배송:` 포함 row 추출 가능 여부
- 실패 시 로컬 Hermes cron/self-hosted runner 유지가 안전

관련 참고 skill reference:

```text
references/fmkorea-aws-lambda-ingest-probe.md
references/local-hermes-source-ingest-cron.md
```

### 4-3. 펨딜 이미지 품질 개선

문제:

- FMKorea 목록 이미지가 `.../cache/thumb/..._70x50.crop.webp` 또는 140x100급 목록 썸네일로 들어오면 상세 hero에서 심하게 확대/열화됨.
- 단순히 fmkorea를 Storage 미러링 대상에 넣으면 70x50 원본을 그대로 WebP로 변환해 `detail640`이라는 파일명인데 실제 픽셀은 70x50인 문제가 발생했다.

해결:

- `scripts/update_fmkorea_feed.py`
  - `/cache/thumb/` 이미지는 저품질 후보로 간주
  - 상세 DOM에서 `data-src`, `data-original`, `src` 순으로 실제 이미지 재추출
  - Playwright 상세 DOM이 실패하거나 썸네일만 잡으면 `requests` 상세 HTML에서 `og:image`/본문 첨부 이미지 fallback 추출
  - `/modules/point/icons/`, FMKorea 로고, transparent gif 제외
  - `detailImg` 필드도 실제 첨부 이미지로 저장

- `scripts/sync_hotdeals_to_supabase.py`
  - `fmkorea`를 `IMAGE_HEADERS_BY_SOURCE`에 추가
  - `row_id_from_source_link()`에서 `fmkorea.com/<document_id>` 추출
  - `/cache/thumb/` 이미지는 미러링 후보에서 차단
  - 품질 전환 중에는 fmkorea 기존 Storage WebP 재사용을 막아 원본 첨부에서 새로 생성
  - 결과: `img`는 320px급 WebP, `detail_img`는 640px급 WebP

검증 결과:

```text
python3 scripts/hermes_fmkorea_ingest.py --verbose
# saved: assets/fmkorea_hotdeals_2days.json (162 items)
# UPSERT_OK total=162 changed=162 deleted=0 ingest=SKIP
```

JSON 검증:

```text
total 162
full_img 162
thumb_img 0
blank 0
```

Supabase 최신 30건 샘플 검증:

```text
storage_urls 60
direct_urls 0
blank 0
sample_small<=80px 0
sample_detail>=300px 7
```

샘플 이미지 크기:

```text
img        (196, 320) WEBP
detail_img (391, 640) WEBP
img        (258, 320) WEBP
detail_img (517, 640) WEBP
img        (320, 306) WEBP
detail_img (640, 613) WEBP
```

### 4-4. 사용자 등록 이미지 640px 정규화

문제:

- 사용자 등록 이미지가 원본 URL 또는 큰 업로드 이미지로 들어오면 과도하게 클 수 있음.

해결:

- `indexcreate.html`
  - 첨부 파일 압축 기준을 `maxSide=960`에서 `maxSide=640`으로 변경
  - `maxLen`은 `50_000`에서 `80_000`으로 완화해 640px 품질을 확보

- `api/_lib/deals.js`
  - `normalizeUserImageUrl()` 추가
  - user 이미지 저장/응답 시 http(s) 이미지는 다음 형태로 정규화:

```text
https://wsrv.nl/?url=<encoded-host-path-query>&w=640&h=640&fit=inside&output=webp
```

검증:

```text
node - <<'NODE'
const { mapPayload, normalizeUserRow } = require('./api/_lib/deals');
const raw = 'https://example.com/images/product-large.jpg?x=1';
const mapped = mapPayload({ title: 't', img: raw });
const row = normalizeUserRow({ id: '1', title: 't', img: raw, detail_img: raw });
console.log(mapped.img.includes('w=640') && row.detailImg.includes('h=640'));
NODE
# true
```

### 4-5. 루딜 이미지 방식 정정

중요 정정:

- 루딜은 단순 CDN URL 직접 로딩 구조가 아니다.
- 현재 `scripts/sync_hotdeals_to_supabase.py` 기준 `ruliweb`은 이미 `IMAGE_HEADERS_BY_SOURCE`에 포함되어 있고, 동기화 시 Supabase Storage `deal-images/ruliweb/...webp` 미러링 대상이다.
- 다만 실제 운영 샘플에 루딜 건수가 적거나 없으면 확인 시 안 보일 수 있다.

### 4-6. 뽐뿌 이미지 hotlink 경고 이미지 대응

이번 주 초반 주요 안정화:

- 뽐뿌 CDN 이미지는 서버에서 200이어도 브라우저에서 `403 Forbidden - Invalid image reference` 이미지가 200 JPEG로 내려올 수 있다.
- `<img onerror>`로 감지되지 않는다.
- 동기화 단계에서 뽐뿌 referer로 1회 다운로드 후 355x138 약 25KB 경고 이미지를 감지하고, 실제 상품 이미지를 Storage에 미러링하는 구조로 전환했다.
- 운영 DB에는 장기적으로 원본 `cdn*.ppomppu.co.kr` 직접 URL을 남기지 않는 것이 원칙이다.

### 4-7. 가지온도 부정 신호 강화

요구사항:

- 바이럴/업체/비싸다/안사요 등 부정 댓글 신호나 비추천이 3개 이상이면 최신성·댓글수·무료딜 보정과 무관하게 온도는 50점을 초과하면 안 된다.

현재 반영:

- `api/_lib/deals.js`에서 `computeHotScore`, `applyTemperatureNormalization`, negative cap 로직을 운영 중.
- 파서 쪽에서 `commentSignalScore`, `positiveCommentSignals`, `negativeCommentSignals`, `likes/dislikes` 등을 source별로 저장한다.
- 신규 지표 추가 시 Supabase 스키마와 payload를 같이 맞춰야 한다.

### 4-8. 새로고침 / artifact 병합 / soft-delete 안정화

이번 주 여러 커밋에서 정리한 핵심:

- source별 parser job 결과 artifact가 하위 디렉터리로 풀릴 수 있으므로 upsert 단계에서 실제 artifact path/source row count를 로그로 확인해야 한다.
- 특정 source가 0건이면 전체 source soft-delete가 발생하지 않게 source-aware guard가 필요하다.
- API dedupe는 `source+canonical sourceLink` 기준으로 최신 row를 우선 선택해야 한다.
- `scope=all`에서 user 조회 필터가 누락되면 feed row가 user로 섞일 수 있으므로 source 분포를 항상 교차 검증한다.

---

## 5) 가지가지 / 쇼핑팁 현재 운영

### 현재 제품 규칙

- `gajigaji.html`은 쇼핑팁 중심으로 운영.
- 여러 가지 팁 / 내가 올린 핫딜 탭 구조는 숨기고, tips-only 모드로 정리했다.
- 작성/수정 경로도 `category=tips` 고정 흐름을 유지한다.

### 자동 작성 규칙

- 매일 gaji.run 가지가지 > 여러 가지 팁 글 1개 자동 작성 cron이 있다.
- 사용자가 선호한 참고 방향:
  - 노써치
  - 귀곰
  - 잇섭
  - 정가거부
  - 최근 유튜브/콘텐츠가 있으면 그 내용을 우선 주제로 삼음
- 글 스타일:
  - 정부 공식문서식/딱딱한 참고근거 나열 금지
  - 실사용 리뷰·쇼핑 채널을 종합한 짧고 실용적인 인사이트형 글
  - 출처 요약문보다 “구매 기준/체감 포인트” 중심

### 관련 cron

- `daily-gajigaji-shopping-tip-post`
  - schedule: `0 12 * * *`
  - deliver: origin
  - enabled: true
  - 최근 상태: ok

---

## 6) PWA / 설치성 변경

이번 주 변경:

- PWA 설치 이름과 아이콘 변경.
- 설치 유도 UI/메타 보강.
- 관련 파일은 `manifest.webmanifest`, icon assets, service worker 관련 파일을 확인.

주의:

- PWA/아이콘 변경은 캐시 영향이 있을 수 있으므로 운영 확인 시 hard refresh 또는 새 설치 테스트 권장.
- Android WebView와 모바일웹은 nav 책임이 다르므로 앱 WebView에서 중복 네비가 생기지 않는지 확인해야 한다.

---

## 7) 현재 Hermes cron / 자동화 상태

2026-06-05 22:28 KST 기준 확인한 cron 상태 요약:

### Enabled / scheduled

- `infra-usage-report-every-3h-with-vercel-deploys`
  - schedule: every 180m
  - script: `infra_usage_report.py`
  - 최근 상태: ok
  - Vercel/Supabase 사용량 및 당일 prod 배포 횟수 보고용

- `daily-gajigaji-shopping-tip-post`
  - schedule: `0 12 * * *`
  - 최근 상태: ok

- `hotdeal-refresh-watchdog`
  - schedule: every 15m
  - script: `hotdeal_refresh_watchdog.py`
  - 최근 상태: ok

- `hotdeal-refresh-aux-watchdog`
  - schedule: every 15m
  - script: `hotdeal_refresh_watchdog.py`
  - 최근 상태: ok

- `hotdeal-fmkorea-local-ingest`
  - schedule: every 15m
  - script: `hotdeal_fmkorea_ingest.py`
  - 최근 상태: error
  - 중요: repo 내 `scripts/hermes_fmkorea_ingest.py --verbose`는 성공했으므로 Hermes script wrapper 환경을 점검해야 한다.

### Paused

- `hotdeals-15m-refresh-all-sources`
  - script: `cron_refresh_hotdeals.sh`
  - 상태: paused
  - 과거 all-source 15분 refresh job으로 보이며 현재는 사용하지 않음/보류 상태

---

## 8) 로컬/운영 검증 명령 모음

### 시작 전 저장소 상태

같은 PC에서 WSL/Hermes와 Windows Codex는 같은 작업 폴더를 보므로 보통 pull 불필요. 그래도 시작 전 확인:

```bash
cd /mnt/c/Users/namin/hotdeal-site
git status -sb
git log --oneline -10
```

다른 컴퓨터/새 환경이면:

```bash
git pull origin main
```

### 문법/테스트

```bash
cd /mnt/c/Users/namin/hotdeal-site
python3 -m py_compile scripts/update_fmkorea_feed.py scripts/sync_hotdeals_to_supabase.py
node -c api/_lib/deals.js
python3 -m pytest tests/test_fmkorea_static_fallback.py tests/test_sync_soft_delete_guard.py
```

2026-06-05 결과:

```text
5 passed
```

### FMKorea 수동 ingest

```bash
cd /mnt/c/Users/namin/hotdeal-site
python3 scripts/hermes_fmkorea_ingest.py --verbose
```

예상 성공 로그:

```text
FMKOREA_LIST_CANDIDATE ... rows=162
saved: ... assets/fmkorea_hotdeals_2days.json (162 items)
UPSERT_OK total=162 changed=162 deleted=0 ingest=SKIP
```

### 펨딜 이미지 품질 확인

```bash
cd /mnt/c/Users/namin/hotdeal-site
python3 - <<'PY'
import json
from pathlib import Path
items=json.loads(Path('assets/fmkorea_hotdeals_2days.json').read_text(encoding='utf-8')).get('items',[])
thumb=sum(1 for it in items if '/cache/thumb/' in (it.get('img') or ''))
blank=sum(1 for it in items if not it.get('img'))
full=sum(1 for it in items if it.get('img') and '/cache/thumb/' not in it.get('img'))
print('total',len(items),'full_img',full,'thumb_img',thumb,'blank',blank)
PY
```

정상 기준:

```text
total 162 full_img 162 thumb_img 0 blank 0
```

### 사용자 이미지 640 정규화 확인

```bash
node - <<'NODE'
const { mapPayload, normalizeUserRow } = require('./api/_lib/deals');
const raw = 'https://example.com/images/product-large.jpg?x=1';
const mapped = mapPayload({ title: 't', img: raw });
const row = normalizeUserRow({ id: '1', title: 't', img: raw, detail_img: raw });
console.log(mapped.img);
console.log(row.detailImg);
console.log(mapped.img.includes('w=640') && row.detailImg.includes('h=640'));
NODE
```

정상 기준:

```text
true
```

### 로컬 UI 미리보기

단순 정적 서버는 `/api/deals`를 처리하지 못할 수 있다. UI만 볼 때는 가능하지만 API 연동 검증은 `vercel dev` 또는 live API 프리뷰 서버 패턴을 사용한다.

```bash
python3 -m http.server 4173
```

브라우저:

```text
http://localhost:4173/index.html
http://localhost:4173/indexdetail.html?id=<id>
```

---

## 9) 배포/푸시 정책

### Git

사용자 선호:

- 코드 변경 완료 시 기본적으로 commit + push까지 수행.
- 커밋 메시지는 한국어, 첫 줄은 `요구사항: ...` 형식.
- 본문에는 `요청사항`, `작업 내용`, 가능하면 `기대 효과` 포함.

예시:

```text
요구사항: 펨딜 이미지 품질 및 사용자 이미지 640px 정규화

- 요청사항
  - 펨딜 이미지를 뽐딜 수준으로 320/640 Storage WebP 구조에 맞춤
  - 사용자 등록 이미지를 640px 수준으로 제한

- 작업 내용
  - scripts/update_fmkorea_feed.py: cache/thumb 썸네일 배제 및 상세 첨부 이미지 재추출
  - scripts/sync_hotdeals_to_supabase.py: fmkorea Storage 미러링 추가

- 기대 효과
  - 펨딜 상세 이미지가 70x50 목록 썸네일로 확대되는 문제 감소
```

### GitHub push 인증

일반 push에서 HTTPS username/password prompt 실패 가능:

```text
fatal: could not read Username for 'https://github.com': No such device or address
```

이때 PAT 파일은 아래에 있음. 토큰값은 절대 출력하지 않는다.

```text
/mnt/c/codex/pat.txt
```

필요 시 `GIT_ASKPASS` 임시 스크립트로 push 가능.

### Vercel prod 배포

중요:

- `hotdeal`/`hotdeal-site`는 GitHub push 자동 배포를 막기 위해 Vercel 설정에서 deployment 생성이 제한되어 있다.
- `vercel.json`에도 `git.deploymentEnabled=false`가 추가되어 있다.
- 따라서 `git push`는 코드 저장소 반영일 뿐, 운영 prod 배포 완료를 의미하지 않는다.
- 사용자가 명시적으로 운영 배포를 요청했을 때만 Vercel CLI/REST deploy를 실행한다.
- 배포 요청이 없으면 절대 prod deploy하지 않는다.

---

## 10) 자주 발생 가능한 이슈와 대응

### 이슈 A) 펨딜이 갑자기 사라짐/0건

가능 원인:

- GitHub Actions hosted runner가 FMKorea 430 보안 페이지를 받아 0건 수집
- stale fallback/soft-delete guard 미작동
- 로컬 Hermes ingest cron wrapper 실패

대응:

1. 운영 API source 분포 확인
2. Actions 로그에서 `WARN_FMKOREA_ZERO_ITEMS_KEEP_PREVIOUS`, `saved: ... fmkorea ...`, `UPSERT_OK ... deleted=N` 확인
3. 로컬에서 수동 실행:

```bash
python3 scripts/hermes_fmkorea_ingest.py --verbose
```

4. Hermes cron wrapper `~/.hermes/scripts/hotdeal_fmkorea_ingest.py` 점검

### 이슈 B) 펨딜 상세 이미지가 흐림/작음

가능 원인:

- `/cache/thumb/` 목록 썸네일이 다시 들어옴
- 기존 저품질 Storage WebP가 재사용됨

대응:

- `assets/fmkorea_hotdeals_2days.json`에서 `/cache/thumb/` 건수 확인
- Supabase `deals`의 `img`, `detail_img`가 `deal-images/fmkorea/...thumb...webp`, `...detail640...webp`인지 확인
- 실제 이미지 픽셀 크기를 PIL로 측정

### 이슈 C) 뽐딜 이미지가 403 경고 이미지처럼 보임

가능 원인:

- 원본 `cdn*.ppomppu.co.kr` 직접 URL이 DB에 남음
- 경고 이미지가 HTTP 200으로 내려와 onerror가 동작하지 않음

대응:

- 동기화 단계에서 Storage WebP로 미러링되었는지 확인
- 355x138, 약 25KB JPEG 경고 이미지를 감지하는 로직 유지

### 이슈 D) 사용자 등록 이미지가 너무 큼

대응:

- `indexcreate.html`의 `maxSide=640` 유지 확인
- API user row normalize에서 `wsrv.nl ... w=640&h=640` 변환 확인

### 이슈 E) 운영 반영이 안 된 것처럼 보임

가능 원인:

- push는 됐지만 prod deploy를 하지 않았음
- Vercel 자동 배포가 intentionally disabled
- API/브라우저 캐시

대응:

- 먼저 사용자에게 prod 배포 요청 여부 확인
- 명시 요청 없으면 deploy하지 않음
- 운영 확인 시 API cache-bust query 사용

---

## 11) 다음 작업 후보 / 우선순위

### 1순위: FMKorea 로컬 ingest cron error 점검

현재 수동 실행은 성공했지만 Hermes cron 상태가 error다.

확인할 것:

- `~/.hermes/scripts/hotdeal_fmkorea_ingest.py` 내용
- working directory가 `/mnt/c/Users/namin/hotdeal-site`인지
- 필요한 Supabase credential 파일 경로 접근 가능 여부
- stdout/stderr가 비어야 정상 조용히 지나가도록 되어 있는지

### 2순위: AWS Lambda probe

목표:

- FMKorea가 AWS Lambda IP에서 목록 1페이지를 정상 반환하는지 확인
- 성공하면 EventBridge 기반 소형 수집 실험 가능
- 실패하면 로컬 Hermes/self-hosted runner 유지

### 3순위: 운영 이미지 품질 정기 감사

- source별 최신 20건의 `img/detail_img` host 분포
- actual pixel size
- content-type / format
- `/cache/thumb/`, placeholder, blank URL 건수

### 4순위: PWA/Android WebView 실제 단말 검증

- 설치 이름/아이콘
- 앱 WebView와 모바일웹 네비 중복 여부
- Google OAuth 외부 브라우저 위임/딥링크 복귀
- push/keyword notify 연계 여부

### 5순위: 가지가지 자동 글 품질 점검

- 최근 게시글이 tips-only category로 잘 들어가는지
- 출처 나열식이 아닌 실사용 쇼핑팁 톤인지
- 이미지 URL이 깨지지 않는지

---

## 12) 작업 시작/종료 체크리스트

### 시작 전

- [ ] `cd /mnt/c/Users/namin/hotdeal-site`
- [ ] `git status -sb`
- [ ] `git log --oneline -10`
- [ ] 같은 PC면 보통 pull 불필요, 다른 PC면 `git pull origin main`
- [ ] 작업 범위 확인: 웹만인지, Android도 포함인지, prod deploy 요청이 있는지

### 변경 후

- [ ] 문법 검사: `py_compile`, `node -c`
- [ ] 관련 pytest 실행
- [ ] 실제 수집/운영 API 검증이 필요한 작업이면 샘플 row/이미지 픽셀까지 확인
- [ ] 커밋 메시지 `요구사항: ...` 형식
- [ ] `git push origin main`
- [ ] prod deploy는 명시 요청이 있을 때만

---

## 13) Android 관련 오래된 인계 메모

이 문서의 과거 섹션에는 2026-05 Android WebView 작업 메모가 있었다. 최신 웹 작업과 직접 연결되는 핵심만 남긴다.

- Android 앱은 WebView shell 역할이며, 네이티브 하단 탭/푸시/공유 받기/권한을 담당한다.
- 웹 detail/index에 앱 네이티브와 중복되는 하단 탭을 함부로 추가하지 않는다.
- Google OAuth는 Android WebView에서 `disallowed_useragent`가 날 수 있으므로 외부 브라우저/Custom Tabs 위임을 기본으로 한다.
- APK 전달 시 사용자는 `gaji_YYMMDD.apk` 형식의 파일명을 선호한다.

---

끝.
