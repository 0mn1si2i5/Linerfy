create extension if not exists pgcrypto;

create table if not exists public.artists (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  sort_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.releases (
  id uuid primary key default gen_random_uuid(),
  artist_id uuid not null references public.artists(id) on delete cascade,
  title text not null,
  release_date date,
  artwork_url text,
  created_at timestamptz not null default now()
);

create table if not exists public.recordings (
  id uuid primary key default gen_random_uuid(),
  release_id uuid not null references public.releases(id) on delete cascade,
  title text not null,
  track_number integer check (track_number > 0),
  duration_ms integer check (duration_ms > 0),
  created_at timestamptz not null default now()
);

create table if not exists public.provider_identifiers (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null check (entity_type in ('artist', 'release', 'recording')),
  entity_id uuid not null,
  provider text not null,
  provider_id text not null,
  canonical_url text,
  unique (provider, provider_id),
  unique (entity_type, entity_id, provider)
);

create table if not exists public.review_sources (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  publication text not null,
  homepage_url text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.source_policies (
  source_id uuid primary key references public.review_sources(id) on delete cascade,
  crawl_allowed boolean not null default false,
  requests_per_minute integer not null check (requests_per_minute > 0),
  retention_days integer not null check (retention_days >= 0),
  excerpt_max_chars integer not null check (excerpt_max_chars between 1 and 1000),
  attribution_required boolean not null default true,
  removal_contact text not null,
  reviewed_at timestamptz not null default now()
);

create table if not exists public.review_documents (
  id uuid primary key default gen_random_uuid(),
  release_id uuid not null references public.releases(id) on delete cascade,
  source_id uuid not null references public.review_sources(id),
  source_url text not null unique,
  title text not null,
  author text,
  published_at date,
  score numeric,
  score_scale numeric,
  content_fingerprint text not null,
  fetched_at timestamptz not null default now(),
  status text not null default 'draft' check (status in ('draft', 'published', 'withdrawn'))
);

create table if not exists public.review_excerpts (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.review_documents(id) on delete cascade,
  excerpt text not null,
  is_paraphrase boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.summary_runs (
  id uuid primary key default gen_random_uuid(),
  release_id uuid not null references public.releases(id) on delete cascade,
  model text not null,
  prompt_version text not null,
  status text not null default 'draft' check (status in ('draft', 'published', 'superseded')),
  created_at timestamptz not null default now()
);

create table if not exists public.claims (
  id uuid primary key default gen_random_uuid(),
  summary_run_id uuid not null references public.summary_runs(id) on delete cascade,
  claim_order integer not null check (claim_order >= 0),
  claim_text text not null,
  unique (summary_run_id, claim_order)
);

create table if not exists public.claim_sources (
  claim_id uuid not null references public.claims(id) on delete cascade,
  document_id uuid not null references public.review_documents(id) on delete cascade,
  primary key (claim_id, document_id)
);

create index if not exists review_documents_release_status_idx
  on public.review_documents (release_id, status);
create index if not exists claims_summary_run_idx on public.claims (summary_run_id, claim_order);

alter table public.artists enable row level security;
alter table public.releases enable row level security;
alter table public.recordings enable row level security;
alter table public.provider_identifiers enable row level security;
alter table public.review_sources enable row level security;
alter table public.source_policies enable row level security;
alter table public.review_documents enable row level security;
alter table public.review_excerpts enable row level security;
alter table public.summary_runs enable row level security;
alter table public.claims enable row level security;
alter table public.claim_sources enable row level security;

drop policy if exists "published releases are public" on public.releases;
create policy "published releases are public" on public.releases for select
  to anon, authenticated using (
    exists (
      select 1 from public.review_documents d
      where d.release_id = releases.id and d.status = 'published'
    )
  );
drop policy if exists "artists with published releases are public" on public.artists;
create policy "artists with published releases are public" on public.artists for select
  to anon, authenticated using (
    exists (
      select 1 from public.releases r
      join public.review_documents d on d.release_id = r.id
      where r.artist_id = artists.id and d.status = 'published'
    )
  );
drop policy if exists "recordings on published releases are public" on public.recordings;
create policy "recordings on published releases are public" on public.recordings for select
  to anon, authenticated using (
    exists (
      select 1 from public.review_documents d
      where d.release_id = recordings.release_id and d.status = 'published'
    )
  );
drop policy if exists "published review documents are public" on public.review_documents;
create policy "published review documents are public" on public.review_documents for select
  to anon, authenticated using (status = 'published');
drop policy if exists "sources for published documents are public" on public.review_sources;
create policy "sources for published documents are public" on public.review_sources for select
  to anon, authenticated using (
    exists (
      select 1 from public.review_documents d
      where d.source_id = review_sources.id and d.status = 'published'
    )
  );
drop policy if exists "excerpts from published documents are public" on public.review_excerpts;
create policy "excerpts from published documents are public" on public.review_excerpts for select
  to anon, authenticated using (
    exists (
      select 1 from public.review_documents d
      where d.id = review_excerpts.document_id and d.status = 'published'
    )
  );
drop policy if exists "published summary runs are public" on public.summary_runs;
create policy "published summary runs are public" on public.summary_runs for select
  to anon, authenticated using (status = 'published');
drop policy if exists "claims from published runs are public" on public.claims;
create policy "claims from published runs are public" on public.claims for select
  to anon, authenticated using (
    exists (
      select 1 from public.summary_runs s
      where s.id = claims.summary_run_id and s.status = 'published'
    )
  );
drop policy if exists "citations from published runs are public" on public.claim_sources;
create policy "citations from published runs are public" on public.claim_sources for select
  to anon, authenticated using (
    exists (
      select 1 from public.claims c
      join public.summary_runs s on s.id = c.summary_run_id
      where c.id = claim_sources.claim_id and s.status = 'published'
    )
    and exists (
      select 1 from public.claims c
      join public.summary_runs s on s.id = c.summary_run_id
      join public.review_documents cited on cited.id = claim_sources.document_id
      where c.id = claim_sources.claim_id
        and cited.status = 'published'
        and cited.release_id = s.release_id
    )
  );

-- provider_identifiers and source_policies stay server-only.
