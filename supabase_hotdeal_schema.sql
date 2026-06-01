create extension if not exists pgcrypto;

create table if not exists public.deals (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'user',
  source_link text not null default '',
  buy_link text not null default '',
  title text not null,
  "desc" text not null default '',
  price text not null default '',
  category text not null default '기타',
  img text not null default '',
  detail_img text not null default '',
  area text not null default '오늘의 핫딜',
  dist text not null default '기타',
  time text not null default '',
  likes integer not null default 0,
  views integer not null default 0,
  comments integer not null default 0,
  date text not null default '',
  registered_at timestamptz,
  deleted_at timestamptz,
  edited boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.deals
  add column if not exists source text not null default 'user',
  add column if not exists source_link text not null default '',
  add column if not exists buy_link text not null default '',
  add column if not exists likes integer not null default 0,
  add column if not exists views integer not null default 0,
  add column if not exists comments integer not null default 0,
  add column if not exists category text not null default '기타',
  add column if not exists detail_img text not null default '',
  add column if not exists area text not null default '오늘의 핫딜',
  add column if not exists dist text not null default '기타',
  add column if not exists time text not null default '',
  add column if not exists date text not null default '',
  add column if not exists registered_at timestamptz,
  add column if not exists edited boolean not null default false;

create unique index if not exists deals_source_source_link_uniq
  on public.deals (source, source_link)
  where source <> 'user' and source_link <> '';

create index if not exists idx_deals_source_registered_at
  on public.deals (source, registered_at desc);

create index if not exists idx_deals_deleted_at
  on public.deals (deleted_at);

create table if not exists public.favorite_deals (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  deal_key text not null,
  created_at timestamptz not null default now(),
  unique (user_id, deal_key)
);

create table if not exists public.read_marks (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  deal_key text not null,
  read_at timestamptz not null default now(),
  unique (user_id, deal_key)
);

create table if not exists public.deal_comments (
  id uuid primary key default gen_random_uuid(),
  deal_key text not null,
  nickname text not null default '익명 가지',
  body text not null,
  guest_key text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists idx_deal_comments_deal_key_created_at
  on public.deal_comments (deal_key, created_at desc);
