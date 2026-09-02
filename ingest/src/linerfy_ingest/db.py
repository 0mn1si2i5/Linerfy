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
    "review_documents",
    "genres",
    "source_policies",
    "review_sources",
    "provider_identifiers",
    "recordings",
    "releases",
    "artists",
]


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def reset(conn: psycopg.Connection) -> None:
    """Drop catalog tables so a fresh migrate + seed is deterministic."""
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
    inserted = 0
    for table in _TABLE_ORDER:
        table_rows = rows[table]
        if not table_rows:
            continue
        columns = list(table_rows[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        statement = (
            f"INSERT INTO public.{table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        )
        for row in table_rows:
            values = [_db_value(column, row[column]) for column in columns]
            conn.execute(statement, values)
            inserted += 1
    return inserted


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
        conn.execute("RESET ROLE")
    return report
