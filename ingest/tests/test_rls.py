"""RLS integration tests on isolated, uniquely-named test entities.

Opt-in: they run only when ``DATABASE_URL`` is set, and they exercise that
database directly. They create their own artist/release/source/documents (never
seeding the fixture), assert the public read boundary, and clean up fully, so a
real release such as Norman Fucking Rockwell! is never touched.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from _db_helpers import cleanup, skip_unless_test_db, tid

from linerfy_ingest.db import connect

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)


def _role_count(conn, role: str, query: str, params: tuple = ()) -> int:
    conn.execute(f"SET ROLE {role}")
    try:
        return conn.execute(query, params).fetchone()[0]
    finally:
        conn.execute("RESET ROLE")


@pytest.fixture(scope="module")
def rls_ids():
    """Create an isolated artist/release/source with a published and a draft
    document, a genre, a published summary + claim, and a second release with its
    own document. Citations span all three documents (published same-release,
    draft, cross-release) so visibility can be asserted per citation."""
    ids = {
        "artist": tid("rls-artist"),
        "release": tid("rls-release"),
        "source": tid("rls-source"),
        "published": tid("rls-doc-published"),
        "draft": tid("rls-doc-draft"),
        "second_release": tid("rls-second-release"),
        "second_doc": tid("rls-second-doc"),
        "genre": tid("rls-genre"),
        "summary": tid("rls-summary"),
        "claim": tid("rls-claim"),
    }

    with connect() as conn:
        skip_unless_test_db(conn)

        conn.execute(
            "INSERT INTO public.artists (id, slug, name) VALUES (%s,%s,%s)",
            (ids["artist"], "rls-artist", "RLS Test Artist"),
        )
        conn.execute(
            "INSERT INTO public.releases (id, slug, artist_id, title) VALUES (%s,%s,%s,%s)",
            (ids["release"], "rls-release", ids["artist"], "RLS Test Release"),
        )
        conn.execute(
            "INSERT INTO public.review_sources "
            "(id, slug, publication, homepage_url) VALUES (%s,%s,%s,%s)",
            (ids["source"], "rls-source", "RLS Test Source", "https://example.com"),
        )

        for key, slug, status in (
            ("published", "rls-doc-published", "published"),
            ("draft", "rls-doc-draft", "draft"),
        ):
            conn.execute(
                "INSERT INTO public.review_documents "
                "(id, slug, release_id, source_id, source_url, title, content_fingerprint, status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    ids[key],
                    slug,
                    ids["release"],
                    ids["source"],
                    f"https://example.com/{slug}",
                    slug.replace("-", " ").title(),
                    f"fingerprint-{slug}",
                    status,
                ),
            )

        conn.execute(
            "INSERT INTO public.releases (id, slug, artist_id, title) VALUES (%s,%s,%s,%s)",
            (ids["second_release"], "rls-second-release", ids["artist"], "RLS Second Release"),
        )
        conn.execute(
            "INSERT INTO public.review_documents "
            "(id, slug, release_id, source_id, source_url, title, content_fingerprint, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                ids["second_doc"],
                "rls-second-doc",
                ids["second_release"],
                ids["source"],
                "https://example.com/rls-second-doc",
                "RLS Second Doc",
                "fingerprint-rls-second-doc",
                "published",
            ),
        )

        conn.execute(
            "INSERT INTO public.genres (id, release_id, name) VALUES (%s,%s,%s)",
            (ids["genre"], ids["release"], "RLS Genre"),
        )
        conn.execute(
            "INSERT INTO public.summary_runs "
            "(id, release_id, model, prompt_version, status) VALUES (%s,%s,%s,%s,%s)",
            (ids["summary"], ids["release"], "rls-model", "rls-prompt", "published"),
        )
        conn.execute(
            "INSERT INTO public.claims (id, summary_run_id, claim_order, claim_text) "
            "VALUES (%s,%s,%s,%s)",
            (ids["claim"], ids["summary"], 0, "rls claim"),
        )

        for document in (ids["published"], ids["draft"], ids["second_doc"]):
            conn.execute(
                "INSERT INTO public.genre_sources (genre_id, document_id) VALUES (%s,%s)",
                (ids["genre"], document),
            )
            conn.execute(
                "INSERT INTO public.claim_sources (claim_id, document_id) VALUES (%s,%s)",
                (ids["claim"], document),
            )

    try:
        yield ids
    finally:
        with connect() as conn:
            cleanup(conn, artist_id=ids["artist"], source_id=ids["source"])


def test_anon_is_fully_revoked(rls_ids) -> None:
    # The auth boundary (migration 004) removes anonymous catalog reads: the
    # anon role has no SELECT grant, so even a policy regression cannot leak.
    with connect() as conn:
        for query in (
            "SELECT count(*) FROM public.releases",
            "SELECT count(*) FROM public.claims",
            "SELECT count(*) FROM public.claim_sources",
        ):
            conn.execute("SET ROLE anon")
            try:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(query)
            finally:
                conn.execute("RESET ROLE")


def test_authenticated_reads_published_same_release_citations(rls_ids) -> None:
    with connect() as conn:
        assert (
            _role_count(
                conn,
                "authenticated",
                "SELECT count(*) FROM public.claim_sources "
                "WHERE claim_id = %s AND document_id = %s",
                (rls_ids["claim"], rls_ids["published"]),
            )
            == 1
        )
        assert (
            _role_count(
                conn,
                "authenticated",
                "SELECT count(*) FROM public.genre_sources "
                "WHERE genre_id = %s AND document_id = %s",
                (rls_ids["genre"], rls_ids["published"]),
            )
            == 1
        )


def test_authenticated_cannot_read_a_draft_citation(rls_ids) -> None:
    with connect() as conn:
        assert (
            _role_count(
                conn,
                "authenticated",
                "SELECT count(*) FROM public.claim_sources "
                "WHERE claim_id = %s AND document_id = %s",
                (rls_ids["claim"], rls_ids["draft"]),
            )
            == 0
        )
        assert (
            _role_count(
                conn,
                "authenticated",
                "SELECT count(*) FROM public.genre_sources "
                "WHERE genre_id = %s AND document_id = %s",
                (rls_ids["genre"], rls_ids["draft"]),
            )
            == 0
        )


def test_authenticated_cannot_read_a_cross_release_citation(rls_ids) -> None:
    with connect() as conn:
        assert (
            _role_count(
                conn,
                "authenticated",
                "SELECT count(*) FROM public.claim_sources "
                "WHERE claim_id = %s AND document_id = %s",
                (rls_ids["claim"], rls_ids["second_doc"]),
            )
            == 0
        )
        assert (
            _role_count(
                conn,
                "authenticated",
                "SELECT count(*) FROM public.genre_sources "
                "WHERE genre_id = %s AND document_id = %s",
                (rls_ids["genre"], rls_ids["second_doc"]),
            )
            == 0
        )


def test_authenticated_cannot_read_a_review_body(rls_ids) -> None:
    with connect() as conn:
        conn.execute("SET ROLE authenticated")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM public.review_document_bodies")
