-- Controlled, idempotent backfill: re-enqueue ready jobs whose release was
-- published without genres (jobs completed before the worker began seeding
-- MusicBrainz genres in the fetch_sources stage). Re-running is a no-op: a
-- re-enqueued job leaves the 'ready' state, and the worker re-seeds genres from
-- the release group as it re-runs the pipeline.
--
-- The release slug is recomputed from the job payload exactly as the ingest
-- pipeline does (casefold -> [^a-z0-9]+ -> '-' -> strip '-'), so the join is
-- deterministic and never touches unrelated releases. The rare non-ASCII
-- casefold difference (e.g. 'ß') only under-matches, never over-matches.
--
-- Re-enqueue from resolve_entity (not fetch_sources) so each job re-enters the
-- pipeline through the same predictable path as a fresh request; the one extra
-- MusicBrainz resolve per job is negligible for this bounded set.

do $$
declare affected_rows integer;
begin
  update public.enrichment_jobs j
  set
    state = 'queued',
    stage = 'resolve_entity',
    retry_count = 0,
    last_error = null,
    updated_at = now()
  where j.state = 'ready'
    and exists (
      select 1
      from public.releases r
      where r.slug = (
          coalesce(
            nullif(
              btrim(
                regexp_replace(lower(j.payload ->> 'artist'), '[^a-z0-9]+', '-', 'g'),
                '-'
              ),
              ''
            ),
            'unknown'
          )
          || '-' ||
          coalesce(
            nullif(
              btrim(
                regexp_replace(lower(j.payload ->> 'album'), '[^a-z0-9]+', '-', 'g'),
                '-'
              ),
              ''
            ),
            'unknown'
          )
        )
        and not exists (
          select 1 from public.genres g where g.release_id = r.id
        )
    );

  get diagnostics affected_rows = row_count;
  raise notice 'backfill_missing_genres: re-enqueued % ready job(s)', affected_rows;
end $$;
