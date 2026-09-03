from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewSource(BaseModel):
    """A publication we draw reviews from: machine id, display name, and homepage."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    publication: str = Field(min_length=1)
    homepage_url: str = Field(pattern=r"^https://")


class SourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    crawl_allowed: bool
    requests_per_minute: int = Field(gt=0, le=120)
    retention_days: int = Field(ge=0)
    excerpt_max_chars: int = Field(gt=0, le=1000)
    attribution_required: bool = True
    removal_contact: str = Field(min_length=3)
    license_id: str = Field(min_length=1)
    license_url: str = Field(min_length=1)


def license_pool(license_id: str) -> str:
    """A source's compatibility pool is its license id.

    Two documents may be summarized into one corpus only when they share the
    same pool (identical license id); otherwise each pool is summarized
    separately and never mixed into a single claim.
    """
    return license_id.strip()


class ArtistEntity(BaseModel):
    """Canonical artist identity, independent of any review or provider."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class ReleaseEntity(BaseModel):
    """Canonical album identity a set of reviews is matched against."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    artist_id: str = Field(min_length=1)
    year: int | None = Field(default=None, ge=1900, le=2100)
    artwork_url: str | None = None


class ReviewDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    title: str = Field(min_length=1)
    author: str | None = None
    published_at: date | None = None
    score: float | None = Field(default=None, ge=0)
    score_scale: int | None = Field(default=None, gt=0)
    public_excerpt: str = Field(min_length=1)
    content: str | None = None
    policy: SourcePolicy

    @model_validator(mode="after")
    def check_source_and_excerpt(self) -> "ReviewDocument":
        if self.source_id != self.policy.source_id:
            raise ValueError("document source_id must match its source policy")
        if len(self.public_excerpt) > self.policy.excerpt_max_chars:
            raise ValueError("public excerpt exceeds the source policy limit")
        return self


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class Genre(BaseModel):
    """A genre tag attributed to the review documents that support it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class Summary(BaseModel):
    """A generated summary whose every claim cites stored review documents.

    ``kind`` distinguishes a per-source summary (``source``, with ``source_id``)
    from a cross-source consensus block (``consensus``, pooled by
    ``license_pool``). ``license_pool`` is the license id that scopes the
    summary, so incompatible licenses never share a run. ``skipped_reason`` is
    set when a consensus was legitimately not generated (fewer than two distinct
    sources in the pool).
    """

    model_config = ConfigDict(extra="forbid")

    locale: str = Field(min_length=2)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    generated_at: datetime
    corpus_hash: str = Field(min_length=1)
    claims: list[CitedClaim] = Field(min_length=1)
    kind: Literal["source", "consensus"] = "source"
    license_pool: str = ""
    license_url: str = ""
    source_id: str | None = None
    attribution: str = ""
    ai_modified: bool = True
    skipped_reason: str | None = None


class IngestedContext(BaseModel):
    """One album's full ingestion: entity, sources, reviews, and a traceable summary."""

    model_config = ConfigDict(extra="forbid")

    release: ReleaseEntity
    artist: ArtistEntity
    sources: list[ReviewSource]
    review_documents: list[ReviewDocument]
    genres: list[Genre] = Field(default_factory=list)
    summaries: list[Summary] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_consistency(self) -> "IngestedContext":
        if self.release.artist_id != self.artist.id:
            raise ValueError("release artist_id must match the context artist")
        self._check_release_links()
        self._check_sources_and_policies()
        self._check_claim_provenance()
        self._check_genre_provenance()
        return self

    def _check_release_links(self) -> None:
        misplaced = [
            document.id
            for document in self.review_documents
            if document.release_id != self.release.id
        ]
        if misplaced:
            raise ValueError(
                f"review documents reference another release: {sorted(misplaced)}"
            )

    def _check_sources_and_policies(self) -> None:
        source_ids = {source.id for source in self.sources}
        unknown_sources = {
            document.source_id
            for document in self.review_documents
            if document.source_id not in source_ids
        }
        unknown_policies = {
            document.policy.source_id
            for document in self.review_documents
            if document.policy.source_id not in source_ids
        }
        unknown = unknown_sources | unknown_policies
        if unknown:
            raise ValueError(f"references unknown sources: {sorted(unknown)}")

    def _check_claim_provenance(self) -> None:
        document_ids = {document.id for document in self.review_documents}
        missing = {
            source_id
            for summary in self.summaries
            for claim in summary.claims
            for source_id in claim.source_ids
            if source_id not in document_ids
        }
        if missing:
            raise ValueError(f"claim references unknown review documents: {sorted(missing)}")

    def _check_genre_provenance(self) -> None:
        document_ids = {document.id for document in self.review_documents}
        missing = {
            source_id
            for genre in self.genres
            for source_id in genre.source_ids
            if source_id not in document_ids
        }
        if missing:
            raise ValueError(f"genre references unknown review documents: {sorted(missing)}")
