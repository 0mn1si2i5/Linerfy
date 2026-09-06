"""Fixture-based tests for the CritiqueBrainz review adapter, no network.

Fixtures mirror the real listing shape: top-level ``license_id``, an
``entity_type`` of ``release_group``, an RFC 1123 ``created`` HTTP date, and a
rating-only review whose ``text`` is null.
"""

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
    "average_rating": {"rating": 4.0, "count": 4},
    "reviews": [
        {
            "id": "cb-1",
            "entity_id": "rg-nfr",
            "entity_type": "release_group",
            "text": "A **lush** record with a [link](https://example.com) inside.",
            "language": "en",
            "license_id": "CC BY-SA 3.0",
            "info_url": "https://creativecommons.org/licenses/by-sa/3.0/",
            "rating": 4,
            "user": {"display_name": "reviewer-one"},
            "created": "Fri, 06 Mar 2026 04:06:52 GMT",
        },
        {
            "id": "cb-2",
            "entity_id": "rg-nfr",
            "entity_type": "release_group",
            "text": None,
            "language": "en",
            "license_id": "CC BY-SA 3.0",
            "info_url": "https://creativecommons.org/licenses/by-sa/3.0/",
            "rating": 5,
            "user": {"display_name": "reviewer-two"},
            "created": "Fri, 06 Mar 2026 04:06:52 GMT",
        },
        {
            "id": "cb-wrong",
            "entity_id": "rg-other",
            "entity_type": "release_group",
            "text": "This belongs to another release group.",
            "language": "en",
            "license_id": "CC BY-SA 3.0",
            "info_url": "https://creativecommons.org/licenses/by-sa/3.0/",
            "rating": 3,
            "user": {"display_name": "reviewer-three"},
            "created": "Fri, 06 Mar 2026 04:06:52 GMT",
        },
    ],
}

_RELEASE = ReleaseEntity(
    id="norman-fucking-rockwell",
    title="Norman Fucking Rockwell!",
    artist_id="lana-del-rey",
    year=2019,
)


def test_unknown_license_does_not_fall_back_to_provider_default() -> None:
    review = parse_review({**_PAYLOAD["reviews"][0], "license_id": "unknown"})
    assert to_document(review, _RELEASE) is None


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
    assert review.license_id == "CC BY-SA 3.0"
    assert review.license_url == "https://creativecommons.org/licenses/by-sa/3.0/"
    assert review.rating == 4
    assert review.author == "reviewer-one"
    assert review.created is not None and review.created.isoformat() == "2026-03-06"


def test_parse_review_parses_iso_created_for_legacy_fixtures() -> None:
    review = parse_review(
        {
            "id": "cb-iso",
            "entity_id": "rg-nfr",
            "entity_type": "release_group",
            "text": "body",
            "license_id": "CC BY-SA 3.0",
            "rating": 4,
            "user": {"display_name": "a"},
            "created": "2019-09-03T10:00:00Z",
        }
    )
    assert review.created is not None and review.created.isoformat() == "2019-09-03"


def test_search_reviews_keeps_only_matching_entities_and_rating() -> None:
    adapter = FakeCB(_PAYLOAD)
    listing = adapter.search_reviews("rg-nfr")
    assert [r.id for r in listing.reviews] == ["cb-1", "cb-2"]
    assert listing.average_rating == 4.0
    assert listing.rating_count == 4


def test_strip_markdown_removes_markup_and_collapses_space() -> None:
    assert "lush" in strip_markdown("A **lush** record.")
    assert "inside." in strip_markdown("A [link](https://example.com) inside.")


def test_to_document_bounds_excerpt_and_maps_score() -> None:
    document = to_document(parse_review(_PAYLOAD["reviews"][0]), _RELEASE)
    assert document is not None
    assert document.source_id == "critiquebrainz"
    assert len(document.public_excerpt) <= CRITIQUEBRAINZ_POLICY.excerpt_max_chars
    assert document.score == 4.0
    assert document.score_scale == 5
    assert document.license_id == "CC BY-SA 3.0"
    assert document.policy.source_id == "critiquebrainz"


def test_to_document_returns_none_for_rating_only_review() -> None:
    document = to_document(parse_review(_PAYLOAD["reviews"][1]), _RELEASE)
    assert document is None
