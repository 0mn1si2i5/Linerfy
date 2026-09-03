"""Tests for the real stage handlers (resolve stage + handler wiring)."""

from __future__ import annotations

import pytest

from linerfy_ingest.entities import ReleaseGroup
from linerfy_ingest.jobs import EnrichmentJob, JobUnavailable
from linerfy_ingest.musicbrainz import MusicBrainzAdapter
from linerfy_ingest.pipeline import PipelineDeps, build_handlers

_JOB = EnrichmentJob(
    id="j1",
    entity_id="fingerprint",
    stage="resolve_entity",
    state="running",
    payload={
        "provider": "spotify",
        "title": "Mariners Apartment Complex",
        "artist": "Lana Del Rey",
        "album": "Norman Fucking Rockwell!",
    },
)


class FakeStore:
    def __init__(self):
        self.resolutions: list[tuple] = []
        self.commits: list[tuple] = []

    def set_resolution(self, job_id, lease_id, release_group_id, status):
        self.resolutions.append((release_group_id, status))

    def commit(self, job_id, lease_id, *, stage, state):
        self.commits.append((stage, state))

    def fail(self, job_id, lease_id, error):
        raise AssertionError(f"unexpected fail: {error}")


class FakeMB(MusicBrainzAdapter):
    def __init__(self, search_result, lookup_result):
        super().__init__()
        self.search_result = search_result
        self.lookup_result = lookup_result

    def search_release_groups(self, artist, album):
        return self.search_result

    def get_release_group(self, mbid):
        return self.lookup_result


def _deps(store, musicbrainz) -> PipelineDeps:
    return PipelineDeps(
        store=store,
        musicbrainz=musicbrainz,
        critiquebrainz=None,
        wikipedia=None,
        model="deepseek-chat",
        chat=lambda messages: None,
    )


def test_build_handlers_has_all_four_stages() -> None:
    handlers = build_handlers(_deps(FakeStore(), FakeMB([], None)))
    assert set(handlers) == {
        "resolve_entity",
        "fetch_sources",
        "build_source_summaries",
        "build_consensus",
    }


def test_resolve_entity_sets_resolution_on_match() -> None:
    store = FakeStore()
    rg = ReleaseGroup(
        mbid="rg-1", title="Norman Fucking Rockwell!", artist="Lana Del Rey", score=100
    )
    mb = FakeMB([rg], rg)
    handlers = build_handlers(_deps(store, mb))
    advanced = handlers["resolve_entity"](_JOB, "lease-1")
    assert advanced is True
    assert store.resolutions == [("rg-1", "resolved")]


def test_resolve_entity_marks_unavailable_on_no_match() -> None:
    store = FakeStore()
    mb = FakeMB([], None)
    handlers = build_handlers(_deps(store, mb))
    with pytest.raises(JobUnavailable):
        handlers["resolve_entity"](_JOB, "lease-1")
    assert store.resolutions == [(None, "unavailable")]


def test_resolve_entity_preserves_ambiguous() -> None:
    store = FakeStore()
    # A low-score candidate: unreliable, not a hard not-found.
    low = ReleaseGroup(
        mbid="rg-low", title="Norman Fucking Rockwell!", artist="Lana Del Rey", score=10
    )
    mb = FakeMB([low], None)
    handlers = build_handlers(_deps(store, mb))
    with pytest.raises(JobUnavailable):
        handlers["resolve_entity"](_JOB, "lease-1")
    assert store.resolutions == [(None, "ambiguous")]
