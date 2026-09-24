-- Existing installations: repair only Gaji tables that already exist.
-- No data, policies, default privileges, or unrelated schemas are changed.
begin;
set local lock_timeout = '5s';

grant usage on schema public to service_role;

do $$
declare
  table_name text;
  table_oid regclass;
  sequence_name text;
begin
  foreach table_name in array array[
    'deals', 'favorite_deals', 'read_marks', 'deal_comments',
    'deal_temperature_snapshots', 'board_posts',
    'admin_reports', 'admin_notices', 'user_profiles'
  ] loop
    table_oid := to_regclass(format('public.%I', table_name));
    if table_oid is null then
      continue;
    end if;

    execute format('alter table %s enable row level security', table_oid);
    execute format('revoke all on table %s from public, anon, authenticated', table_oid);
    execute format('grant select, insert, update, delete on table %s to service_role', table_oid);

    -- Production can contain identity/serial columns absent from older SQL files.
    for sequence_name in
      select pg_get_serial_sequence(table_oid::text, a.attname)
      from pg_attribute a
      where a.attrelid = table_oid and a.attnum > 0 and not a.attisdropped
    loop
      if sequence_name is not null then
        execute format('revoke all on sequence %s from public, anon, authenticated', sequence_name);
        execute format('grant usage, select on sequence %s to service_role', sequence_name);
      end if;
    end loop;
  end loop;
end;
$$;

commit;
