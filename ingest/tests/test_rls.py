"""Minimal RLS integration tests for the public read boundary.

Opt-in: they run only when ``DATABASE_URL`` is set, and they exercise that
database directly. They prove the ``claim_sources`` / ``genre_sources`` policy:
anon sees a citation only when the cited document is published and belongs to
the same release as the citing genre or claim.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from linerfy_ingest.adapter import FixtureSourceAdapter
from linerfy_ingest.db import apply_migration, connect, seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; DB integration tests are opt-in",
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "reviews.json"


def _anon_count(query: str, params: tuple = ()) -> int:
    with connect() as conn:
        conn.execute("SET ROLE anon")
        return conn.execute(query, params).fetchone()[0]


@pytest.fixture(scope="module")
def rls_ids():
    """Apply migrations + seed, then insert a draft doc and a second release
    with cross-release citations, and hand back the ids the tests assert on."""
    with connect() as conn:
        apply_migration(conn)
        seed(conn, FixtureSourceAdapter(_FIXTURE).fetch())

        release_id = conn.execute(
            "SELECT id FROM public.releases WHERE slug = %s",
            ("norman-fucking-rockwell",),
        ).fetchone()[0]
        artist_id = conn.execute(
            "SELECT artist_id FROM public.releases WHERE id = %s",
            (release_id,),
        ).fetchone()[0]
        source_id = conn.execute(
            "SELECT id FROM public.review_sources WHERE slug = %s",
            ("pitchfork",),
        ).fetchone()[0]
        genre_id = conn.execute(
            "SELECT id FROM public.genres WHERE release_id = %s LIMIT 1",
            (release_id,),
        ).fetchone()[0]
        claim_id = conn.execute(
            "SELECT c.id FROM public.claims c "
            "JOIN public.summary_runs s ON s.id = c.summary_run_id "
            "WHERE s.release_id = %s LIMIT 1",
            (release_id,),
        ).fetchone()[0]

        draft_id = uuid.uuid5(uuid.NAMESPACE_URL, "linerfy-rls-test/draft-doc")
        second_release_id = uuid.uuid5(
            uuid.NAMESPACE_URL, "linerfy-rls-test/second-release"
        )
        second_doc_id = uuid.uuid5(
            uuid.NAMESPACE_URL, "linerfy-rls-test/second-doc"
        )

        # A draft document on the featured release, and a second (published)
        # release with its own document.
        conn.execute(
            "INSERT INTO public.review_documents "
            "(id, release_id, source_id, source_url, title, content_fingerprint, status, slug) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (
                draft_id,
                release_id,
                source_id,
                "https://example.com/rls-draft",
                "RLS Draft",
                "rls-test-draft",
                "draft",
                "rls-test-draft",
            ),
        )
        conn.execute(
            "INSERT INTO public.releases (id, artist_id, title, slug) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (
                second_release_id,
                artist_id,
                "RLS Second Release",
                "rls-test-second-release",
            ),
        )
        conn.execute(
            "INSERT INTO public.review_documents "
            "(id, release_id, source_id, source_url, title, content_fingerprint, status, slug) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (
                second_doc_id,
                second_release_id,
                source_id,
                "https://example.com/rls-second-doc",
                "RLS Second Doc",
                "rls-test-second-doc",
                "published",
                "rls-test-second-doc",
            ),
        )

        # Citations that anon must NOT see: a draft doc, and a cross-release doc.
        conn.execute(
            "INSERT INTO public.genre_sources (genre_id, document_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (genre_id, draft_id),
        )
        conn.execute(
            "INSERT INTO public.genre_sources (genre_id, document_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (genre_id, second_doc_id),
        )
        conn.execute(
            "INSERT INTO public.claim_sources (claim_id, document_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (claim_id, draft_id),
        )
        conn.execute(
            "INSERT INTO public.claim_sources (claim_id, document_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (claim_id, second_doc_id),
        )

    ids = {
        "genre_id": genre_id,
        "claim_id": claim_id,
        "draft_id": draft_id,
        "second_doc_id": second_doc_id,
        "second_release_id": second_release_id,
    }
    try:
        yield ids
    finally:
        with connect() as conn:
            conn.execute(
                "DELETE FROM public.review_documents WHERE id = %s",
                (draft_id,),
            )
            conn.execute(
                "DELETE FROM public.releases WHERE id = %s",
                (second_release_id,),
            )


def test_anon_reads_published_same_release_citations(rls_ids) -> None:
    # The fixture seeds two published genre_sources and two claim_sources.
    assert _anon_count("SELECT count(*) FROM public.genre_sources") >= 2
    assert _anon_count("SELECT count(*) FROM public.claim_sources") >= 2


def test_anon_cannot_read_a_draft_citation(rls_ids) -> None:
    assert (
        _anon_count(
            "SELECT count(*) FROM public.genre_sources "
            "WHERE genre_id = %s AND document_id = %s",
            (rls_ids["genre_id"], rls_ids["draft_id"]),
        )
        == 0
    )
    assert (
        _anon_count(
            "SELECT count(*) FROM public.claim_sources "
            "WHERE claim_id = %s AND document_id = %s",
            (rls_ids["claim_id"], rls_ids["draft_id"]),
        )
        == 0
    )


def test_anon_cannot_read_a_cross_release_citation(rls_ids) -> None:
    assert (
        _anon_count(
            "SELECT count(*) FROM public.genre_sources "
            "WHERE genre_id = %s AND document_id = %s",
            (rls_ids["genre_id"], rls_ids["second_doc_id"]),
        )
        == 0
    )
    assert (
        _anon_count(
            "SELECT count(*) FROM public.claim_sources "
            "WHERE claim_id = %s AND document_id = %s",
            (rls_ids["claim_id"], rls_ids["second_doc_id"]),
        )
        == 0
    )
