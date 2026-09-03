"""Database integration tests for immutable summary generations.

Opt-in and gated: they run only when both ``DATABASE_URL`` and
``LINERFY_DB_TESTS_ALLOWED=1`` are set, and then only against a database marked
with ``prepare_test_db``. Every entity is uniquely named and cleaned up, so a
real release such as Norman Fucking Rockwell! is never read or written.

These prove the R4 invariants directly at the ``write_summary`` /
``write_consensus_skipped`` / ``publish`` boundary: a generation is append-only,
a candidate coexists with the old published version, retry with the same corpus
is idempotent, a changed corpus creates a new generation, and publish atomically
switches the candidate into place while retaining (and superseding) the old one.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import psycopg
import pytest
from _db_helpers import cleanup, skip_unless_test_db

from linerfy_ingest.db import connect, seed
from linerfy_ingest.jobs import StaleLease
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
from linerfy_ingest.summarize import (
    publish,
    write_consensus_skipped,
    write_summary,
)

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)

_RELEASE_SLUG = "atomic-release"


def _sid(kind: str, slug: str) -> uuid.UUID:
    return uuid.UUID(stable_uuid(kind, slug))


def _summary(
    texts: list[str],
    *,
    corpus_hash: str = "test-corpus",
    kind: str = "source",
    source_id: str | None = "atomic-source",
    license_pool: str = "proprietary",
    source_ids: list[str] | None = None,
) -> Summary:
    """A summary whose claims all cite existing catalog documents by default."""
    default_sources = ["atomic-doc-a", "atomic-doc-b", "atomic-doc-c"]
    sources = source_ids if source_ids is not None else default_sources
    claims = [
        CitedClaim(text=text, source_ids=[sources[i % len(sources)]])
        for i, text in enumerate(texts)
    ]
    return Summary(
        locale="zh-CN",
        model="test-model",
        prompt_version="test-v1",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        corpus_hash=corpus_hash,
        claims=claims,
        kind=kind,
        source_id=source_id,
        license_pool=license_pool,
        license_url="https://example.com/license",
        attribution="Atomic Source",
    )


def _insert_atomic_catalog(conn) -> dict:
    ids = {
        "artist": _sid("artist", "atomic-artist"),
        "release": _sid("release", _RELEASE_SLUG),
        "source": _sid("source", "atomic-source"),
    }
    conn.execute(
        "INSERT INTO public.artists (id, slug, name) VALUES (%s,%s,%s)",
        (ids["artist"], "atomic-artist", "Atomic Artist"),
    )
    conn.execute(
        "INSERT INTO public.releases (id, slug, artist_id, title) VALUES (%s,%s,%s,%s)",
        (ids["release"], _RELEASE_SLUG, ids["artist"], "Atomic Release"),
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


def _published(conn, release_id: uuid.UUID) -> list[str]:
    rows = conn.execute(
        "SELECT corpus_hash FROM public.summary_runs "
        "WHERE release_id = %s AND status = 'published' ORDER BY corpus_hash",
        (release_id,),
    ).fetchall()
    return [r[0] for r in rows]


def test_candidate_coexists_with_published_and_read_returns_old() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        v1 = _summary(["结论一", "结论二", "结论三"], corpus_hash="corpus-v1")
        with connect(autocommit=False) as conn:
            write_summary(conn, _RELEASE_SLUG, v1, status="candidate")
            publish(conn, _RELEASE_SLUG)

        v2 = _summary(["新结论一", "新结论二", "新结论三"], corpus_hash="corpus-v2")
        with connect(autocommit=False) as conn:
            write_summary(conn, _RELEASE_SLUG, v2, status="candidate")

        with connect() as conn:
            # The public read path (status = 'published') still returns v1.
            assert _published(conn, ids["release"]) == ["corpus-v1"]
            candidate = conn.execute(
                "SELECT corpus_hash FROM public.summary_runs "
                "WHERE release_id = %s AND status = 'candidate'",
                (ids["release"],),
            ).fetchone()
            assert candidate is not None and candidate[0] == "corpus-v2"
    finally:
        with connect() as conn:
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def test_half_failed_candidate_leaves_old_intact() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        v1 = _summary(["结论一", "结论二", "结论三"], corpus_hash="corpus-v1")
        with connect(autocommit=False) as conn:
            write_summary(conn, _RELEASE_SLUG, v1, status="candidate")
            publish(conn, _RELEASE_SLUG)

        # A candidate citing a nonexistent document violates the claim_sources
        # foreign key; the failed generation must not disturb the published v1.
        bad = Summary(
            locale="zh-CN",
            model="test-model",
            prompt_version="test-v1",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            corpus_hash="corpus-v2",
            claims=[
                CitedClaim(text=f"结论{i}", source_ids=["atomic-doc-nonexistent"])
                for i in range(3)
            ],
        )
        with connect(autocommit=False) as conn, pytest.raises(
            psycopg.errors.IntegrityError
        ):
            write_summary(conn, _RELEASE_SLUG, bad, status="candidate")

        with connect() as conn:
            assert _published(conn, ids["release"]) == ["corpus-v1"]
            candidate = conn.execute(
                "SELECT count(*) FROM public.summary_runs "
                "WHERE release_id = %s AND status = 'candidate'",
                (ids["release"],),
            ).fetchone()[0]
            assert candidate == 0
    finally:
        with connect() as conn:
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def _insert_job(conn, lease_id: uuid.UUID) -> uuid.UUID:
    job_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO public.enrichment_jobs "
        "(id, entity_id, entity_kind, stage, state, lease_id, payload) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (
            job_id,
            f"atomic-{job_id.hex[:8]}",
            "release",
            "publish",
            "running",
            lease_id,
            '{"provider":"test","title":"T","artist":"A","album":"B","state":"playing"}',
        ),
    )
    return job_id


def test_stale_lease_cannot_publish() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        v1 = _summary(["结论一", "结论二", "结论三"])
        with connect(autocommit=False) as conn:
            write_summary(conn, _RELEASE_SLUG, v1, status="candidate")

        with connect() as conn:
            job_id = _insert_job(conn, lease_id=uuid.uuid4())

        with connect(autocommit=False) as conn, pytest.raises(StaleLease):
            publish(
                conn,
                _RELEASE_SLUG,
                job_id=str(job_id),
                lease_id=str(uuid.uuid4()),  # wrong lease
            )

        with connect() as conn:
            assert _published(conn, ids["release"]) == []
            candidate = conn.execute(
                "SELECT count(*) FROM public.summary_runs "
                "WHERE release_id = %s AND status = 'candidate'",
                (ids["release"],),
            ).fetchone()[0]
            assert candidate == 1
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM public.enrichment_jobs WHERE entity_id LIKE 'atomic-%'")
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def test_atomic_switch_promotes_candidate_and_retains_old() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        v1 = _summary(["结论一", "结论二", "结论三"], corpus_hash="corpus-v1")
        with connect(autocommit=False) as conn:
            write_summary(conn, _RELEASE_SLUG, v1, status="candidate")
            publish(conn, _RELEASE_SLUG)

        v2 = _summary(["新结论一", "新结论二", "新结论三"], corpus_hash="corpus-v2")
        with connect(autocommit=False) as conn:
            write_summary(conn, _RELEASE_SLUG, v2, status="candidate")

        with connect() as conn:
            lease_id = uuid.uuid4()
            job_id = _insert_job(conn, lease_id=lease_id)

        with connect(autocommit=False) as conn:
            publish(conn, _RELEASE_SLUG, job_id=str(job_id), lease_id=str(lease_id))

        with connect() as conn:
            assert _published(conn, ids["release"]) == ["corpus-v2"]
            statuses = conn.execute(
                "SELECT corpus_hash, status, published_at IS NOT NULL FROM public.summary_runs "
                "WHERE release_id = %s ORDER BY corpus_hash",
                (ids["release"],),
            ).fetchall()
            by_hash = {row[0]: row for row in statuses}
            # The old version is retained, but superseded (not current).
            assert by_hash["corpus-v1"][1] == "superseded"
            # The new version is published, with a publish timestamp.
            assert by_hash["corpus-v2"][1] == "published"
            assert by_hash["corpus-v2"][2] is True
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM public.enrichment_jobs WHERE entity_id LIKE 'atomic-%'")
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def test_corpus_unchanged_retry_is_idempotent() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        s = _summary(["结论一", "结论二", "结论三"], corpus_hash="corpus-v1")
        with connect(autocommit=False) as conn:
            first = write_summary(conn, _RELEASE_SLUG, s, status="candidate")
        with connect(autocommit=False) as conn:
            second = write_summary(conn, _RELEASE_SLUG, s, status="candidate")

        assert first == second
        with connect() as conn:
            count = conn.execute(
                "SELECT count(*) FROM public.summary_runs WHERE release_id = %s",
                (ids["release"],),
            ).fetchone()[0]
            assert count == 1
    finally:
        with connect() as conn:
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def test_corpus_changed_creates_a_new_generation() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        s1 = _summary(["结论一", "结论二", "结论三"], corpus_hash="corpus-v1")
        s2 = _summary(["新结论一", "新结论二", "新结论三"], corpus_hash="corpus-v2")
        with connect(autocommit=False) as conn:
            first = write_summary(conn, _RELEASE_SLUG, s1, status="candidate")
        with connect(autocommit=False) as conn:
            second = write_summary(conn, _RELEASE_SLUG, s2, status="candidate")

        assert first != second
        with connect() as conn:
            statuses = conn.execute(
                "SELECT corpus_hash, status FROM public.summary_runs WHERE release_id = %s",
                (ids["release"],),
            ).fetchall()
            by_hash = {row[0]: row[1] for row in statuses}
            assert by_hash["corpus-v1"] == "superseded"  # in-flight candidate retired
            assert by_hash["corpus-v2"] == "candidate"
    finally:
        with connect() as conn:
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def test_two_sources_and_two_pools_are_not_lost() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        source_a = _summary(
            ["结论一", "结论二", "结论三"], source_id="src-a", license_pool="pool-1"
        )
        source_b = _summary(
            ["结论四", "结论五", "结论六"], source_id="src-b", license_pool="pool-2"
        )
        consensus_1 = _summary(
            ["共识一", "共识二", "共识三"], kind="consensus", license_pool="pool-1", source_id=None
        )
        consensus_2 = _summary(
            ["共识四", "共识五", "共识六"], kind="consensus", license_pool="pool-2", source_id=None
        )
        with connect(autocommit=False) as conn:
            write_summary(conn, _RELEASE_SLUG, source_a, status="candidate")
            write_summary(conn, _RELEASE_SLUG, source_b, status="candidate")
            write_summary(conn, _RELEASE_SLUG, consensus_1, status="candidate")
            write_summary(conn, _RELEASE_SLUG, consensus_2, status="candidate")
            publish(conn, _RELEASE_SLUG)

        with connect() as conn:
            scopes = conn.execute(
                "SELECT scope, summary_kind, license_pool FROM public.summary_runs "
                "WHERE release_id = %s AND status = 'published' ORDER BY scope",
                (ids["release"],),
            ).fetchall()
            scope_keys = {row[0] for row in scopes}
            assert scope_keys == {
                "source::src-a",
                "source::src-b",
                "consensus::pool-1",
                "consensus::pool-2",
            }
            assert len(scopes) == 4
    finally:
        with connect() as conn:
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def test_consensus_skipped_is_idempotent_and_scope_aware() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        ids = _insert_atomic_catalog(conn)
    try:
        with connect(autocommit=False) as conn:
            first = write_consensus_skipped(
                conn,
                _RELEASE_SLUG,
                license_pool="pool-1",
                attribution="Atomic Source",
                corpus_hash="pool-v1",
            )
        with connect(autocommit=False) as conn:
            second = write_consensus_skipped(
                conn,
                _RELEASE_SLUG,
                license_pool="pool-1",
                attribution="Atomic Source",
                corpus_hash="pool-v1",
            )
        assert first == second
        with connect() as conn:
            count = conn.execute(
                "SELECT count(*) FROM public.summary_runs WHERE release_id = %s",
                (ids["release"],),
            ).fetchone()[0]
            assert count == 1
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
        license_id="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
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
        summaries=[summary],
    )


def test_insert_only_seed_does_not_overwrite_existing_records() -> None:
    first = _synthetic_context("Synthetic Release v1", "claim v1")
    second = _synthetic_context("Synthetic Release v2", "claim v2")

    artist_id = _sid("artist", "synthetic-artist")
    source_id = _sid("source", "synthetic-source")
    release_id = _sid("release", "synthetic-release")
    summary_run_id = _sid("summary", "synthetic-release::source::unscoped")

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
            (summary_run_id,),
        ).fetchone()[0]
        assert claim_text == "claim v1"

    with connect() as conn:
        cleanup(conn, artist_id=artist_id, source_id=source_id)
