"""Database integration tests for summary atomicity and fixture isolation.

Opt-in (``DATABASE_URL``). The atomicity test uses uniquely-named test entities
created with the same ``stable_uuid`` scheme as production, so ``write_summary``
resolves their ids exactly as it does in real life; it cleans up afterwards. The
fixture test runs the real fixture against the real catalog and proves it changes
nothing.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from _db_helpers import cleanup

from linerfy_ingest.adapter import FixtureSourceAdapter
from linerfy_ingest.db import apply_migration, connect, seed
from linerfy_ingest.models import CitedClaim, Summary
from linerfy_ingest.seed import stable_uuid
from linerfy_ingest.summarize import write_summary

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; DB integration tests are opt-in",
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "reviews.json"


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
        apply_migration(conn)
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


def _nfr_snapshot(conn):
    release_id = conn.execute(
        "SELECT id FROM public.releases WHERE slug = %s", ("norman-fucking-rockwell",)
    ).fetchone()
    if release_id is None:
        return None
    release_id = release_id[0]
    guardian_title = conn.execute(
        "SELECT title FROM public.review_documents WHERE slug = %s", ("guardian-nfr",)
    ).fetchone()
    summary = conn.execute(
        "SELECT corpus_hash, model FROM public.summary_runs WHERE release_id = %s",
        (release_id,),
    ).fetchone()
    claims = conn.execute(
        "SELECT count(*) FROM public.claims c "
        "JOIN public.summary_runs s ON s.id = c.summary_run_id WHERE s.release_id = %s",
        (release_id,),
    ).fetchone()[0]
    sources = conn.execute(
        "SELECT count(*) FROM public.claim_sources cs "
        "JOIN public.claims c ON c.id = cs.claim_id "
        "JOIN public.summary_runs s ON s.id = c.summary_run_id WHERE s.release_id = %s",
        (release_id,),
    ).fetchone()[0]
    return (guardian_title, summary, claims, sources)


def test_fixture_seed_does_not_change_existing_records() -> None:
    with connect() as conn:
        before = _nfr_snapshot(conn)
        if before is None:
            pytest.skip("NFR release not present; cannot exercise fixture no-overwrite")
        written = seed(conn, FixtureSourceAdapter(_FIXTURE).fetch(), overwrite=False)
        after = _nfr_snapshot(conn)

    assert written == 0
    assert after == before
