-- Clean up provenance tags that were written as genres before the fetch stage
-- switched from the MusicBrainz user-tag folksonomy to the curated `genres`
-- list. The earlier 015 cleanup removed these once, but the old code re-wrote
-- them on subsequent re-fetches; 017 re-runs the same delete and adds site /
-- placeholder names 015 never covered (e.g. "laut.de", "ph_temp_checken").
--
-- This only deletes genre rows (their genre_sources citations cascade); it
-- never touches ratings, review documents, or summaries. Idempotent: once the
-- bad rows are gone, re-running is a no-op. Apply after the new fetch code is
-- deployed so nothing re-pollutes.

delete from public.genres g
where not exists (select 1 from public.genre_sources gs where gs.genre_id = g.id)
and (lower(trim(g.name)) in (
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
    'album', 'single', 'ep', 'compilation', 'mixtape', 'remix',
    -- external site names / placeholders observed in the catalog
    'laut.de', 'ph_temp_checken', '5+ wochen', 'me 26–01'
  )
  or trim(g.name) ~ '^\d{4}$'
  or trim(g.name) ~ '^\d{4}s$'
  or trim(g.name) ~ '^\d{2}s$'
  or trim(g.name) ~ '^\d+\s*[-–—]\s*\d+');
