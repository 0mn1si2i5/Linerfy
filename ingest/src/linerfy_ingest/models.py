from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    crawl_allowed: bool
    requests_per_minute: int = Field(gt=0, le=120)
    retention_days: int = Field(ge=0)
    excerpt_max_chars: int = Field(gt=0, le=1000)
    attribution_required: bool = True
    removal_contact: str = Field(min_length=3)


class ReviewDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    title: str = Field(min_length=1)
    author: str | None = None
    published_at: date | None = None
    public_excerpt: str = Field(min_length=1)
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


class IngestedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_documents: list[ReviewDocument]
    claims: list[CitedClaim]

    @model_validator(mode="after")
    def check_claim_provenance(self) -> "IngestedContext":
        document_ids = {document.id for document in self.review_documents}
        missing = {
            source_id
            for claim in self.claims
            for source_id in claim.source_ids
            if source_id not in document_ids
        }
        if missing:
            raise ValueError(f"claim references unknown review documents: {sorted(missing)}")
        return self
