-- Auth boundary: remove anonymous catalog reads.
--
-- v1 reads are authenticated only. The catalog is no longer visible to the
-- `anon` role through PostgREST: every public read policy is narrowed from
-- `to anon, authenticated` to `to authenticated`, and the `anon` SELECT grant
-- is revoked as defense in depth.
--
-- The numeric GitHub id whitelist is enforced at the API layer (a Vercel env
-- var), not here: RLS cannot read process environment. This migration only
-- guarantees that no unauthenticated request reaches a catalog row.

-- Narrow every public read policy to authenticated only.
alter policy "published releases are public" on public.releases to authenticated;
alter policy "artists with published releases are public" on public.artists to authenticated;
alter policy "recordings on published releases are public" on public.recordings to authenticated;
alter policy "published review documents are public" on public.review_documents to authenticated;
alter policy "sources for published documents are public" on public.review_sources to authenticated;
alter policy "excerpts from published documents are public" on public.review_excerpts to authenticated;
alter policy "published summary runs are public" on public.summary_runs to authenticated;
alter policy "claims from published runs are public" on public.claims to authenticated;
alter policy "citations from published runs are public" on public.claim_sources to authenticated;
alter policy "genres on published releases are public" on public.genres to authenticated;
alter policy "genre citations on published releases are public" on public.genre_sources to authenticated;

-- Revoke the anon SELECT grant outright so even a policy regression cannot
-- expose catalog rows to an unauthenticated client.
revoke select on public.artists from anon;
revoke select on public.releases from anon;
revoke select on public.recordings from anon;
revoke select on public.review_sources from anon;
revoke select on public.review_documents from anon;
revoke select on public.review_excerpts from anon;
revoke select on public.summary_runs from anon;
revoke select on public.claims from anon;
revoke select on public.claim_sources from anon;
revoke select on public.genres from anon;
revoke select on public.genre_sources from anon;
