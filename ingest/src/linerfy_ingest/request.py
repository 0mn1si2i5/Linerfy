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
    """Lowercase and collapse whitespace for stable fingerprinting.

    Uses ``str.lower`` (simple case mapping) rather than ``str.casefold`` so the
    result matches the web side's ``String.prototype.toLowerCase``; the two ends
    must agree byte-for-byte on the request key (see apps/web/lib/request.ts).
    """
    return " ".join(value.lower().split())


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
        """A stable release-level dedup key for this request.

        ``provider_url`` identifies a track, while enrichment and published
        context are release-level. It therefore cannot participate in this key:
        every track on one album must resolve to the same enrichment job.

        Each field is hashed to a fixed-length hex before being combined, so a
        field containing ``:`` or ``|`` cannot collide with the separator, and
        the result matches the web side byte-for-byte (see request.ts).
        """
        artist = hashlib.sha256(normalize(self.artist).encode("utf-8")).hexdigest()
        album = hashlib.sha256(normalize(self.album).encode("utf-8")).hexdigest()
        key = f"{self.provider}:{artist}:{album}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def lookup_key(self) -> dict[str, str]:
        """The fields handed to entity resolution."""
        return {"artist": self.artist, "album": self.album, "title": self.title}
