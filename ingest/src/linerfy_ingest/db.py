"""Apply the catalog migration and load an IngestedContext into Supabase.

The pure transformations (`to_rows`, `to_public`) are covered by pytest; this
module exercises the real write path against a live database identified by
`DATABASE_URL`. It is run as a one-shot loader rather than unit-tested.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg

from .models import IngestedContext
from .seed import to_rows

_MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"

# Insertion order respects foreign keys (parents before children).
_TABLE_ORDER = [
    "artists",
    "releases",
    "genres",
    "review_sources",
    "source_policies",
    "review_documents",
    "review_document_bodies",
    "review_excerpts",
    "genre_sources",
    "summary_runs",
    "claims",
    "claim_sources",
]

# Every table the migrations create, children first, for a clean re-seed.
_DROP_ORDER = [
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

# Primary key columns per table, so a seed can upsert deterministically: the
# same canonical slug always maps to the same row, and re-seeding with real data
# replaces an earlier hand-authored placeholder instead of leaving it behind.
_PRIMARY_KEYS = {
    "artists": ["id"],
    "releases": ["id"],
    "genres": ["id"],
    "review_sources": ["id"],
    "source_policies": ["source_id"],
    "review_documents": ["id"],
    "review_document_bodies": ["document_id"],
    "review_excerpts": ["id"],
    "genre_sources": ["genre_id", "document_id"],
    "summary_runs": ["id"],
    "claims": ["id"],
    "claim_sources": ["claim_id", "document_id"],
}


def connect(*, autocommit: bool = True) -> psycopg.Connection:
    """Open a connection. Default is autocommit (one statement == one commit),
    used by the read path and one-shot seeding. Pass ``autocommit=False`` when a
    caller must control commit/rollback itself (e.g. an atomic summary write)."""
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=autocommit)


def _reset_permitted(host: str) -> bool:
    """Reset is allowed only for a local or explicitly-marked test database."""
    local = host in {"localhost", "127.0.0.1", "::1"}
    marked = os.environ.get("LINERFY_RESET_ALLOWED") == "1"
    return local or marked


def require_test_db(conn: psycopg.Connection) -> None:
    """Refuse destructive or test-only writes against an unmarked remote DB.

    Local databases and those explicitly marked with ``LINERFY_RESET_ALLOWED=1``
    are the only targets that may be reset or loaded with the fixture; the real
    catalog is always remote and therefore always refused.
    """
    host = conn.info.host or ""
    if not _reset_permitted(host):
        raise RuntimeError(
            "refusing to write: target host is not a marked local/test database; "
            "set LINERFY_RESET_ALLOWED=1 inline for this one command only"
        )


def reset(conn: psycopg.Connection) -> None:
    """Drop catalog tables so a fresh migrate + seed is deterministic.

    Refuses to run unless the target is a local database or has been explicitly
    marked as a test database, so the default command can never destroy tables.
    For a remote test database, set LINERFY_RESET_ALLOWED=1 inline on the reset
    command only -- do not persist it.
    """
    require_test_db(conn)
    for table in _DROP_ORDER:
        conn.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")


def apply_migration(conn: psycopg.Connection) -> None:
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        conn.execute(path.read_text(encoding="utf-8"))


# The dedicated test database is identified by this marker table, which only the
# prep step creates. The production catalog never has it, so an integration test
# can prove it is talking to a throwaway test database instead of real data.
_TEST_MARKER_TABLE = "_linerfy_test_marker"
_TEST_MARKER_VALUE = "test-database"


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
    catalog migration, and mark it.

    Run this once, manually, against a throwaway/test database -- never against
    the production catalog (guarded the same way as ``reset``).
    """
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
    # no-op stubs so the migration applies (the schedule itself is a no-op here
    # and is only ever exercised on Supabase).
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


