"""Load an ``IngestedContext`` into the Supabase catalog.

The pure transformations (``to_rows``) are covered by pytest; this module
exercises the real write path against a live database identified by
``DATABASE_URL``. Test-database setup (migration application, the Supabase role
and pg_cron stubs, and the test marker) lives in ``tests/_db_helpers.py``, not
here -- it is test infrastructure, not a product path.
"""

from __future__ import annotations

import os
import uuid

import psycopg

from .models import IngestedContext
from .seed import to_rows

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
