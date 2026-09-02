"""Database integration tests for summary atomicity and insert-only seeding.

Opt-in and gated: they run only when both ``DATABASE_URL`` and
``LINERFY_DB_TESTS_ALLOWED=1`` are set, and then only against a database marked
with ``prepare_test_db``. Every entity is uniquely named and cleaned up, so a
real release such as Norman Fucking Rockwell! is never read or written.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from _db_helpers import cleanup, skip_unless_test_db

from linerfy_ingest.db import connect, seed
from linerfy_ingest.models import (
    ArtistEntity,
    CitedClaim,
    IngestedContext,
    ReleaseEntity,
    ReviewDocument,
    ReviewSource,
    SourcePolicy,
    Summary,
)
from linerfy_ingest.seed import stable_uuid
from linerfy_ingest.summarize import write_summary

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)


def _sid(kind: str, slug: str) -> uuid.UUID:
    return uuid.UUID(stable_uuid(kind, slug))


def _summary(claims: list[tuple[str, list[str]]]) -> Summary:
    return Summary(
        locale="zh-CN",
        model="test-model",
        prompt_version="test-v1",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        corpus_hash="test-corpus",
        claims=[CitedClaim(text=text, source_ids=sources) for text, sources in claims],
    )


def _insert_atomic_catalog(conn) -> dict:
    ids = {
        "artist": _sid("artist", "atomic-artist"),
        "release": _sid("release", "atomic-release"),
        "source": _sid("source", "atomic-source"),
    }
    conn.execute(
        "INSERT INTO public.artists (id, slug, name) VALUES (%s,%s,%s)",
        (ids["artist"], "atomic-artist", "Atomic Artist"),
    )
    conn.execute(
        "INSERT INTO public.releases (id, slug, artist_id, title) VALUES (%s,%s,%s,%s)",
        (ids["release"], "atomic-release", ids["artist"], "Atomic Release"),
    )
    conn.execute(
        "INSERT INTO public.review_sources "
        "(id, slug, publication, homepage_url) VALUES (%s,%s,%s,%s)",
        (ids["source"], "atomic-source", "Atomic Source", "https://example.com"),
    )
    for i in ("a", "b", "c"):
        slug = f"atomic-doc-{i}"
        conn.execute(
            "INSERT INTO public.review_documents "
            "(id, slug, release_id, source_id, source_url, title, content_fingerprint, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                _sid("document", slug),
                slug,
                ids["release"],
                ids["source"],
                f"https://example.com/{slug}",
                slug,
                f"fingerprint-{slug}",
                "published",
            ),
        )
    return ids


def test_write_summary_is_atomic_on_failure() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)

    good = _summary(
        [
            ("结论一", ["atomic-doc-a"]),
            ("结论二", ["atomic-doc-b"]),
            ("结论三", ["atomic-doc-c"]),
        ]
    )
    bad = _summary(
        [
            ("新结论一", ["atomic-doc-a"]),
            ("新结论二", ["atomic-doc-b"]),
            ("新结论三", ["atomic-doc-nonexistent"]),
        ]
    )

    try:
        with connect(autocommit=False) as conn:
            write_summary(conn, "atomic-release", good)

            with pytest.raises(psycopg.errors.IntegrityError):
                write_summary(conn, "atomic-release", bad)

            # The failed write must have rolled back: the old summary is intact.
            summary_run = conn.execute(
                "SELECT model, corpus_hash FROM public.summary_runs WHERE release_id = %s",
                (ids["release"],),
            ).fetchone()
            assert summary_run == ("test-model", "test-corpus")

            texts = conn.execute(
                "SELECT claim_text FROM public.claims WHERE summary_run_id = %s "
                "ORDER BY claim_order",
                (_sid("summary", "atomic-release"),),
            ).fetchall()
            assert [row[0] for row in texts] == ["结论一", "结论二", "结论三"]
    finally:
        with connect() as conn:
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


# --- insert-only seeding (the fixture no-overwrite guarantee, made synthetic) ---


def _synthetic_context(title: str, claim_text: str) -> IngestedContext:
    artist = ArtistEntity(id="synthetic-artist", name="Synthetic Artist")
    release = ReleaseEntity(
        id="synthetic-release", title=title, artist_id=artist.id, year=2000
    )
    source = ReviewSource(
        id="synthetic-source",
        publication="Synthetic Source",
        homepage_url="https://example.com/synthetic",
    )
    policy = SourcePolicy(
        source_id=source.id,
        crawl_allowed=True,
        requests_per_minute=10,
        retention_days=30,
        excerpt_max_chars=280,
        attribution_required=True,
        removal_contact="rights@example.com",
    )
    document = ReviewDocument(
        id="synthetic-doc",
        release_id=release.id,
        source_id=source.id,
        source_url="https://example.com/synthetic/doc",
        title=title,
        author=None,
        published_at=None,
        score=None,
        score_scale=None,
        public_excerpt="A synthetic excerpt.",
        content=None,
        policy=policy,
    )
    summary = Summary(
        locale="zh-CN",
        model="synthetic-model",
        prompt_version="synthetic-v1",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        corpus_hash="synthetic-corpus",
        claims=[CitedClaim(text=claim_text, source_ids=["synthetic-doc"])],
    )
    return IngestedContext(
        release=release,
        artist=artist,
        sources=[source],
        review_documents=[document],
        genres=[],
        summary=summary,
    )


def test_insert_only_seed_does_not_overwrite_existing_records() -> None:
    first = _synthetic_context("Synthetic Release v1", "claim v1")
    second = _synthetic_context("Synthetic Release v2", "claim v2")

    artist_id = _sid("artist", "synthetic-artist")
    source_id = _sid("source", "synthetic-source")
    release_id = _sid("release", "synthetic-release")

    with connect() as conn:
        skip_unless_test_db(conn)

        # First seed populates the synthetic release (release absent).
        seed(conn, first, overwrite=False)

        # A second insert-only seed of the same release must write nothing.
        written = seed(conn, second, overwrite=False)
        assert written == 0

        title = conn.execute(
            "SELECT title FROM public.releases WHERE id = %s", (release_id,)
        ).fetchone()[0]
        assert title == "Synthetic Release v1"

        claim_text = conn.execute(
            "SELECT claim_text FROM public.claims WHERE summary_run_id = %s "
            "ORDER BY claim_order",
            (_sid("summary", "synthetic-release"),),
        ).fetchone()[0]
        assert claim_text == "claim v1"

    with connect() as conn:
        cleanup(conn, artist_id=artist_id, source_id=source_id)
