-- Document-level license + provider rating snapshots.
--
-- A review document may carry its own license (e.g. each CritiqueBrainz review
-- reports its own license_id), distinct from the source-level access/retention
-- policy. The summarizer keys its license pool on the document's license, so
-- two documents from one source under different licenses stay in separate pools.
--
-- Ratings are a release-level snapshot per provider (MusicBrainz community
-- rating, CritiqueBrainz official average), independent of any review document:
-- a score-only source still surfaces without an empty excerpt or a model call.

-- 1. Document-level license.
alter table public.review_documents add column if not exists license_id text;
alter table public.review_documents add column if not exists license_url text;

-- Backfill existing documents from their source's policy license (the only
-- license available when they were stored), then make the columns non-null.
update public.review_documents d
set
  license_id = coalesce(d.license_id, p.license_id),
  license_url = coalesce(d.license_url, p.license_url)
from public.source_policies p
where p.source_id = d.source_id
  and (d.license_id is null or d.license_url is null);

alter table public.review_documents alter column license_id set not null;
alter table public.review_documents alter column license_url set not null;

-- 2. Release-level rating snapshots, one per (release, provider).
create table if not exists public.release_ratings (
  id uuid primary key default gen_random_uuid(),
  release_id uuid not null references public.releases(id) on delete cascade,
  provider text not null,
  value numeric,
  scale integer,
  vote_count integer,
  source_url text,
  updated_at timestamptz not null default now(),
  unique (release_id, provider)
);

-- Server-only: catalog reads go through the service role, so ratings (like the
-- queue) are granted nothing to anon/authenticated.
alter table public.release_ratings enable row level security;
revoke all on public.release_ratings from anon, authenticated;
grant select on public.release_ratings to service_role;

-- Source summaries must not replace another license pool from the same provider.
update public.summary_runs
set scope = 'source::' || coalesce(source_id, license_pool, 'unscoped') || '::' || license_pool
where summary_kind = 'source';

alter table public.enrichment_jobs add column if not exists source_errors text[] not null default '{}';

-- A user retry resumes the existing job, never creates a second job or steals
-- a running lease. Cooldown bounds repeated clicks without another queue/table.
create or replace function public.retry_enrichment(job_id uuid)
returns boolean language sql security invoker set search_path = '' as $$
  with changed as (
    update public.enrichment_jobs
    set state = 'queued',
        stage = case when resolved_release_group_id is null then 'resolve_entity' else 'fetch_sources' end,
        retry_count = 0, last_error = null, source_errors = '{}',
        lease_id = null, lease_expires_at = null, updated_at = now()
    where id = job_id and (state = 'failed' or (state = 'ready' and cardinality(source_errors) > 0))
      and updated_at < now() - interval '10 seconds'
    returning id
  ) select exists(select 1 from changed);
$$;
revoke all on function public.retry_enrichment(uuid) from public, anon, authenticated;
grant execute on function public.retry_enrichment(uuid) to service_role;
