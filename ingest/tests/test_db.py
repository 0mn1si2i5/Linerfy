import os
import uuid

import pytest
from _db_helpers import _reset_permitted, skip_unless_test_db

from linerfy_ingest.db import connect, delete_metadata_genres


def test_reset_permitted_for_local_host() -> None:
    assert _reset_permitted("localhost")
    assert _reset_permitted("127.0.0.1")
    assert _reset_permitted("::1")


def test_reset_refused_for_remote_host_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LINERFY_RESET_ALLOWED", raising=False)
    assert not _reset_permitted("aws-0-ap-southeast-1.pooler.supabase.com")


def test_reset_permitted_when_explicitly_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINERFY_RESET_ALLOWED", "1")
    assert _reset_permitted("aws-0-ap-southeast-1.pooler.supabase.com")


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="requires test database")
def test_delete_metadata_genres_removes_uncited_keeps_cited() -> None:
    artist_id = uuid.uuid4()
    release_id = uuid.uuid4()
    source_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    uncited_id = uuid.uuid4()
    cited_id = uuid.uuid4()

    with connect() as conn:
        skip_unless_test_db(conn)
        conn.execute(
            "INSERT INTO public.artists (id, slug, name) VALUES (%s,%s,%s)",
            (artist_id, "ga-artist", "GA"),
        )
        conn.execute(
            "INSERT INTO public.releases (id, slug, artist_id, title) VALUES (%s,%s,%s,%s)",
            (release_id, "ga-release", artist_id, "GA Release"),
        )
        conn.execute(
            "INSERT INTO public.review_sources (id, slug, publication, homepage_url) "
            "VALUES (%s,%s,%s,%s)",
            (source_id, "ga-source", "GA Source", "https://example.com"),
        )
        conn.execute(
            "INSERT INTO public.review_documents "
            "(id, slug, release_id, source_id, source_url, title, license_id, "
            " license_url, content_fingerprint, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                doc_id,
                "ga-doc",
                release_id,
                source_id,
                "https://example.com/ga",
                "GA Doc",
                "proprietary",
                "https://example.com/license",
                "fp",
                "published",
            ),
        )
        conn.execute(
            "INSERT INTO public.genres (id, release_id, name) VALUES (%s,%s,%s)",
            (uncited_id, release_id, "stale genre"),
        )
        conn.execute(
            "INSERT INTO public.genres (id, release_id, name) VALUES (%s,%s,%s)",
            (cited_id, release_id, "cited genre"),
        )
        conn.execute(
            "INSERT INTO public.genre_sources (genre_id, document_id) VALUES (%s,%s)",
            (cited_id, doc_id),
        )

    try:
        with connect() as conn:
            assert delete_metadata_genres(conn, release_id) == 1
        with connect() as conn:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM public.genres WHERE release_id = %s",
                    (release_id,),
                ).fetchall()
            }
        assert names == {"cited genre"}
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM public.artists WHERE id = %s", (artist_id,))
            conn.execute("DELETE FROM public.review_sources WHERE id = %s", (source_id,))