# The columns that are genuinely uuid-typed, per table. ``source_id`` is a uuid
# foreign key on documents/policies but a *text* slug on summary_runs, and
# ``license_id`` is a text slug on policies -- a naive ``endswith("_id")`` would
# coerce those to uuid and break the seed. This map is the precise source of truth.
_UUID_COLUMNS: dict[str, set[str]] = {
    "artists": {"id"},
    "releases": {"id", "artist_id"},
    "genres": {"id", "release_id"},
    "review_sources": {"id"},
    "source_policies": {"source_id"},
    "review_documents": {"id", "release_id", "source_id"},
    "review_document_bodies": {"document_id"},
    "review_excerpts": {"id", "document_id"},
    "genre_sources": {"genre_id", "document_id"},
    "summary_runs": {"id", "release_id"},
    "claims": {"id", "summary_run_id"},
    "claim_sources": {"claim_id", "document_id"},
}


def _db_value(table: str, name: str, value: object) -> object:
    if value is None:
        return None
    if name in _UUID_COLUMNS.get(table, set()):
        return uuid.UUID(value)
    return value


def _release_present(conn: psycopg.Connection, rows: dict[str, list[dict]]) -> bool:
    """True when the context's release already has a row, so a bootstrap-only
    (``overwrite=False``) seed should write nothing."""
    release_rows = rows["releases"]
    if not release_rows:
        return False
    release_id = uuid.UUID(release_rows[0]["id"])
    return (
        conn.execute("SELECT 1 FROM public.releases WHERE id = %s", (release_id,)).fetchone()
        is not None
    )


def seed(
    conn: psycopg.Connection, context: IngestedContext, *, overwrite: bool = True
) -> int:
    """Load a context into the catalog.

    ``overwrite=True`` (real adapters) upserts, so a later fetch with real data
    replaces an earlier placeholder. ``overwrite=False`` (the fixture) is a
    bootstrap-only write: if the release is already present it writes nothing at
    all, so it can neither overwrite nor extend a record that already exists --
    the hand-authored fixture stays a pure contract check.
    """
    rows = to_rows(context)
    if not overwrite and _release_present(conn, rows):
        return 0
    written = 0
    for table in _TABLE_ORDER:
        table_rows = rows[table]
        if not table_rows:
            continue
        columns = list(table_rows[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        if not overwrite:
            on_conflict = "ON CONFLICT DO NOTHING"
        else:
            primary_keys = _PRIMARY_KEYS[table]
            update_columns = [
                column for column in columns if column not in primary_keys
            ]
            if update_columns:
                on_conflict = (
                    f"ON CONFLICT ({', '.join(primary_keys)}) DO UPDATE SET "
                    + ", ".join(
                        f"{column} = EXCLUDED.{column}" for column in update_columns
                    )
                )
            else:
                on_conflict = "ON CONFLICT DO NOTHING"
        statement = (
            f"INSERT INTO public.{table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) {on_conflict}"
        )
        for row in table_rows:
            values = [_db_value(table, column, row[column]) for column in columns]
            cursor = conn.execute(statement, values)
            written += cursor.rowcount
    return written


def verify() -> dict:
    """Read back the seeded rows and confirm row-level security boundaries."""
    report: dict = {}
    with connect() as conn:
        report["counts"] = {
            table: conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0]
            for table in _TABLE_ORDER
        }
        report["documents"] = conn.execute(
            "SELECT title, author, score, score_scale "
            "FROM public.review_documents ORDER BY title"
        ).fetchall()

        conn.execute("SET ROLE anon")
        report["anon_review_documents"] = conn.execute(
            "SELECT count(*) FROM public.review_documents"
        ).fetchone()[0]
        report["anon_source_policies"] = conn.execute(
            "SELECT count(*) FROM public.source_policies"
        ).fetchone()[0]
        try:
            report["anon_review_document_bodies"] = conn.execute(
                "SELECT count(*) FROM public.review_document_bodies"
            ).fetchone()[0]
        except psycopg.errors.InsufficientPrivilege:
            report["anon_review_document_bodies"] = "denied"
        conn.execute("RESET ROLE")
    return report
