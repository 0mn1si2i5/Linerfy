-- Private storage for review full text. The body is fetched to produce
-- summaries and excerpts, but it never enters the public read path: no SELECT
-- grant and no RLS policy means anon/authenticated cannot read it.

create table if not exists public.review_document_bodies (
  document_id uuid primary key references public.review_documents(id) on delete cascade,
  content text not null
);

alter table public.review_document_bodies enable row level security;

revoke all on public.review_document_bodies from anon, authenticated;
