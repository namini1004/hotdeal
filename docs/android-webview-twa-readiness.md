# Android WebView/TWA 출시 준비 점검

## 결론

현재 가지딜은 웹이 본체이고 Android는 얇은 WebView 셸로 유지하는 구성이 가장 안전하다.
TWA는 Play 스토어 정식 출시/브라우저 기반 신뢰 UX에는 좋지만, 현재 앱이 쓰는 네이티브 기능 때문에 즉시 전환 1순위는 아니다.

## WebView 유지가 유리한 이유

- 기존 `hotdeal-android`가 이미 `gaji.run` WebView, 하단 탭, 공유 받기, 파일 선택, FCM 토큰 등록을 담당한다.
- Google 로그인 쿠키가 WebView 안에 유지되어야 앱 세션이 안정적이다.
- 푸시 클릭 상세 진입, Android 공유 브릿지, 탭 컨텍스트 유지 같은 앱 전용 흐름을 직접 제어할 수 있다.

## TWA 전환 전 선행 조건

- `https://gaji.run/.well-known/assetlinks.json` 준비
- Android 패키지명/서명 SHA-256 확정
- 하단 탭을 웹 UI로 흡수하거나, TWA 외부 네이티브 탭 구조를 포기할지 결정
- OAuth가 Custom Tabs/TWA 세션에서 기대대로 유지되는지 실기기 검증
- FCM 클릭 URL을 `indexdetail.html?id=...` 또는 `/d/:id` 중 하나로 통일

## 외부 링크 처리 원칙

- `원본보기`: 커뮤니티 원문 링크
- `사러가기`: 실제 구매처 링크
- 루딜처럼 구매처가 분리되지 않은 소스는 `원본보기` 단일 CTA 유지
- 앱에서는 외부 구매처/원문은 가능하면 외부 브라우저 또는 Custom Tab으로 열어 WebView 이탈/결제 이슈를 줄인다.

## 뒤로가기/공유/딥링크 원칙

- 홈 목록 → 상세 → 뒤로가기: 목록 스크롤 복원 유지
- 푸시/공유 딥링크: `/d/:id` 공유 URL을 받고, 최종 상세는 `indexdetail.html?id=:id`로 정규화
- Android 공유 시 제목 + canonical URL(`https://gaji.run/d/:id`) 사용
- 앱 내부 공유 받기는 기존 WebView 작성 화면으로 넘긴다.

## APK 릴리즈 흐름

- 파일명: `gaji_YYMMDD.apk`
- 릴리즈 전 확인:
  - 웹 첫 화면
  - 딜 상세 CTA
  - Google 로그인
  - 키워드 알림 토큰 등록
  - 푸시 클릭 상세 진입
  - Android 13+ 알림 권한

## PWA 대응 상태

- `manifest.webmanifest` 추가
- `service-worker.js` 추가
- API는 서비스워커 캐시 대상에서 제외해서 핫딜 목록/상세 데이터가 오래 고정되지 않게 유지
- 홈 화면 추가 시 standalone 앱처럼 실행되도록 `display: standalone` 설정
