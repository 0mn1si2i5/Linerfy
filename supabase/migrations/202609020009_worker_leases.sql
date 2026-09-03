-- Short, atomic worker leases.
--
-- A worker claims a job by writing a fresh `lease_id` and `lease_expires_at` in
-- one short transaction, then performs external HTTP/model work OUTSIDE any
-- transaction, then commits its result with a compare-and-set on
-- `(id, lease_id)`. A stale worker whose lease was reaped can therefore never
-- overwrite a newer claim. `attempt` tracks retries independent of the CAS.

alter table public.enrichment_jobs
  add column if not exists lease_id uuid,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists attempt integer not null default 0;

create index if not exists enrichment_jobs_lease_idx
  on public.enrichment_jobs (state, lease_expires_at);
