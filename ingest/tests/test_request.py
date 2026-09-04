"""Tests for the untrusted now-playing request model, no network."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from linerfy_ingest.request import NowPlayingRequest, normalize


def test_fingerprint_deduplicates_tracks_from_the_same_album() -> None:
    a = NowPlayingRequest(
        provider="spotify", title="t1", artist="a", album="b",
        provider_url="spotify:track:1",
    )
    b = NowPlayingRequest(
        provider="spotify", title="t2", artist="a", album="b",
        provider_url="spotify:track:2",
    )
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_differs_by_album() -> None:
    a = NowPlayingRequest(provider="spotify", title="t", artist="A", album="B")
    b = NowPlayingRequest(provider="spotify", title="t", artist="A", album="C")
    assert a.fingerprint() != b.fingerprint()


def test_fingerprint_normalizes_case_and_whitespace() -> None:
    a = NowPlayingRequest(provider="spotify", title="t", artist="Lana Del Rey", album="NFR")
    b = NowPlayingRequest(provider="spotify", title="t", artist="  lana   del rey ", album="nfr")
    assert a.fingerprint() == b.fingerprint()


def test_rejects_unsupported_provider() -> None:
    with pytest.raises(ValidationError):
        NowPlayingRequest(provider="youtube", title="t", artist="a", album="b")


def test_rejects_overlong_field() -> None:
    with pytest.raises(ValidationError):
        NowPlayingRequest(provider="spotify", title="x" * 501, artist="a", album="b")


def test_lookup_key_returns_resolution_fields() -> None:
    request = NowPlayingRequest(provider="spotify", title="t", artist="a", album="b")
    assert request.lookup_key() == {"artist": "a", "album": "b", "title": "t"}


def test_accepts_web_ingest_payload_shape() -> None:
    """The web API persists the snake_case payload produced by toIngestPayload."""
    request = NowPlayingRequest.model_validate(
        {
            "provider": "spotify",
            "title": "Mariners Apartment Complex",
            "artist": "Lana Del Rey",
            "album": "Norman Fucking Rockwell!",
            "state": "playing",
            "provider_url": "spotify:track:123",
        }
    )
    assert request.provider_url == "spotify:track:123"


def test_rejects_camel_case_provider_url() -> None:
    """The ingest contract is snake_case; a camelCase `providerUrl` must be
    mapped at the web boundary before it is persisted."""
    with pytest.raises(ValidationError):
        NowPlayingRequest.model_validate(
            {
                "provider": "spotify",
                "title": "t",
                "artist": "a",
                "album": "b",
                "providerUrl": "spotify:track:123",
            }
        )


def test_normalize_folds_case_and_collapses_space() -> None:
    assert normalize("  Lana   Del Rey ") == "lana del rey"
