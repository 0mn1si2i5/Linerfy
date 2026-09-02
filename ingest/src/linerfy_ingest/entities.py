"""Entity metadata models and source policies for the v1 metadata sources.

These are the machine- and human-facing data contracts for MusicBrainz, Wikidata,
and the Cover Art Archive -- distinct from the review-source ``SourcePolicy`` in
``models.py``, because metadata sources have no excerpts or bodies to retain;
they carry a license, a rate limit, a cache TTL, and an attribution requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class MetadataSourcePolicy(BaseModel):
    """Policy for a metadata source: rate limit, cache TTL, license, attribution."""

    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1)
    requests_per_minute: int = Field(gt=0, le=120)
    cache_ttl_days: int = Field(ge=0)
    attribution_required: bool = True
    license_id: str = Field(min_length=1)
    license_url: str = Field(pattern=r"^https://")


MUSICBRAINZ_POLICY = MetadataSourcePolicy(
    source_id="musicbrainz",
    requests_per_minute=60,  # MusicBrainz allows ~1 request/second.
    cache_ttl_days=30,
    attribution_required=True,
    license_id="CC0-1.0",
    license_url="https://musicbrainz.org/doc/MusicBrainz_Licensing",
)

WIKIDATA_POLICY = MetadataSourcePolicy(
    source_id="wikidata",
    requests_per_minute=60,
    cache_ttl_days=30,
    attribution_required=True,
    license_id="CC0-1.0",
    license_url="https://www.wikidata.org/wiki/Wikidata:Copyright",
)

COVER_ART_POLICY = MetadataSourcePolicy(
    source_id="cover-art-archive",
    requests_per_minute=60,
    cache_ttl_days=30,
    attribution_required=True,
    license_id="varies",
    license_url="https://coverartarchive.org/",
)


@dataclass(frozen=True)
class ReleaseGroup:
    """A MusicBrainz release group with its metadata."""

    mbid: str
    title: str
    artist: str
    score: int | None = None
    first_release_date: str | None = None
    tags: tuple[str, ...] = ()
    rating: float | None = None
    rating_votes: int = 0
    artwork_url: str | None = None


@dataclass(frozen=True)
class EntityMatchResult:
    """The outcome of resolving a track to a release group.

    ``status`` is ``matched`` (reliable), ``unreliable`` (below threshold, never
    written as a polluted entity), or ``not-found`` (no candidate at all).
    """

    status: Literal["matched", "unreliable", "not-found"]
    release_group: ReleaseGroup | None = None
    candidates: tuple[ReleaseGroup, ...] = field(default_factory=tuple)
    reason: str | None = None
