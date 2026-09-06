"""Tests for the real stage handlers (resolve stage + handler wiring)."""

from __future__ import annotations

import pytest

from linerfy_ingest.entities import ReleaseGroup
from linerfy_ingest.jobs import EnrichmentJob, JobUnavailable
from linerfy_ingest.musicbrainz import MusicBrainzAdapter
from linerfy_ingest.pipeline import PipelineDeps, _release_slug, build_handlers
from linerfy_ingest.request import NowPlayingRequest


def test_source_groups_keep_document_license_pools_separate() -> None:
    from linerfy_ingest.pipeline import _group_by_source
    from linerfy_ingest.summarize import StoredDocument

    docs = [
        StoredDocument(
            id=str(i),
            source_id="critiquebrainz",
            license_id=pool,
            license_url="https://example.com/license",
            publication="CB",
            content="text",
        )
        for i, pool in enumerate(["CC BY-SA 3.0", "CC BY-SA 4.0"])
    ]
    groups = _group_by_source(docs)
    assert len(groups) == 2
    assert all(len(group) == 1 for group in groups.values())


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


def test_deluxe_fallback_still_requires_a_reliable_release_group() -> None:
    from linerfy_ingest.musicbrainz import resolve_release_group

    class EditionMB(FakeMB):
        def search_release_groups(self, artist, album):
            if album == "Plastic Beach (Deluxe)":
                return []
            assert album == "Plastic Beach"
            return [self.lookup_result]

    for score, expected in [(100, "matched"), (30, "unreliable")]:
        rg = ReleaseGroup(mbid="rg-1", title="Plastic Beach", artist="Gorillaz", score=score)
        result = resolve_release_group("Gorillaz", "Plastic Beach (Deluxe)", EditionMB([], rg))
        assert result.status == expected


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


def test_release_slug_keeps_ascii_readable() -> None:
    request = NowPlayingRequest(
        provider="spotify",
        title="t",
        artist="Lana Del Rey",
        album="Norman Fucking Rockwell!",
    )
    assert _release_slug(request) == "lana-del-rey-norman-fucking-rockwell"


def test_release_slug_does_not_collapse_non_ascii_names() -> None:
    jay = NowPlayingRequest(provider="spotify", title="t", artist="周杰伦", album="范特西")
    faye = NowPlayingRequest(provider="spotify", title="t", artist="王菲", album="寓言")
    # Pinned values shared with apps/web/lib/request.test.ts: both ends produce
    # the identical slug, so the read path finds what the worker wrote.
    assert _release_slug(jay) == "d1d51d7a7c5c-a23acf6103d1"
    assert _release_slug(faye) == "b7e62df3267a-114fcb616f84"
    assert _release_slug(jay) != _release_slug(faye)
