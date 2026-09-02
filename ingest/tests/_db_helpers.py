"""Shared helpers for the opt-in database integration tests.

Every helper uses uniquely-named test entities so a test can never touch a real
release such as Norman Fucking Rockwell!. ``cleanup`` removes everything a test
created, children first via the foreign-key cascade.
"""

from __future__ import annotations

import uuid

import psycopg

# A namespace distinct from the ingest ``stable_uuid`` namespace, so test ids can
# never collide with a real entity's id even if the slugs happen to match.
_NAMESPACE = uuid.UUID("8f1d3c9b-2a4e-4b7e-9d0c-5f6a7b8c9d0e")


def tid(slug: str) -> uuid.UUID:
    """Deterministic test-only uuid, outside the ingest ``stable_uuid`` namespace."""
    return uuid.uuid5(_NAMESPACE, f"linerfy-dbtest:{slug}")


def cleanup(
    conn: psycopg.Connection, *, artist_id: uuid.UUID, source_id: uuid.UUID
) -> None:
    """Remove a test artist (cascades to its releases, documents, genres and
    summaries) and then the test source, which is only then unreferenced."""
    conn.execute("DELETE FROM public.artists WHERE id = %s", (artist_id,))
    conn.execute("DELETE FROM public.review_sources WHERE id = %s", (source_id,))
