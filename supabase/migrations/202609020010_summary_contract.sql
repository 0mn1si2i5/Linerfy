-- The license-pool public contract for summaries.
--
-- A summary run is now either a per-source summary (`summary_kind = 'source'`,
-- `source_id` set) or a consensus block (`summary_kind = 'consensus'`, pooled by
-- `license_pool`). Both carry the license and attribution so the public context
-- can show them, plus an explicit `skipped_reason` for a consensus that was
-- legitimately not generated (fewer than two distinct sources in the pool).

alter table public.summary_runs
  add column if not exists summary_kind text not null default 'source'
    check (summary_kind in ('source', 'consensus')),
  add column if not exists license_pool text not null default '',
  add column if not exists license_url text not null default '',
  add column if not exists source_id text,
  add column if not exists attribution text not null default '',
  add column if not exists ai_modified boolean not null default true,
  add column if not exists skipped_reason text;

-- The publish stage builds candidates and atomically promotes them; the old
-- inline check lacks the candidate state.
alter table public.summary_runs drop constraint if exists summary_runs_status_check;
alter table public.summary_runs add constraint summary_runs_status_check
  check (status in ('draft', 'candidate', 'published', 'superseded'));

create index if not exists summary_runs_release_kind_idx
  on public.summary_runs (release_id, summary_kind, status);
