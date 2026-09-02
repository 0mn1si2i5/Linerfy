"""CritiqueBrainz review adapter (a licensed v1 review source).

CritiqueBrainz hosts user reviews under a Creative Commons license and is
addressed through its public WS API by MusicBrainz release-group id. Reviews are
stored with their license id so the corpus provenance is explicit; the full
body stays private while a bounded excerpt is public.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
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


@dataclass(frozen=True)
class CritiqueBrainzReview:
    id: str
    entity_id: str
    text: str
    license_id: str
    language: str
    rating: int | None
    author: str
    created: date | None


def parse_review(item: dict[str, Any]) -> CritiqueBrainzReview:
    """Parse one CritiqueBrainz review object into a CritiqueBrainzReview."""
    license_info = item.get("license") or {}
    created = item.get("created")
    return CritiqueBrainzReview(
        id=item["id"],
        entity_id=item.get("entity_id", ""),
        text=item.get("text", ""),
        license_id=license_info.get("id", ""),
        language=item.get("language", "en"),
        rating=item.get("rating"),
        author=(item.get("user") or {}).get("display_name", ""),
        created=date.fromisoformat(created[:10]) if created else None,
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
    ) -> list[CritiqueBrainzReview]:
        query = urllib.parse.urlencode(
            {"release_group": release_group_mbid, "limit": limit, "fmt": "json"}
        )
        url = f"{_API_BASE}/review/?{query}"
        payload = self._get_json(url)
        return [parse_review(item) for item in payload.get("reviews", [])]


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
)


def to_document(
    review: CritiqueBrainzReview, release: ReleaseEntity
) -> ReviewDocument:
    """Wrap a CritiqueBrainz review in a ReviewDocument for the given release."""
    excerpt = strip_markdown(review.text)[: CRITIQUEBRAINZ_POLICY.excerpt_max_chars]
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
        public_excerpt=excerpt,
        content=review.text,
        policy=CRITIQUEBRAINZ_POLICY,
    )
