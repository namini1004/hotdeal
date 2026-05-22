create extension if not exists pgcrypto;

create table if not exists public.board_posts (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null default '',
  img text not null default '',
  author text not null default '익명',
  views integer not null default 0,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_board_posts_created_at
  on public.board_posts (created_at desc);

create index if not exists idx_board_posts_deleted_at
  on public.board_posts (deleted_at);
