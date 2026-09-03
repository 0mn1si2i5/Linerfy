"""Legacy Guardian adapter — disabled in v1, not part of the production pipeline.

The Guardian is not a cleared v1 source (the v1 sources are MusicBrainz,
Wikidata, Cover Art Archive, CritiqueBrainz, and Wikipedia Reception). This
adapter is retained only for reference; it is not wired into the CLI or any
stage handler, and it must not be used for acceptance.
"""

from __future__ import annotations

import html
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any

from .models import (
    ArtistEntity,
    IngestedContext,
    ReleaseEntity,
    ReviewDocument,
    ReviewSource,
    SourcePolicy,
)

_API_BASE = "https://content.guardianapis.com"
_SHOW_FIELDS = (
    "body,trailText,byline,starRating,headline,publication,firstPublicationDate"
)

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_BREAK_RE = re.compile(
    r"</?(?:p|div|blockquote|h[1-6]|li|br)\b[^>]*>", re.IGNORECASE
)


def strip_html(raw: str) -> str:
    """Turn an article's HTML body into plain text for the private store."""
    text = _BLOCK_BREAK_RE.sub("\n", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


@dataclass(frozen=True)
class GuardianReview:
    title: str
    author: str
    score: int
    score_scale: int
    url: str
    published_at: date
    body_text: str
    trail_text: str


def parse_content(content: dict[str, Any]) -> GuardianReview:
    """Parse one Guardian ``content`` object into a GuardianReview."""
    fields = content.get("fields", {})
    body_text = strip_html(fields.get("body", ""))
    return GuardianReview(
        title=content["webTitle"],
        author=fields.get("byline") or "",
        score=int(fields["starRating"]),
        score_scale=5,
        url=content["webUrl"],
        published_at=date.fromisoformat(content["webPublicationDate"][:10]),
        body_text=body_text,
        trail_text=(fields.get("trailText") or "").strip(),
    )


class GuardianAdapter:
    """Read one Guardian article by its Content API path."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("GUARDIAN_API_KEY is required")
        self.api_key = api_key

    def fetch_review(self, article_path: str) -> GuardianReview:
        url = (
            f"{_API_BASE}/{article_path}"
            f"?show-fields={_SHOW_FIELDS}&api-key={self.api_key}"
        )
        return parse_content(self._get_json(url)["response"]["content"])

    def _get_json(self, url: str) -> dict[str, Any]:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


GUARDIAN_SOURCE = ReviewSource(
    id="guardian",
    publication="The Guardian",
    homepage_url="https://www.theguardian.com",
)

GUARDIAN_POLICY = SourcePolicy(
    source_id="guardian",
    crawl_allowed=True,
    requests_per_minute=10,
    retention_days=30,
    excerpt_max_chars=280,
    attribution_required=True,
    removal_contact="rights@linerfy.local",
    license_id="proprietary",
    license_url="https://www.theguardian.com/help/terms-of-service",
)

# Entity matching is a later slice; this hardcodes the one album the adapter is
# first run against.
_ARTIST = ArtistEntity(id="lana-del-rey", name="Lana Del Rey")
_RELEASE = ReleaseEntity(
    id="norman-fucking-rockwell",
    title="Norman Fucking Rockwell!",
    artist_id="lana-del-rey",
    year=2019,
)


def build_context(review: GuardianReview) -> IngestedContext:
    """Wrap one fetched review in a summary-less context for the NFR album."""
    excerpt_source = review.trail_text or review.body_text
    document = ReviewDocument(
        id="guardian-nfr",
        release_id=_RELEASE.id,
        source_id=GUARDIAN_SOURCE.id,
        source_url=review.url,
        title=review.title,
        author=review.author or None,
        published_at=review.published_at,
        score=review.score,
        score_scale=review.score_scale,
        public_excerpt=excerpt_source[: GUARDIAN_POLICY.excerpt_max_chars],
        content=review.body_text,
        policy=GUARDIAN_POLICY,
    )
    return IngestedContext(
        release=_RELEASE,
        artist=_ARTIST,
        sources=[GUARDIAN_SOURCE],
        review_documents=[document],
    )
