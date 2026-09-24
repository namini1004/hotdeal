# Supabase Free 설정

## 1) 테이블 생성(SQL Editor)

새 환경에서는 다음 파일을 순서대로 실행합니다. 각 파일에 테이블 생성,
RLS 활성화, 서버용 Data API 권한이 함께 포함되어 있습니다.

1. [supabase_hotdeal_schema.sql](supabase_hotdeal_schema.sql): 딜, 찜, 읽음, 댓글, 온도 기록
2. [supabase_board_posts.sql](supabase_board_posts.sql): 가지가지 게시글
3. [supabase_admin_schema.sql](supabase_admin_schema.sql): 신고, 공지, 사용자 프로필
4. [supabase_data_api_permissions.sql](supabase_data_api_permissions.sql): 기존 환경의 권한 정리

온도 기록만 추가하는 기존 환경은 [supabase_temperature_model.sql](supabase_temperature_model.sql)을
사용할 수 있습니다. CLI 마이그레이션이나 `db reset`에 이 SQL을 옮길 때도 권한 구문을 함께 포함합니다.

## Data API 권한 (2026-10-30 변경 대비)

가지는 브라우저가 `/api/...`를 호출하고, Vercel API와 수집기가 서버의
`service_role`로 Supabase REST API를 호출합니다. Google 로그인 사용자도
Supabase의 `authenticated` 역할로 DB를 직접 호출하지 않습니다.

- Data API와 `public` 스키마 노출은 유지합니다.
- 앱 테이블에는 RLS를 활성화하고 `service_role`에 SELECT/INSERT/UPDATE/DELETE를 명시합니다.
- `PUBLIC`, `anon`, `authenticated`에는 앱 테이블과 연결된 시퀀스 권한을 부여하지 않습니다.
- identity/serial 시퀀스에는 서버 역할의 USAGE/SELECT도 명시합니다.
- 서버 API는 `service_role`이 RLS를 우회하므로 요청별 인증과 권한 검사를 계속 담당합니다.

기존 운영 DB에서는 **`supabase_data_api_permissions.sql`만 실행**하면 됩니다.
없는 테이블은 건너뛰고, 존재하는 앱 테이블 및 연결된 시퀀스만 처리합니다.
데이터와 RLS 정책, Storage/Auth 스키마, 프로젝트 기본 권한은 변경하지 않습니다.
재실행할 수 있으며, 잠금 대기 시간이 5초를 넘으면 트랜잭션을 중단합니다.

적용 후 [tests/supabase_data_api_permissions.sql](tests/supabase_data_api_permissions.sql)을
SQL Editor에서 실행합니다. 서버의 읽기/쓰기 권한과 클라이언트 접근 차단을 확인하며
잘못된 권한이 있으면 예외가 발생합니다. 실제 요청은 아래 배포 후 확인 항목으로 검증합니다.

공식 안내: [Data API 권한 변경](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically),
[GRANT와 RLS](https://supabase.com/docs/guides/api/securing-your-api).

## 2) Vercel 환경변수
Project Settings → Environment Variables

- `SUPABASE_URL` = `https://<project-ref>.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY` = Supabase Settings > API > service_role

> service_role 키는 서버(API)에서만 사용해야 합니다.

## 3) 배포 후 확인
- `GET /api/deals` 200
- 글쓰기 후 다른 기기에서도 동일 항목 노출
- 수정/삭제 반영 확인
- `GET /api/board-posts` 200
- `board.html`에서 게시글 작성 후 다른 기기에서도 동일 항목 노출
