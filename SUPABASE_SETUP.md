# Supabase Free 설정

## 1) 테이블 생성(SQL Editor)
```sql
create extension if not exists pgcrypto;

create table if not exists public.deals (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  "desc" text not null default '',
  price text not null default '0원',
  category text not null default '디지털',
  img text not null default '',
  buy_link text not null default '',
  source_link text not null default '',
  area text not null default '오늘의 핫딜',
  dist text not null default '방금 등록',
  "time" text not null default '방금 전',
  views integer not null default 0,
  comments integer not null default 0,
  "date" text not null default '',
  registered_at timestamptz not null default now(),
  source text not null default 'user',
  edited boolean not null default false,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_deals_created_at on public.deals (created_at desc);
create index if not exists idx_deals_deleted_at on public.deals (deleted_at);
```

## 2) Vercel 환경변수
Project Settings → Environment Variables

- `SUPABASE_URL` = `https://<project-ref>.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY` = Supabase Settings > API > service_role

> service_role 키는 서버(API)에서만 사용해야 합니다.

## 3) 배포 후 확인
- `GET /api/deals` 200
- 글쓰기 후 다른 기기에서도 동일 항목 노출
- 수정/삭제 반영 확인
