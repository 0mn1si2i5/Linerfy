"""Real end-to-end pipeline test against the marked test database.

This is the closest to a live E2E that can run unattended. The real job store,
seed, SQL, and five-stage state machine run against a real Postgres; only the
network boundary is stubbed — the MusicBrainz / CritiqueBrainz / Wikipedia HTTP
clients and the model — because those are external, flaky, and (for the model)
metered. Everything from ``resolve_entity`` to ``publish`` is the real code
path, including the license-pool-aware summary write and the publish guard.

Gated exactly like the other DB integration tests: it runs only with
``DATABASE_URL`` and ``LINERFY_DB_TESTS_ALLOWED=1`` set, and only against a
database marked by ``prepare_test_db``.
"""

from __future__ import annotations

import os

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.critiquebrainz import CritiqueBrainzAdapter
from linerfy_ingest.db import connect
from linerfy_ingest.entities import ReleaseGroup
from linerfy_ingest.jobs import PostgresJobStore, run_once
from linerfy_ingest.musicbrainz import MusicBrainzAdapter
from linerfy_ingest.pipeline import PipelineDeps, build_handlers
from linerfy_ingest.providers import ChatResult
from linerfy_ingest.wikipedia import ReceptionSection, WikipediaAdapter

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)

_ARTIST = "Test Artist"
_ALBUM = "Test Album"
_SLUG = "test-artist-test-album"
_DOC_ID = f"wikipedia-{_SLUG}-reception"
_FINGERPRINT = "e2e-fingerprint"


class _FakeMB(MusicBrainzAdapter):
    def search_release_groups(self, artist, album):
        return [
            ReleaseGroup(
                mbid="e2e-mbid",
                title=_ALBUM,
                artist=_ARTIST,
                score=100,
                first_release_date="2020-01-01",
            )
        ]

    def get_release_group(self, mbid):
        return ReleaseGroup(
            mbid=mbid,
            title=_ALBUM,
            artist=_ARTIST,
            first_release_date="2020-01-01",
            tags=(),
            rating=8.0,
            rating_votes=10,
            artwork_url=None,
        )


class _FakeCB(CritiqueBrainzAdapter):
    def search_reviews(self, mbid):
        return []


class _FakeWiki(WikipediaAdapter):
    def reception_section(self, title):
        return ReceptionSection(
            title="Critical reception",
            plain_text="Critics broadly praised the album.",
        )


def _chat(_messages):
    content = (
        '{"claims": ['
        f'{{"text": "评论普遍正面。", "source_ids": ["{_DOC_ID}"]}}, '
        f'{{"text": "制作获得认可。", "source_ids": ["{_DOC_ID}"]}}, '
        f'{{"text": "歌词被认为成熟。", "source_ids": ["{_DOC_ID}"]}}'
        "]}"
    )
    return ChatResult(content=content, finish_reason="stop")


def test_pipeline_runs_resolve_to_publish_against_test_db() -> None:
    with connect(autocommit=False) as conn:
        skip_unless_test_db(conn)
        conn.execute(
            "INSERT INTO public.enrichment_jobs "
            "(entity_id, entity_kind, stage, state, payload) VALUES (%s,%s,%s,%s,%s)",
            (
                _FINGERPRINT,
                "release",
                "resolve_entity",
                "queued",
                '{"provider":"spotify","title":"T","artist":"Test Artist",'
                '"album":"Test Album","state":"playing"}',
            ),
        )

        store = PostgresJobStore(conn)
        deps = PipelineDeps(
            store=store,
            conn=conn,
            musicbrainz=_FakeMB(),
            critiquebrainz=_FakeCB(),
            wikipedia=_FakeWiki(),
            model="e2e-model",
            chat=_chat,
        )
        handlers = build_handlers(deps)

        # One stage per run_once; the loop bound guards against a regression
        # that would otherwise spin forever.
        for _ in range(6):
            if run_once(store, handlers) == 0:
                break

        state = conn.execute(
            "SELECT state, stage FROM public.enrichment_jobs WHERE entity_id = %s",
            (_FINGERPRINT,),
        ).fetchone()
        assert state is not None and state[0] == "ready", f"job not ready: {state}"

        published = conn.execute(
            "SELECT count(*) FROM public.summary_runs s "
            "JOIN public.releases r ON r.id = s.release_id "
            "WHERE r.slug = %s AND s.status = 'published'",
            (_SLUG,),
        ).fetchone()[0]
        assert published == 1

        # No commit on the transaction: the test DB is left untouched.
        conn.rollback()


def test_pipeline_marks_unresolvable_entity_unavailable() -> None:
    class _NoMatch(_FakeMB):
        def search_release_groups(self, artist, album):
            return []

    with connect(autocommit=False) as conn:
        skip_unless_test_db(conn)
        conn.execute(
            "INSERT INTO public.enrichment_jobs "
            "(entity_id, entity_kind, stage, state, payload) VALUES (%s,%s,%s,%s,%s)",
            (
                "e2e-unresolvable",
                "release",
                "resolve_entity",
                "queued",
                '{"provider":"spotify","title":"T","artist":"Unknown","album":"None"}',
            ),
        )

        store = PostgresJobStore(conn)
        deps = PipelineDeps(
            store=store,
            conn=conn,
            musicbrainz=_NoMatch(),
            critiquebrainz=_FakeCB(),
            wikipedia=_FakeWiki(),
            model="e2e-model",
            chat=_chat,
        )
        run_once(store, build_handlers(deps))

        state = conn.execute(
            "SELECT state FROM public.enrichment_jobs WHERE entity_id = %s",
            ("e2e-unresolvable",),
        ).fetchone()
        assert state is not None and state[0] == "unavailable"

        conn.rollback()
