-- Persistent enrichment job queue (a plain table, not pgmq).

create table if not exists public.enrichment_jobs (
  id uuid primary key default gen_random_uuid(),
  entity_kind text not null default 'release' check (entity_kind in ('release')),
  entity_id text not null,
  stage text not null default 'resolve_entity'
    check (stage in (
      'resolve_entity',
      'fetch_sources',
      'build_source_summaries',
      'build_consensus'
    )),
  state text not null default 'queued'
    check (state in ('queued', 'running', 'ready', 'unavailable', 'failed')),
  retry_count integer not null default 0 check (retry_count >= 0),
  last_error text,
  corpus_hash text,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (entity_kind, entity_id)
);

create index if not exists enrichment_jobs_claim_idx
  on public.enrichment_jobs (state, updated_at);

-- A tiny key/value table for service-wide flags (e.g. the global model-
-- generation pause). Kept separate from the catalog so a pause never mixes
-- with entity data.
create table if not exists public.service_flags (
  key text primary key,
  value text not null,
  updated_at timestamptz not null default now()
);

-- Server-only: no grants and no RLS policy, so anon/authenticated cannot read
-- or write the queue. Access is via the service role / the worker connection.
alter table public.enrichment_jobs enable row level security;
alter table public.service_flags enable row level security;
revoke all on public.enrichment_jobs from anon, authenticated;
revoke all on public.service_flags from anon, authenticated;
