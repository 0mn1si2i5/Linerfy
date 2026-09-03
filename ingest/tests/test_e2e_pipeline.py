"""Real end-to-end pipeline test against the marked test database.

This is the closest to a live E2E that can run unattended. The real job store,
lease CAS, seed, SQL, and five-stage state machine run against a real Postgres;
only the network boundary is stubbed — the MusicBrainz / CritiqueBrainz /
Wikipedia HTTP clients and the model — because those are external, flaky, and
(for the model) metered.

Gated exactly like the other DB integration tests: it runs only with
``DATABASE_URL`` and ``LINERFY_DB_TESTS_ALLOWED=1`` set, and only against a
database marked by ``prepare_test_db``.
"""

from __future__ import annotations

import os
import re

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.critiquebrainz import CritiqueBrainzAdapter, CritiqueBrainzReview
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
        return [
            CritiqueBrainzReview(
                id="cb-1",
                entity_id=mbid,
                text="A user review that praises the album's writing.",
                license_id="CC BY-NC-SA 3.0",
                language="en",
                rating=4,
                author="Reviewer",
                created=None,
            )
        ]


class _FakeWiki(WikipediaAdapter):
    def reception_section(self, title):
        return ReceptionSection(
            title="Critical reception",
            plain_text="Critics broadly praised the album.",
        )


def _chat(messages):
    # The stub model must cite the ids of the corpus it was actually given, so
    # the same callable serves every source/pool. Extract them from the user
    # prompt's <document id="..."> markers.
    user = messages[-1]["content"]
    doc_ids = re.findall(r'<document id="([^"]+)"', user) or [_DOC_ID]
    src = doc_ids[0]
    content = (
        '{"claims": ['
        f'{{"text": "评论普遍正面。", "source_ids": ["{src}"]}}, '
        f'{{"text": "制作获得认可。", "source_ids": ["{src}"]}}, '
        f'{{"text": "歌词被认为成熟。", "source_ids": ["{src}"]}}'
        "]}"
    )
    return ChatResult(content=content, finish_reason="stop")


def _deps(store, musicbrainz) -> PipelineDeps:
    return PipelineDeps(
        store=store,
        musicbrainz=musicbrainz,
        critiquebrainz=_FakeCB(),
        wikipedia=_FakeWiki(),
        model="e2e-model",
        chat=_chat,
    )


def _cleanup(fingerprints: list[str]) -> None:
    with connect() as conn:
        for fp in fingerprints:
            conn.execute(
                "DELETE FROM public.enrichment_jobs WHERE entity_id = %s", (fp,)
            )
        conn.execute("DELETE FROM public.artists WHERE slug = %s", ("test-artist",))
        conn.execute(
            "DELETE FROM public.review_sources WHERE slug IN (%s,%s)",
            ("wikipedia", "critiquebrainz"),
        )


def _run_to_completion(store, handlers) -> None:
    # One bounded work unit per run_once; loop until the queue is empty, with a
    # bound to catch a regression that would otherwise spin forever.
    for _ in range(40):
        if run_once(store, handlers) == 0:
            return
    raise AssertionError("pipeline did not reach an idle state")


def test_pipeline_runs_resolve_to_publish_against_test_db() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)

    try:
        with connect() as conn:
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

        store = PostgresJobStore()
        _run_to_completion(store, build_handlers(_deps(store, _FakeMB())))

        with connect() as conn:
            state = conn.execute(
                "SELECT state, stage, resolution_status FROM public.enrichment_jobs "
                "WHERE entity_id = %s",
                (_FINGERPRINT,),
            ).fetchone()
            assert state is not None and state[0] == "ready", f"job not ready: {state}"

            published = conn.execute(
                "SELECT count(*) FROM public.summary_runs s "
                "JOIN public.releases r ON r.id = s.release_id "
                "WHERE r.slug = %s AND s.status = 'published'",
                (_SLUG,),
            ).fetchone()[0]
            # Two per-source summaries (Wikipedia + CritiqueBrainz) plus two
            # skipped consensus blocks (one per license pool; each pool has a
            # single source, below the two-source consensus threshold).
            assert published == 4

            # The two sources and two license pools all survived the switch.
            scopes = conn.execute(
                "SELECT scope FROM public.summary_runs s "
                "JOIN public.releases r ON r.id = s.release_id "
                "WHERE r.slug = %s AND s.status = 'published'",
                (_SLUG,),
            ).fetchall()
            assert {row[0] for row in scopes} == {
                "source::critiquebrainz",
                "source::wikipedia",
                "consensus::CC BY-NC-SA 3.0",
                "consensus::CC BY-SA 4.0",
            }

            # The corpus was persisted privately: the full review text lives in
            # review_document_bodies, never in the public summary claim text.
            body_count = conn.execute(
                "SELECT count(*) FROM public.review_document_bodies b "
                "JOIN public.review_documents d ON d.id = b.document_id "
                "JOIN public.releases r ON r.id = d.release_id "
                "WHERE r.slug = %s",
                (_SLUG,),
            ).fetchone()[0]
            assert body_count == 2
    finally:
        _cleanup([_FINGERPRINT])


def test_pipeline_marks_unresolvable_entity_unavailable() -> None:
    class _NoMatch(_FakeMB):
        def search_release_groups(self, artist, album):
            return []

    with connect() as conn:
        skip_unless_test_db(conn)

    try:
        with connect() as conn:
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

        store = PostgresJobStore()
        run_once(store, build_handlers(_deps(store, _NoMatch())))

        with connect() as conn:
            state = conn.execute(
                "SELECT state, resolution_status FROM public.enrichment_jobs "
                "WHERE entity_id = %s",
                ("e2e-unresolvable",),
            ).fetchone()
            assert state is not None and state[0] == "unavailable"
    finally:
        _cleanup(["e2e-unresolvable"])
