create extension if not exists pgcrypto;

create table if not exists public.admin_reports (
  id uuid primary key default gen_random_uuid(),
  target_type text not null default 'deal',
  target_id text not null default '',
  reason text not null default '',
  memo text not null default '',
  reporter text not null default '',
  status text not null default 'pending',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_admin_reports_status_created_at
  on public.admin_reports (status, created_at desc);

create table if not exists public.admin_notices (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null default '',
  pinned boolean not null default false,
  published boolean not null default true,
  starts_at timestamptz,
  ends_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_admin_notices_published_created_at
  on public.admin_notices (published, created_at desc);

create table if not exists public.user_profiles (
  user_key text primary key,
  provider text not null default '',
  provider_id text not null default '',
  email text not null default '',
  nickname text not null default '',
  status text not null default 'active',
  role text not null default 'user',
  memo text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.user_profiles
  add column if not exists provider text not null default '',
  add column if not exists provider_id text not null default '',
  add column if not exists email text not null default '',
  add column if not exists nickname text not null default '',
  add column if not exists status text not null default 'active',
  add column if not exists role text not null default 'user',
  add column if not exists memo text not null default '',
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

create unique index if not exists user_profiles_nickname_uniq
  on public.user_profiles (nickname)
  where nickname <> '';
