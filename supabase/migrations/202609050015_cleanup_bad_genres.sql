-- Controlled, idempotent cleanup of provenance tags that were written as genres
-- before the MusicBrainz tag filter existed (languages, regions, eras, release
-- formats, and chart positions such as "English" and "1–4 Wochen").
--
-- Re-enqueues the affected ready jobs so the worker re-seeds a corrected genre
-- list, then deletes the bad genre rows (their genre_sources citations cascade
-- away). Idempotent: a re-enqueued job leaves the 'ready' state, and the deletes
-- are a no-op once the bad rows are gone, so re-running neither loops nor
-- duplicates.

-- 1. Re-enqueue ready jobs whose release still has a bad genre. This runs before
--    the delete so the "has a bad genre" condition still holds.
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
    join public.genres g on g.release_id = r.id
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
      and (
        lower(trim(g.name)) in (
          -- languages
          'english', 'german', 'french', 'spanish', 'italian', 'portuguese',
          'japanese', 'korean', 'chinese', 'russian', 'dutch', 'swedish',
          'norwegian', 'danish', 'finnish', 'polish', 'turkish', 'arabic',
          'hindi', 'ukrainian',
          -- countries / nationalities
          'united states', 'usa', 'us', 'uk', 'united kingdom', 'canada',
          'australia', 'germany', 'france', 'italy', 'japan', 'britain',
          'british', 'american', 'america', 'ireland', 'irish', 'australian',
          'canadian', 'europe',
          -- release formats / versions
          'album', 'single', 'ep', 'compilation', 'mixtape', 'remix'
        )
        or trim(g.name) ~ '^\d{4}$'
        or trim(g.name) ~ '^\d{4}s$'
        or trim(g.name) ~ '^\d{2}s$'
        or trim(g.name) ~ '^\d+\s*[-–—]\s*\d+'
      )
  );

-- 2. Delete the bad genre rows; genre_sources cascade.
delete from public.genres g
where lower(trim(g.name)) in (
    'english', 'german', 'french', 'spanish', 'italian', 'portuguese',
    'japanese', 'korean', 'chinese', 'russian', 'dutch', 'swedish',
    'norwegian', 'danish', 'finnish', 'polish', 'turkish', 'arabic',
    'hindi', 'ukrainian',
    'united states', 'usa', 'us', 'uk', 'united kingdom', 'canada',
    'australia', 'germany', 'france', 'italy', 'japan', 'britain',
    'british', 'american', 'america', 'ireland', 'irish', 'australian',
    'canadian', 'europe',
    'album', 'single', 'ep', 'compilation', 'mixtape', 'remix'
  )
  or trim(g.name) ~ '^\d{4}$'
  or trim(g.name) ~ '^\d{4}s$'
  or trim(g.name) ~ '^\d{2}s$'
  or trim(g.name) ~ '^\d+\s*[-–—]\s*\d+';
