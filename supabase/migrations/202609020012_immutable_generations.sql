-- Immutable summary generations.
--
-- A summary run is now an append-only generation. Each scope (a per-source
-- summary or a per-license-pool consensus) accumulates generations over time;
-- only one is "current published" at a time, and older published generations
-- are superseded rather than overwritten in place. A failed generation never
-- reaches the public read path.

alter table public.summary_runs add column if not exists scope text not null default '';
alter table public.summary_runs add column if not exists published_at timestamptz;

-- Legacy draft/candidate/failed states remain valid for existing rows. Current
-- workers insert only a fully validated published generation.
alter table public.summary_runs drop constraint if exists summary_runs_status_check;
alter table public.summary_runs add constraint summary_runs_status_check
  check (status in ('draft', 'candidate', 'published', 'superseded', 'failed'));

-- At most one current published generation per (release, scope).
create unique index if not exists summary_runs_current_published_idx
  on public.summary_runs (release_id, scope) where status = 'published';
