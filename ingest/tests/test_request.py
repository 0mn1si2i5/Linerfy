"""Tests for the untrusted now-playing request model, no network."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from linerfy_ingest.request import NowPlayingRequest, normalize


def test_fingerprint_uses_provider_url_when_present() -> None:
    a = NowPlayingRequest(
        provider="spotify", title="t", artist="a", album="b",
        provider_url="spotify:track:x",
    )
    b = NowPlayingRequest(
        provider="spotify", title="t2", artist="a2", album="b2",
        provider_url="spotify:track:x",
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


def test_normalize_folds_case_and_collapses_space() -> None:
    assert normalize("  Lana   Del Rey ") == "lana del rey"
