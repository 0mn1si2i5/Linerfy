-- Persist canonical entity slugs so clients can address releases/artists, and
-- store the source-backed genre tags the public context requires.

alter table public.artists add column if not exists slug text;
alter table public.releases add column if not exists slug text;
alter table public.review_documents add column if not exists slug text;

create unique index if not exists artists_slug_idx on public.artists (slug);
create unique index if not exists releases_slug_idx on public.releases (slug);
create unique index if not exists review_documents_slug_idx on public.review_documents (slug);

alter table public.summary_runs add column if not exists locale text not null default 'en';
alter table public.summary_runs add column if not exists corpus_hash text not null default '';
alter table public.summary_runs add column if not exists generated_at timestamptz not null default now();

create table if not exists public.genres (
  id uuid primary key default gen_random_uuid(),
  release_id uuid not null references public.releases(id) on delete cascade,
  name text not null,
  unique (release_id, name)
);

create table if not exists public.genre_sources (
  genre_id uuid not null references public.genres(id) on delete cascade,
  document_id uuid not null references public.review_documents(id) on delete cascade,
  primary key (genre_id, document_id)
);

alter table public.genres enable row level security;
alter table public.genre_sources enable row level security;

drop policy if exists "genres on published releases are public" on public.genres;
create policy "genres on published releases are public" on public.genres for select
  to anon, authenticated using (
    exists (
      select 1 from public.review_documents d
      where d.release_id = genres.release_id and d.status = 'published'
    )
  );

drop policy if exists "genre citations on published releases are public" on public.genre_sources;
create policy "genre citations on published releases are public" on public.genre_sources for select
  to anon, authenticated using (
    exists (
      select 1 from public.genres g
      join public.review_documents d on d.release_id = g.release_id
      where g.id = genre_sources.genre_id and d.status = 'published'
    )
    and exists (
      select 1 from public.genres g
      join public.review_documents cited on cited.id = genre_sources.document_id
      where g.id = genre_sources.genre_id
        and cited.status = 'published'
        and cited.release_id = g.release_id
    )
  );

-- Slugs are canonical identifiers: non-null and unique.
alter table public.artists alter column slug set not null;
alter table public.releases alter column slug set not null;
alter table public.review_documents alter column slug set not null;

-- Tighten privileges: public reads need only SELECT. Remove any broader grants
-- so no client role can write catalog tables through PostgREST, independent of
-- row-level security. (provider_identifiers and source_policies stay server-only
-- and are granted nothing here.)
revoke all on public.artists from anon, authenticated;
grant select on public.artists to anon, authenticated;
revoke all on public.releases from anon, authenticated;
grant select on public.releases to anon, authenticated;
revoke all on public.recordings from anon, authenticated;
grant select on public.recordings to anon, authenticated;
revoke all on public.review_sources from anon, authenticated;
grant select on public.review_sources to anon, authenticated;
revoke all on public.review_documents from anon, authenticated;
grant select on public.review_documents to anon, authenticated;
revoke all on public.review_excerpts from anon, authenticated;
grant select on public.review_excerpts to anon, authenticated;
revoke all on public.summary_runs from anon, authenticated;
grant select on public.summary_runs to anon, authenticated;
revoke all on public.claims from anon, authenticated;
grant select on public.claims to anon, authenticated;
revoke all on public.claim_sources from anon, authenticated;
grant select on public.claim_sources to anon, authenticated;
revoke all on public.genres from anon, authenticated;
grant select on public.genres to anon, authenticated;
revoke all on public.genre_sources from anon, authenticated;
grant select on public.genre_sources to anon, authenticated;
