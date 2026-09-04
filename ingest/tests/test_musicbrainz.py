"""Fixture-based tests for the MusicBrainz adapter and matching, with no network."""

from __future__ import annotations

import io
import urllib.error

import pytest

import linerfy_ingest.musicbrainz as musicbrainz_module
from linerfy_ingest.musicbrainz import (
    MATCH_THRESHOLD,
    MusicBrainzAdapter,
    front_url,
    resolve_release_group,
)

_SEARCH_PAYLOAD = {
    "release-groups": [
        {
            "id": "rg-nfr",
            "title": "Norman Fucking Rockwell!",
            "score": 100,
            "first-release-date": "2019-08-30",
            "artist-credit": [{"name": "Lana Del Rey", "joinphrase": ""}],
        },
        {
            "id": "rg-other",
            "title": "Norman Fucking Rockwell! (Deluxe)",
            "score": 60,
            "artist-credit": [{"name": "Lana Del Rey", "joinphrase": ""}],
        },
    ]
}

_LOOKUP_PAYLOAD = {
    "id": "rg-nfr",
    "title": "Norman Fucking Rockwell!",
    "first-release-date": "2019-08-30",
    "artist-credit": [{"name": "Lana Del Rey", "joinphrase": ""}],
    "tags": [{"name": "art pop"}, {"name": "baroque pop"}],
    "rating": {"value": 4.2, "votes-count": 87},
}


class FakeMB(MusicBrainzAdapter):
    def __init__(self, payloads: dict[str, dict]):
        super().__init__()
        self.payloads = payloads
        self.urls: list[str] = []

    def _get_json(self, url: str) -> dict:
        self.urls.append(url)
        if "release-group/" in url and "query=" not in url:
            return self.payloads["lookup"]
        return self.payloads["search"]


def _fake() -> FakeMB:
    return FakeMB({"search": _SEARCH_PAYLOAD, "lookup": _LOOKUP_PAYLOAD})


def test_front_url_constructs_cover_art_archive_url() -> None:
    assert front_url("rg-nfr") == "https://coverartarchive.org/release-group/rg-nfr/front"


def test_search_parses_release_groups() -> None:
    results = _fake().search_release_groups("Lana Del Rey", "Norman Fucking Rockwell!")
    assert len(results) == 2
    assert results[0].mbid == "rg-nfr"
    assert results[0].artist == "Lana Del Rey"
    assert results[0].score == 100


def test_lookup_enriches_tags_and_rating() -> None:
    group = _fake().get_release_group("rg-nfr")
    assert group.tags == ("art pop", "baroque pop")
    assert group.rating == 4.2
    assert group.rating_votes == 87
    assert group.artwork_url == "https://coverartarchive.org/release-group/rg-nfr/front"


def test_resolve_matches_a_high_score_release_group() -> None:
    result = resolve_release_group("Lana Del Rey", "Norman Fucking Rockwell!", _fake())
    assert result.status == "matched"
    assert result.release_group is not None
    assert result.release_group.mbid == "rg-nfr"
    assert result.release_group.rating_votes == 87


def test_resolve_refuses_a_low_score_result() -> None:
    payload = {
        "search": {"release-groups": [_SEARCH_PAYLOAD["release-groups"][1]]},
        "lookup": _LOOKUP_PAYLOAD,
    }
    result = resolve_release_group("Lana Del Rey", "Norman Fucking Rockwell!", FakeMB(payload))
    assert result.status == "unreliable"
    assert result.release_group is None
    assert result.reason is not None and str(MATCH_THRESHOLD) in result.reason


def test_resolve_reports_not_found_without_candidates() -> None:
    payload = {"search": {"release-groups": []}, "lookup": _LOOKUP_PAYLOAD}
    result = resolve_release_group("Nobody", "No Album", FakeMB(payload))
    assert result.status == "not-found"
    assert result.release_group is None


class _Response:
    def __init__(self, payload: bytes = b"{}") -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_adapter_spaces_consecutive_musicbrainz_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(
        musicbrainz_module.urllib.request,
        "urlopen",
        lambda request, timeout: _Response(),
    )
    adapter = MusicBrainzAdapter(clock=lambda: now[0], sleep=sleep)

    adapter._get_json("https://musicbrainz.org/first")
    adapter._get_json("https://musicbrainz.org/second")

    assert sleeps == [pytest.approx(1.05)]


def test_adapter_retries_a_transient_503_after_rate_limit_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [10.0]
    sleeps: list[float] = []
    calls = 0

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    def urlopen(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(
                request.full_url, 503, "busy", {}, io.BytesIO()
            )
        return _Response(b'{"release-groups": []}')

    monkeypatch.setattr(musicbrainz_module.urllib.request, "urlopen", urlopen)
    adapter = MusicBrainzAdapter(clock=lambda: now[0], sleep=sleep)

    assert adapter._get_json("https://musicbrainz.org/retry") == {
        "release-groups": []
    }
    assert calls == 2
    assert sleeps == [pytest.approx(1.05)]
