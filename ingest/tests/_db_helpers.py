"""Shared helpers for the opt-in database integration tests.

Every helper uses uniquely-named test entities so a test can never touch a real
release such as Norman Fucking Rockwell!. ``cleanup`` removes everything a test
created, children first via the foreign-key cascade.

The test-database setup (migration application, the Supabase role and pg_cron
stubs, and the marker) also lives here rather than in the product ``db`` module:
a plain local Postgres is an optional verification environment, not a product
component.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
import pytest

_MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

_NAMESPACE = uuid.UUID("8f1d3c9b-2a4e-4b7e-9d0c-5f6a7b8c9d0e")

# The dedicated test database is identified by this marker table, which only the
# prep step creates. The production catalog never has it, so an integration test
# can prove it is talking to a throwaway test database instead of real data.
_TEST_MARKER_TABLE = "_linerfy_test_marker"
_TEST_MARKER_VALUE = "test-database"


def tid(slug: str) -> uuid.UUID:
    """Deterministic test-only uuid, outside the ingest ``stable_uuid`` namespace."""
    return uuid.uuid5(_NAMESPACE, f"linerfy-dbtest:{slug}")


def _reset_permitted(host: str) -> bool:
    """Reset is allowed only for a local or explicitly-marked test database."""
    local = host in {"localhost", "127.0.0.1", "::1"}
    marked = os.environ.get("LINERFY_RESET_ALLOWED") == "1"
    return local or marked


def require_test_db(conn: psycopg.Connection) -> None:
    """Refuse destructive or test-only writes against an unmarked remote DB."""
    host = conn.info.host or ""
    if not _reset_permitted(host):
        raise RuntimeError(
            "refusing to write: target host is not a marked local/test database; "
            "set LINERFY_RESET_ALLOWED=1 inline for this one command only"
        )


def apply_migration(conn: psycopg.Connection) -> None:
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        conn.execute(path.read_text(encoding="utf-8"))


def reset(conn: psycopg.Connection) -> None:
    """Drop catalog tables so a fresh migrate + seed is deterministic."""
    require_test_db(conn)
    drop_order = [
        "claim_sources",
        "claims",
        "summary_runs",
        "genre_sources",
        "review_excerpts",
        "review_document_bodies",
        "review_documents",
        "genres",
        "source_policies",
        "review_sources",
        "provider_identifiers",
        "recordings",
        "releases",
        "artists",
    ]
    for table in drop_order:
        conn.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")


def is_test_db(conn: psycopg.Connection) -> bool:
    """True when the connected database carries the dedicated-test marker."""
    table = conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (_TEST_MARKER_TABLE,),
    ).fetchone()
    if not table:
        return False
    return (
        conn.execute(
            f"SELECT 1 FROM public.{_TEST_MARKER_TABLE} WHERE marker = %s",
            (_TEST_MARKER_VALUE,),
        ).fetchone()
        is not None
    )


def prepare_test_db(conn: psycopg.Connection) -> None:
    """Prepare a dedicated test database: create the Supabase roles, apply the
    catalog migration, and mark it. Run against a throwaway database only."""
    require_test_db(conn)
    # The migrations assume Supabase's three roles exist (RLS policies and
    # grants name `anon`/`authenticated`); a plain Postgres test database must
    # create them before the migrations are applied.
    for role in ("anon", "authenticated", "service_role"):
        conn.execute(
            "DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN "
            f"CREATE ROLE {role}; "
            "END IF; END $$"
        )
    # pg_cron is a Supabase-managed extension absent from plain Postgres; the
    # worker-cron migration calls `cron.unschedule`/`cron.schedule`. Provide
    # no-op stubs so the migration applies.
    conn.execute("CREATE SCHEMA IF NOT EXISTS cron")
    conn.execute(
        "CREATE OR REPLACE FUNCTION cron.unschedule(job_name text) "
        "RETURNS boolean LANGUAGE sql AS $$ SELECT false $$"
    )
    conn.execute(
        "CREATE OR REPLACE FUNCTION cron.schedule(job_name text, schedule text, command text) "
        "RETURNS bigint LANGUAGE sql AS $$ SELECT 0 $$"
    )
    apply_migration(conn)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS public.{_TEST_MARKER_TABLE} "
        "(marker text primary key)"
    )
    conn.execute(
        f"INSERT INTO public.{_TEST_MARKER_TABLE} (marker) VALUES (%s) "
        "ON CONFLICT (marker) DO NOTHING",
        (_TEST_MARKER_VALUE,),
    )


def skip_unless_test_db(conn: psycopg.Connection) -> None:
    """Skip unless the connected database is the marked dedicated test database.

    This is the last line of defence before any write: it proves the target was
    prepared with ``prepare_test_db``, so a stray ``DATABASE_URL`` pointing at
    the production catalog can never be written to by a test.
    """
    if not is_test_db(conn):
        pytest.skip(
            "connected database is not the marked test database; "
            "run prepare_test_db against a dedicated test DB first"
        )


def cleanup(
    conn: psycopg.Connection, *, artist_id: uuid.UUID, source_id: uuid.UUID
) -> None:
    """Remove a test artist (cascades to its releases, documents, genres and
    summaries) and then the test source, which is only then unreferenced."""
    conn.execute("DELETE FROM public.artists WHERE id = %s", (artist_id,))
    conn.execute("DELETE FROM public.review_sources WHERE id = %s", (source_id,))
