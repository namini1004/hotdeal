# Local Quasar Ingestion

Quasar is collected on the Windows PC, not by GitHub Actions. A successful
`hotdeal-refresh-supabase` workflow only verifies the sources that workflow owns.
Do not tune the temperature model to compensate for a missing source.

## Task And Paths

Register or update the dedicated task from this checkout:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/register_hotdeal_quasar_task_windows.ps1 -RepoPath C:\p4\hotdeal
```

The default task is `HotdealQuasarIngest30m`. Registration is idempotent, keeps
an existing 30-minute timetable, specifies the working directory, and points to
`run_hotdeal_quasar_ingest_windows.ps1`. It does not use the generic
`register_hotdeal_task_windows.ps1` / `refresh_hotdeals_windows.ps1` pair.
Use `-RunNow` only when an immediate collection is required.

Python is resolved to `.tools/hotdeal-python/Scripts/python.exe`; on a new PC,
pass `-PythonPath` with an installed bootstrap Python. Dependencies come from
`scripts/requirements-hotdeal-local.txt`. Secret paths default to this checkout's
`supabase_url.txt`, `supabase_service_role_key.txt`, and `push_ingest_secret.txt`.
They can be overridden with the corresponding registration parameters. Never
commit these files. The push secret is optional for database sync, but its
absence logs `push=disabled` / `ingest=SKIP` and prevents push delivery.

The task uses the current interactive Windows user. The PC must be on and that
user must be logged in; this is not a cloud-hosted collection service.

## Collection Contract

- Fetch one list page every 30 minutes; direct HTTP first, then bounded browser
  and Jina fallback when required. A challenge/error page is not a valid feed.
- Read new details with spacing; reuse successful details, including image-only
  bodies. Remember expired IDs on the current page so coarse date labels do not
  cause repeated requests for the same expired posts.
- Support legacy table rows and the observed v2 div rows. Parse Korean count
  suffixes and dotted dates, use original JSON-LD `datePublished`, and exclude
  blinded posts. Unknown times must not turn into "now".
- Write a partial snapshot atomically to
  `.artifacts/quasar-ingest/quasar_hotdeals_2days.json`. Empty or failed results
  must not overwrite the prior cache. Tracked `assets` feeds are not inputs here.
- Before Supabase sync, require a valid Quasar row within the sync retention
  window (48 hours by default, maximum 10 minutes of future clock skew).
  Empty/stale feeds fail without running sync. Supabase operations remain
  source-scoped and use the existing deduplication and age-pruning rules.
- Partial snapshots protect unseen deals from deletion; they are not failed
  observations. Temperature history uses the active 48-hour DB population after
  applying the successful writes, including earlier pages, for refreshed sources.
  Only genuinely stale fallback data is excluded from history. Model weights are
  unchanged.

## Verification

1. Check `Get-ScheduledTaskInfo -TaskName HotdealQuasarIngest30m`. A completed
   successful run has `LastTaskResult=0`; `267009` means it is still running.
2. Inspect `.artifacts/logs/hotdeal_quasar_task.log`, then
   `.artifacts/logs/hotdeal_quasar_ingest.log`. Expect `QUASAR_LOCAL_START`,
   `QUASAR_FETCH_SUMMARY`, `QUASAR_FEED_VALID`, `UPSERT_OK`, and
   `QUASAR_LOCAL_DONE`. Failures emit `QUASAR_LOCAL_ERROR`.
3. Check actual feed `registeredAt` values, then recent active database rows:

```sql
select count(*) as recent_quasar, min(registered_at), max(registered_at)
from public.deals
where source = 'quasar' and deleted_at is null
  and registered_at >= now() - interval '48 hours'
  and registered_at <= now() + interval '10 minutes';
```

4. Run `node scripts/report_temperature_model.js` with the server-side Supabase
   environment set. It reads data and prints the report without posting an issue.
   Verify the Quasar sample is nonzero; do not infer recovery from Actions alone.

Regression tests include sanitized actual v2 HTML, legacy rows, blocked fallback
responses, unchanged-cache preservation, valid timestamp boundaries, detail
reuse, and mocked Windows task registration. Live scheduler and database checks
are still required to prove end-to-end recovery.

## Recovery Verified On 2026-09-27 (KST)

- The dedicated task already existed. It was not a missing-task incident.
  The database's last prior Quasar update was September 1; that alone does not
  establish when the upstream HTML changed.
- The live list returned HTTP 200, but the legacy `<tr>` parser found no rows in
  the new `v2-list-row` layout. Browser and Jina fallback responses were blocked.
  Dotted dates, Korean count units, CSS thumbnails, and JSON-LD publication times
  also needed support.
- Manual recovery at 11:30 and the ordinary 11:35 scheduled run both completed
  with exit code 0, without browser/Jina fallback. The latter added a new deal.
- The resulting active feed had 19 recent deals. The first 18-deal recovery
  confirmed stored images for all rows and no duplicate IDs or expired/future
  active rows. Expired pre-outage database rows were pruned by the normal sync.
- Read-only report generation at 11:38 showed Quasar sample count 19. A separate
  sync of the already captured feed wrote one 19-item temperature snapshot, with
  `NO_CHANGE` for deals and no additional source-site requests.
- The next scheduled run was 12:05. Push delivery remained disabled because the
  local push secret was absent; database ingestion and temperature history do
  not require it.
