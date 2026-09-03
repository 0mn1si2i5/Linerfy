-- Worker maintenance + cron schedule.
--
-- The heavy five-stage enrichment runs in the Python worker; this migration
-- provides (a) an atomic reap of timed-out jobs and (b) a pg_cron schedule that
-- pings the protected Vercel worker route once a minute. The worker URL and
-- secret live in Vault and are never committed.

create or replace function public.reap_enrichment_timeouts()
returns integer
language sql
security definer
set search_path = public
as $$
  with timed_out as (
    select id, retry_count
    from public.enrichment_jobs
    where state = 'running' and timeout_at < now()
    for update
  ), updated as (
    update public.enrichment_jobs j
    set retry_count = j.retry_count + 1,
        state = case when j.retry_count < 2 then 'queued' else 'failed' end,
        last_error = 'stage timeout',
        claimed_at = null,
        timeout_at = null,
        updated_at = now()
    from timed_out t
    where j.id = t.id
    returning j.id
  )
  select count(*)::integer from updated;
$$;

revoke all on function public.reap_enrichment_timeouts() from public, anon, authenticated;

-- One-minute cron pointing at the deployable Python worker (the Worker Vercel
-- Project, root `ingest`), NOT the Next.js reap-only route. The URL and secret
-- are read from Vault at run time and never written into this file:
--   vault.create_secret('linerfy_worker_url', 'https://<worker-project>.vercel.app/api/enrichment')
--   vault.create_secret('linerfy_worker_secret', '<worker secret>')

-- Idempotent: drop any schedule of the same name before creating it.
select cron.unschedule('linerfy-worker');

select cron.schedule(
  'linerfy-worker',
  '* * * * *',
  $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'linerfy_worker_url'),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'linerfy_worker_secret')
    )
  )
  $$
);
