"""Tests for the Vercel Python worker function's core (auth + advance_once)."""

from __future__ import annotations

import os

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.critiquebrainz import CritiqueBrainzAdapter
from linerfy_ingest.db import connect
from linerfy_ingest.entities import ReleaseGroup
from linerfy_ingest.musicbrainz import MusicBrainzAdapter
from linerfy_ingest.providers import ChatResult
from linerfy_ingest.wikipedia import WikipediaAdapter
from linerfy_ingest.worker import advance_once, check_worker_auth

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)


def test_auth_missing_secret_is_503() -> None:
    assert check_worker_auth("", "Bearer anything") == 503


def test_auth_missing_bearer_is_401() -> None:
    assert check_worker_auth("secret", "") == 401
    assert check_worker_auth("secret", "Basic xyz") == 401


def test_auth_wrong_token_is_401() -> None:
    assert check_worker_auth("secret", "Bearer wrong") == 401


def test_auth_correct_token_is_allowed() -> None:
    assert check_worker_auth("secret", "Bearer secret") is None


class _FakeMB(MusicBrainzAdapter):
    def search_release_groups(self, artist, album):
        return [ReleaseGroup(mbid="mb-1", title=album, artist=artist, score=100)]

    def get_release_group(self, mbid):
        return ReleaseGroup(mbid=mbid, title="Test Album", artist="Test Artist")


class _FakeCB(CritiqueBrainzAdapter):
    def search_reviews(self, mbid):
        return []


class _FakeWiki(WikipediaAdapter):
    def reception_section(self, title):
        return None


def test_advance_once_advances_a_synthetic_job() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)

    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO public.enrichment_jobs "
                "(entity_id, entity_kind, stage, state, payload) VALUES (%s,%s,%s,%s,%s)",
                (
                    "worker-fp",
                    "release",
                    "resolve_entity",
                    "queued",
                    '{"provider":"spotify","title":"T","artist":"Test Artist",'
                    '"album":"Test Album"}',
                ),
            )

        processed = advance_once(
            musicbrainz=_FakeMB(),
            critiquebrainz=_FakeCB(),
            wikipedia=_FakeWiki(),
            chat=lambda messages: ChatResult(content="{}", finish_reason="stop"),
        )
        assert processed == 1

        with connect() as conn:
            row = conn.execute(
                "SELECT stage, state, resolution_status FROM public.enrichment_jobs "
                "WHERE entity_id = 'worker-fp'"
            ).fetchone()
            assert row[0] == "fetch_sources"  # advanced past resolve_entity
            assert row[1] == "queued"
            assert row[2] == "resolved"
    finally:
        with connect() as conn:
            conn.execute(
                "DELETE FROM public.enrichment_jobs WHERE entity_id = 'worker-fp'"
            )
