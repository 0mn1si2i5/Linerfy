-- Job input model: carry the minimal now-playing request metadata and the
-- resolution outcome, instead of relying on an ambiguous entity_id alone.
--
-- `entity_id` remains the job's dedup key and now holds the request
-- fingerprint (see request.py). `payload` holds the bounded, untrusted
-- metadata; `resolved_release_group_id` and `resolution_status` are filled by
-- the resolve_entity stage.

alter table public.enrichment_jobs add column if not exists payload jsonb not null default '{}'::jsonb;
alter table public.enrichment_jobs add column if not exists resolved_release_group_id text;
alter table public.enrichment_jobs add column if not exists resolution_status text not null default 'pending'
  check (resolution_status in ('pending', 'resolved', 'ambiguous', 'unavailable'));
