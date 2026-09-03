-- Worker cron schedule.
--
-- The four-stage enrichment and expired-lease reaping both run inside the
-- Python worker. This migration only schedules a one-minute authenticated ping
-- to that worker. The URL and bearer secret live in Vault and are never
-- committed.

-- One-minute cron pointing at the deployable Python worker (the Worker Vercel
-- Project, root `ingest`), NOT the Next.js reap-only route. The URL and secret
-- are read from Vault at run time and never written into this file:
--   vault.create_secret('https://<worker-project>.vercel.app/api/enrichment', 'linerfy_worker_url')
--   vault.create_secret('<worker secret>', 'linerfy_worker_secret')

-- pg_cron updates an existing named job, so rerunning this is idempotent.
select cron.schedule(
  'linerfy-worker',
  '* * * * *',
  $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'linerfy_worker_url'),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'linerfy_worker_secret'),
      'Content-Type', 'application/json'
    ),
    body := '{}'::jsonb
  )
  $$
);
