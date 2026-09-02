"""Fixture-based tests for the CritiqueBrainz review adapter, no network."""

from __future__ import annotations

from linerfy_ingest.critiquebrainz import (
    CRITIQUEBRAINZ_POLICY,
    CritiqueBrainzAdapter,
    parse_review,
    strip_markdown,
    to_document,
)
from linerfy_ingest.models import ReleaseEntity

_PAYLOAD = {
    "reviews": [
        {
            "id": "cb-1",
            "entity_id": "rg-nfr",
            "text": "A **lush** record with a [link](https://example.com) inside.",
            "language": "en",
            "license": {"id": "CC BY-NC-SA 3.0", "url": "https://example.com/license"},
            "rating": 4,
            "user": {"display_name": "reviewer-one"},
            "created": "2019-09-03T10:00:00Z",
        }
    ]
}

_RELEASE = ReleaseEntity(
    id="norman-fucking-rockwell",
    title="Norman Fucking Rockwell!",
    artist_id="lana-del-rey",
    year=2019,
)


class FakeCB(CritiqueBrainzAdapter):
    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.urls: list[str] = []

    def _get_json(self, url: str) -> dict:
        self.urls.append(url)
        return self.payload


def test_parse_review_extracts_license_rating_and_author() -> None:
    review = parse_review(_PAYLOAD["reviews"][0])
    assert review.id == "cb-1"
    assert review.license_id == "CC BY-NC-SA 3.0"
    assert review.rating == 4
    assert review.author == "reviewer-one"
    assert review.created is not None and review.created.isoformat() == "2019-09-03"


def test_search_reviews_queries_release_group() -> None:
    adapter = FakeCB(_PAYLOAD)
    reviews = adapter.search_reviews("rg-nfr")
    assert len(reviews) == 1
    assert "release_group=rg-nfr" in adapter.urls[0]
    assert reviews[0].entity_id == "rg-nfr"


def test_strip_markdown_removes_markup_and_collapses_space() -> None:
    assert "lush" in strip_markdown("A **lush** record.")
    assert "inside." in strip_markdown("A [link](https://example.com) inside.")


def test_to_document_bounds_excerpt_and_maps_score() -> None:
    document = to_document(parse_review(_PAYLOAD["reviews"][0]), _RELEASE)
    assert document.source_id == "critiquebrainz"
    assert len(document.public_excerpt) <= CRITIQUEBRAINZ_POLICY.excerpt_max_chars
    assert document.score == 4.0
    assert document.score_scale == 5
    assert document.policy.source_id == "critiquebrainz"
