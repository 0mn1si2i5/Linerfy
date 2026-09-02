from pathlib import Path

import pytest
from pydantic import ValidationError

from linerfy_ingest import FixtureSourceAdapter, IngestedContext

FIXTURE = Path(__file__).parent.parent / "fixtures" / "reviews.json"


def load_context() -> IngestedContext:
    return FixtureSourceAdapter(FIXTURE).fetch()


def test_fixture_adapter_loads_full_entity_linked_context() -> None:
    context = load_context()

    assert context.release.title == "Norman Fucking Rockwell!"
    assert context.artist.name == "Lana Del Rey"
    assert len(context.review_documents) == 2
    assert len(context.summary.claims) == 1
    assert {genre.name for genre in context.genres} == {
        "Singer-Songwriter",
        "Psychedelic Pop",
    }


def test_every_document_belongs_to_the_release() -> None:
    context = load_context()

    assert all(document.release_id == context.release.id for document in context.review_documents)


def test_excerpts_respect_each_source_policy_limit() -> None:
    context = load_context()

    for document in context.review_documents:
        assert len(document.public_excerpt) <= document.policy.excerpt_max_chars


def test_claim_must_reference_an_ingested_document() -> None:
    context = load_context()

    data = context.model_dump()
    data["summary"]["claims"] = [{"text": "Claim", "source_ids": ["missing"]}]

    with pytest.raises(ValidationError, match="unknown review documents"):
        IngestedContext.model_validate(data)


def test_genre_must_reference_an_ingested_document() -> None:
    context = load_context()

    data = context.model_dump()
    data["genres"] = [{"name": "Noise", "source_ids": ["missing"]}]

    with pytest.raises(ValidationError, match="unknown review documents"):
        IngestedContext.model_validate(data)


def test_release_artist_link_is_enforced() -> None:
    context = load_context()

    data = context.model_dump()
    data["release"]["artist_id"] = "someone-else"

    with pytest.raises(ValidationError, match="artist_id"):
        IngestedContext.model_validate(data)
