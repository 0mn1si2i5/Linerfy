"""Shared helpers for the opt-in database integration tests.

Every helper uses uniquely-named test entities so a test can never touch a real
release such as Norman Fucking Rockwell!. ``cleanup`` removes everything a test
created, children first via the foreign-key cascade.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from linerfy_ingest.db import is_test_db

# A namespace distinct from the ingest ``stable_uuid`` namespace, so test ids can
# never collide with a real entity's id even if the slugs happen to match.
_NAMESPACE = uuid.UUID("8f1d3c9b-2a4e-4b7e-9d0c-5f6a7b8c9d0e")


def tid(slug: str) -> uuid.UUID:
    """Deterministic test-only uuid, outside the ingest ``stable_uuid`` namespace."""
    return uuid.uuid5(_NAMESPACE, f"linerfy-dbtest:{slug}")


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
