-- A durable, concurrency-safe budget ledger for real model calls.
--
-- The Vercel worker is serverless, so the local JSON file cannot be the
-- authority. Before a real call the worker atomically reserves a worst-case
-- cost against a 100 CNY cap; after the call it settles the actual usage and
-- releases the difference. Concurrent invocations can never jointly exceed the
-- cap because the reserve step takes a row lock on the running total.

create table if not exists public.model_usage_reservations (
  id uuid primary key default gen_random_uuid(),
  request_id text not null unique,
  job_id uuid,
  provider text not null,
  model text not null,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cache_read_tokens integer not null default 0,
  cache_write_tokens integer not null default 0,
  reserved_cny numeric not null,
  settled_cny numeric,
  status text not null default 'reserved'
    check (status in ('reserved', 'settled', 'expired')),
  created_at timestamptz not null default now(),
  settled_at timestamptz,
  expires_at timestamptz
);

create index if not exists model_reservations_status_idx
  on public.model_usage_reservations (status, expires_at);

-- A single-row running total that reserve/settle lock FOR UPDATE, so concurrent
-- invocations serialise and can never jointly exceed the cap.
create table if not exists public.model_budget (
  id integer primary key check (id = 1),
  committed_cny numeric not null default 0,
  reserved_cny numeric not null default 0
);
insert into public.model_budget (id, committed_cny, reserved_cny)
  values (1, 0, 0)
  on conflict (id) do nothing;

-- Server-only: anon/authenticated get no grants, and no RLS read policy.
alter table public.model_usage_reservations enable row level security;
alter table public.model_budget enable row level security;
revoke all on public.model_usage_reservations from anon, authenticated;
revoke all on public.model_budget from anon, authenticated;
