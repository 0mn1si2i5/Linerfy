from pathlib import Path

import pytest
from pydantic import ValidationError

from linerfy_ingest import (
    CitedClaim,
    FixtureSourceAdapter,
    IngestedContext,
    ReviewDocument,
)


def test_claims_must_reference_an_ingested_document() -> None:
    with pytest.raises(ValidationError):
        IngestedContext(
            review_documents=[],
            claims=[CitedClaim(text="Claim", source_ids=["missing"])],
        )


def test_fixture_adapter_preserves_policy_and_public_excerpt() -> None:
    fixture = Path(__file__).parent.parent / "fixtures" / "reviews.json"

    documents = FixtureSourceAdapter(fixture).fetch()

    assert len(documents) == 2
    assert all(isinstance(document, ReviewDocument) for document in documents)
    assert documents[0].policy.excerpt_max_chars == 280
    assert len(documents[0].public_excerpt) <= documents[0].policy.excerpt_max_chars
    assert documents[0].source_url.startswith("https://")
