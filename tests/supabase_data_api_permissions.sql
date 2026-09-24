-- Read-only assertions. Run after bootstrap SQL or the permissions migration.
-- Optional Gaji tables may be absent in an existing installation.
do $$
declare
  table_name text;
  table_oid regclass;
  sequence_name text;
  role_name text;
  privilege_name text;
  checked_tables integer := 0;
begin
  if not has_schema_privilege('service_role', 'public', 'USAGE') then
    raise exception 'service_role requires schema USAGE';
  end if;
  if not (select rolbypassrls from pg_roles where rolname = 'service_role') then
    raise exception 'service_role must bypass RLS for the server API';
  end if;

  foreach table_name in array array[
    'deals', 'favorite_deals', 'read_marks', 'deal_comments',
    'deal_temperature_snapshots', 'board_posts',
    'admin_reports', 'admin_notices', 'user_profiles'
  ] loop
    table_oid := to_regclass(format('public.%I', table_name));
    if table_oid is null then
      continue;
    end if;
    checked_tables := checked_tables + 1;

    if not (select relrowsecurity from pg_class where oid = table_oid) then
      raise exception '% requires RLS', table_name;
    end if;
    foreach role_name in array array['anon', 'authenticated'] loop
      if has_table_privilege(role_name, table_oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') then
        raise exception '% unexpectedly has table access to %', role_name, table_name;
      end if;
      if has_any_column_privilege(role_name, table_oid, 'SELECT,INSERT,UPDATE,REFERENCES') then
        raise exception '% unexpectedly has column access to %', role_name, table_name;
      end if;
    end loop;
    foreach privilege_name in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE'] loop
      if not has_table_privilege('service_role', table_oid, privilege_name) then
        raise exception 'service_role lacks % on %', privilege_name, table_name;
      end if;
    end loop;

    for sequence_name in
      select pg_get_serial_sequence(table_oid::text, a.attname)
      from pg_attribute a
      where a.attrelid = table_oid and a.attnum > 0 and not a.attisdropped
    loop
      if sequence_name is not null then
        foreach role_name in array array['anon', 'authenticated'] loop
          if has_sequence_privilege(role_name, sequence_name, 'USAGE,SELECT,UPDATE') then
            raise exception '% unexpectedly has sequence access to %', role_name, sequence_name;
          end if;
        end loop;
        foreach privilege_name in array array['USAGE', 'SELECT'] loop
          if not has_sequence_privilege('service_role', sequence_name, privilege_name) then
            raise exception 'service_role lacks % on %', privilege_name, sequence_name;
          end if;
        end loop;
      end if;
    end loop;
  end loop;

  if checked_tables = 0 then
    raise exception 'No Gaji tables found; permission checks did not run';
  end if;
end;
$$;
