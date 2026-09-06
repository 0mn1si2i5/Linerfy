"""CritiqueBrainz review adapter (a licensed v1 review source).

CritiqueBrainz hosts user reviews under a Creative Commons license and is
addressed through its public WS API by MusicBrainz release-group id. Reviews are
stored with their *document-level* license id (read from the response, never
hard-coded); the full body stays private while a bounded excerpt is public.

The listing response also carries an official ``average_rating`` (value + count)
that becomes the source's rating snapshot; individual per-review ratings are not
averaged here because they are a partial page, not the whole population.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any

from .models import (
    ReleaseEntity,
    ReviewDocument,
    ReviewSource,
    SourcePolicy,
)

_API_BASE = "https://critiquebrainz.org/ws/1"
_USER_AGENT = "Linerfy/0.0 (music-criticism companion; rights@linerfy.local)"

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_markdown(raw: str) -> str:
    """Best-effort plain-text extraction for a review's public excerpt."""
    text = _MARKDOWN_LINK_RE.sub(r"\1", raw)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return " ".join(line for line in lines if line).strip()


def _parse_created(created: str | None) -> date | None:
    """Parse a review's ``created`` field (ISO datetime or RFC 1123 HTTP date).

    The real listing returns HTTP dates like "Fri, 06 Mar 2026 04:06:52 GMT";
    older hand-written fixtures use ISO. Unknown formats raise a source-level
    controlled error rather than guessing a date or crashing the whole fetch.
    """
    if not created:
        return None
    iso = created[:10]
    try:
        return date.fromisoformat(iso)
    except ValueError:
        pass
    parsed = parsedate_to_datetime(created)
    if parsed is not None:
        return parsed.date()
    raise ValueError(f"unrecognized created format: {created!r}")


@dataclass(frozen=True)
class CritiqueBrainzReview:
    id: str
    entity_id: str
    entity_type: str
    text: str
    license_id: str
    license_url: str
    language: str
    rating: int | None
    author: str
    created: date | None


@dataclass(frozen=True)
class CritiqueBrainzListing:
    """A listing response: its reviews plus the official aggregate rating."""

    reviews: tuple[CritiqueBrainzReview, ...]
    average_rating: float | None
    rating_count: int


def parse_review(item: dict[str, Any]) -> CritiqueBrainzReview:
    """Parse one CritiqueBrainz review object into a CritiqueBrainzReview."""
    return CritiqueBrainzReview(
        id=item["id"],
        entity_id=item.get("entity_id", ""),
        entity_type=item.get("entity_type", ""),
        text=item.get("text") or "",
        license_id=item.get("license_id") or (item.get("license") or {}).get("id", ""),
        license_url=item.get("info_url") or (item.get("license") or {}).get("url", ""),
        language=item.get("language", "en"),
        rating=item.get("rating"),
        author=(item.get("user") or {}).get("display_name", ""),
        created=_parse_created(item.get("created")),
    )


class CritiqueBrainzAdapter:
    """Read-only CritiqueBrainz client, stubbable via ``_get_json`` for tests."""

    def __init__(self, user_agent: str = _USER_AGENT) -> None:
        self.user_agent = user_agent

    def _get_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent, "Accept": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def search_reviews(
        self, release_group_mbid: str, limit: int = 10
    ) -> CritiqueBrainzListing:
        query = urllib.parse.urlencode(
            {"release_group": release_group_mbid, "limit": limit, "fmt": "json"}
        )
        url = f"{_API_BASE}/review/?{query}"
        payload = self._get_json(url)

        # Only reviews whose entity_id/type match the target are kept; a
        # mislabelled review must not be stored or summarized just because it
        # came back from a query filtered by release_group.
        reviews = tuple(
            parse_review(item)
            for item in payload.get("reviews", [])
            if item.get("entity_id") == release_group_mbid
            and item.get("entity_type") == "release_group"
        )
        aggregate = payload.get("average_rating") or {}
        return CritiqueBrainzListing(
            reviews=reviews,
            average_rating=aggregate.get("rating"),
            rating_count=aggregate.get("count", 0) or 0,
        )


CRITIQUEBRAINZ_SOURCE = ReviewSource(
    id="critiquebrainz",
    publication="CritiqueBrainz",
    homepage_url="https://critiquebrainz.org",
)

CRITIQUEBRAINZ_POLICY = SourcePolicy(
    source_id="critiquebrainz",
    crawl_allowed=True,
    requests_per_minute=20,
    retention_days=30,
    excerpt_max_chars=280,
    attribution_required=True,
    removal_contact="rights@linerfy.local",
    license_id="CC BY-SA 3.0",
    license_url="https://creativecommons.org/licenses/by-sa/3.0/",
)


def to_document(
    review: CritiqueBrainzReview, release: ReleaseEntity
) -> ReviewDocument | None:
    """Wrap a text-bearing CritiqueBrainz review in a ReviewDocument.

    A rating-only review (no body) is not a review document and must not be
    summarized: it returns ``None`` so the caller can record its rating without
    inventing an empty excerpt or a model call.
    """
    excerpt = strip_markdown(review.text)
    if not excerpt:
        return None
    # Missing license metadata is not permission to assume the provider default.
    known_urls = {
        "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
        "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
        "CC BY-NC-SA 3.0": "https://creativecommons.org/licenses/by-nc-sa/3.0/",
    }
    license_url = known_urls.get(review.license_id)
    if not license_url:
        return None
    return ReviewDocument(
        id=f"critiquebrainz-{review.id}",
        release_id=release.id,
        source_id=CRITIQUEBRAINZ_SOURCE.id,
        source_url=f"https://critiquebrainz.org/review/{review.id}",
        title=f"CritiqueBrainz review of {release.title}",
        author=review.author or None,
        published_at=review.created,
        score=float(review.rating) if review.rating is not None else None,
        score_scale=5 if review.rating is not None else None,
        public_excerpt=excerpt[: CRITIQUEBRAINZ_POLICY.excerpt_max_chars],
        content=review.text,
        license_id=review.license_id,
        license_url=license_url,
        policy=CRITIQUEBRAINZ_POLICY,
    )
