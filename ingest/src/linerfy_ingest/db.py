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


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def _reset_permitted(host: str) -> bool:
    """Reset is allowed only for a local or explicitly-marked test database."""
    local = host in {"localhost", "127.0.0.1", "::1"}
    marked = os.environ.get("LINERFY_RESET_ALLOWED") == "1"
    return local or marked


def reset(conn: psycopg.Connection) -> None:
    """Drop catalog tables so a fresh migrate + seed is deterministic.

    Refuses to run unless the target is a local database or has been explicitly
    marked as a test database, so the default command can never destroy tables.
    For a remote test database, set LINERFY_RESET_ALLOWED=1 inline on the reset
    command only -- do not persist it.
    """
    host = conn.info.host or ""
    if not _reset_permitted(host):
        raise RuntimeError(
            "refusing to reset: target host is not a marked local/test database; "
            "set LINERFY_RESET_ALLOWED=1 inline for this one command only"
        )
    for table in _DROP_ORDER:
        conn.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")


def apply_migration(conn: psycopg.Connection) -> None:
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        conn.execute(path.read_text(encoding="utf-8"))


def _is_uuid_column(name: str) -> bool:
    return name == "id" or name.endswith("_id")


def _db_value(name: str, value: object) -> object:
    if value is None:
        return None
    if _is_uuid_column(name):
        return uuid.UUID(value)
    return value


def seed(conn: psycopg.Connection, context: IngestedContext) -> int:
    rows = to_rows(context)
    written = 0
    for table in _TABLE_ORDER:
        table_rows = rows[table]
        if not table_rows:
            continue
        columns = list(table_rows[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        primary_keys = _PRIMARY_KEYS[table]
        update_columns = [column for column in columns if column not in primary_keys]
        if update_columns:
            on_conflict = (
                f"ON CONFLICT ({', '.join(primary_keys)}) DO UPDATE SET "
                + ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
            )
        else:
            on_conflict = "ON CONFLICT DO NOTHING"
        statement = (
            f"INSERT INTO public.{table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) {on_conflict}"
        )
        for row in table_rows:
            values = [_db_value(column, row[column]) for column in columns]
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
