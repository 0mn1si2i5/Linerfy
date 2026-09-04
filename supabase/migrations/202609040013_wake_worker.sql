-- Immediate worker wake after a job is first enqueued.
--
-- The one-minute cron remains the recovery path. This function lets the
-- authenticated POST /api/context wake the Python worker right after inserting
-- a job, so a newly-detected track starts enriching in seconds instead of
-- waiting for the next cron tick. pg_net queues the HTTP request asynchronously
-- and returns immediately, so the caller never waits on the worker's response
-- inside a transaction.
--
-- The worker URL and bearer secret are read from Vault at run time, never
-- written into this file. Duplicate wakes for the same job are safe: the worker
-- fences with the active-lease predicate and claims with FOR UPDATE SKIP LOCKED,
-- so a second concurrent wake finds nothing to claim and returns 0.

create or replace function public.wake_worker()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  perform net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'linerfy_worker_url'),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'linerfy_worker_secret'),
      'Content-Type', 'application/json'
    ),
    body := '{}'::jsonb
  );
end;
$$;

revoke all on function public.wake_worker() from public, anon, authenticated;
grant execute on function public.wake_worker() to service_role;
