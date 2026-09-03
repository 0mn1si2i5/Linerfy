-- License pools: every review source now carries its license id and url, so
-- summaries and claims can be isolated by license compatibility. Two sources
-- may be summarized together only when they share the same license id (pool).

alter table public.source_policies add column if not exists license_id text;
alter table public.source_policies add column if not exists license_url text;

-- Backfill a safe default for any existing row; v1 adapters always set these.
update public.source_policies
  set license_id = 'proprietary',
      license_url = 'https://example.com/license'
  where license_id is null;

alter table public.source_policies alter column license_id set not null;
alter table public.source_policies alter column license_url set not null;
