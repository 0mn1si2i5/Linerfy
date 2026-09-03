"""Untrusted now-playing request model and its dedup fingerprint.

The desktop main process sends a small, bounded metadata request when a track
is playing. It is treated as untrusted input: fields are length-capped, the
provider is validated, and the value is never interpolated into a shell or
script. Nothing here persists play history -- only the fields needed to resolve
and enrich one track.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_MAX_TEXT_CHARS = 500
_MAX_URL_CHARS = 2048
_VALID_PROVIDERS = ("spotify", "apple-music")


def normalize(value: str) -> str:
    """Case-fold and collapse whitespace for stable fingerprinting."""
    return " ".join(value.casefold().split())


class NowPlayingRequest(BaseModel):
    """A validated current-track request."""

    model_config = {"extra": "forbid"}

    provider: str
    title: str = Field(min_length=1, max_length=_MAX_TEXT_CHARS)
    artist: str = Field(min_length=1, max_length=_MAX_TEXT_CHARS)
    album: str = Field(min_length=1, max_length=_MAX_TEXT_CHARS)
    provider_url: str | None = Field(default=None, max_length=_MAX_URL_CHARS)
    state: Literal["playing", "paused"] = "playing"

    @field_validator("provider")
    @classmethod
    def _check_provider(cls, value: str) -> str:
        if value not in _VALID_PROVIDERS:
            raise ValueError(f"unsupported provider {value!r}")
        return value

    def fingerprint(self) -> str:
        """A stable dedup key for this request.

        The provider URL (Spotify ``spotify:track:...`` / Apple Music URL) is the
        most stable identity; when absent we fall back to normalized
        artist+album so different albums never collide.
        """
        if self.provider_url:
            key = f"{self.provider}:{normalize(self.provider_url)}"
        else:
            key = f"{self.provider}:{normalize(self.artist)}|{normalize(self.album)}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def lookup_key(self) -> dict[str, str]:
        """The fields handed to entity resolution."""
        return {"artist": self.artist, "album": self.album, "title": self.title}
