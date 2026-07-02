# 관심 키워드 푸시 알림 설정

## 1) Vercel 환경변수 (hotdeal-site)
- `FIREBASE_PROJECT_ID`: Firebase 프로젝트 ID
- `FIREBASE_SERVICE_ACCOUNT_JSON`: 서비스 계정 JSON 문자열(권장) 또는 파일 경로
- `PUSH_INGEST_SECRET`: ingest 보호용 임의 시크릿
- `WEB_PUSH_VAPID_PUBLIC_KEY`: PWA Web Push 공개키
- `WEB_PUSH_VAPID_PRIVATE_KEY`: PWA Web Push 개인키
- `WEB_PUSH_CONTACT`: VAPID subject. 예: `mailto:admin@gaji.run`

## 2) sync 스크립트 환경변수
- `PUSH_INGEST_URL`: `https://gaji.run/api/push/ingest`
- `PUSH_INGEST_SECRET`: 위와 동일 값

## 3) Android 설정
- Firebase Console에서 Android 앱(`com.namin.gaji.run`) 등록
- `google-services.json` 다운로드 후 아래 경로에 저장:
  - `hotdeal-android/app/google-services.json`

## 4) Functions 배포
```bash
cd firebase/functions
npm install
npm run build
# firebase cli 로그인/프로젝트 선택 후
npm run deploy
```

## 5) API 사용
- 디바이스 등록: `POST /api/push/register-device`
  - body: `{ "fcmToken": "...", "appVersion": "0.1.0", "enabled": true }`
  - PWA body: `{ "webPushSubscription": { "endpoint": "...", "keys": { "p256dh": "...", "auth": "..." } }, "appVersion": "pwa", "enabled": true }`
  - 인증: 로그인 세션 쿠키 필요
- PWA 공개키 조회: `GET /api/push/register-device?action=vapid-public-key`
- 현재 브라우저 PWA 구독 해제: `DELETE /api/push/register-device`
  - body: `{ "webPushSubscription": { ... } }`
- 키워드 등록: `POST /api/push/keywords`
  - body: `{ "term": "아이패드" }`
- 키워드 조회: `GET /api/push/keywords`
- 키워드 삭제: `DELETE /api/push/keywords?id=<keywordId>`

## 동작 요약
1. 수집 스크립트가 Supabase 변경분을 업서트
2. 변경분을 `/api/push/ingest`로 전송
3. Vercel API가 사용자 키워드를 매칭
4. 사용자+키워드별 30분 알림 창을 확인
5. 첫 매칭은 즉시 발송하고, 같은 창 안의 추가 매칭은 `keyword_alert_windows`에 누적
6. 창이 지난 뒤에는 `관련 새 딜 N개` 묶음 알림을 발송
7. Android 디바이스에는 기존 FCM data 메시지를 발송
8. PWA 브라우저 구독에는 Web Push payload를 발송

## 중복 알림 정리
- PWA standalone에서 브라우저 알림을 켜거나 갱신하면 같은 계정의 기존 브라우저형 Web Push 구독은 `standalone_pwa_registered`로 비활성화한다.
- 특정 브라우저 알림만 끄려면 해당 브라우저에서 `keywords.html`을 열고 브라우저 알림 끄기를 실행한다.
- Android 앱 FCM 토큰은 이 정리 대상이 아니며 계속 유지한다.

## VAPID 키 생성
```bash
node -e "console.log(require('web-push').generateVAPIDKeys())"
```

생성한 키는 Vercel production/preview 환경변수에 같은 값으로 등록한다. Android FCM 키와 별개라서 기존 앱 알림에는 영향을 주지 않는다.
