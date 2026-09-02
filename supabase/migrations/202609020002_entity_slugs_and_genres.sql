-- Persist canonical entity slugs so clients can address releases/artists, and
-- store the source-backed genre tags the public context requires.

alter table public.artists add column slug text unique;
alter table public.releases add column slug text unique;
alter table public.review_documents add column slug text unique;

alter table public.summary_runs add column locale text not null default 'en';
alter table public.summary_runs add column corpus_hash text not null default '';
alter table public.summary_runs add column generated_at timestamptz not null default now();

create table public.genres (
  id uuid primary key default gen_random_uuid(),
  release_id uuid not null references public.releases(id) on delete cascade,
  name text not null,
  unique (release_id, name)
);

create table public.genre_sources (
  genre_id uuid not null references public.genres(id) on delete cascade,
  document_id uuid not null references public.review_documents(id) on delete cascade,
  primary key (genre_id, document_id)
);

alter table public.genres enable row level security;
alter table public.genre_sources enable row level security;

create policy "genres on published releases are public" on public.genres for select
  to anon, authenticated using (
    exists (
      select 1 from public.review_documents d
      where d.release_id = genres.release_id and d.status = 'published'
    )
  );

create policy "genre citations on published releases are public" on public.genre_sources for select
  to anon, authenticated using (
    exists (
      select 1 from public.genres g
      join public.review_documents d on d.release_id = g.release_id
      where g.id = genre_sources.genre_id and d.status = 'published'
    )
  );
