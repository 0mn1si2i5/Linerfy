"""Wikipedia Reception-section adapter (a licensed v1 review source).

Only the article's critical-reception section is fetched, through the official
MediaWiki API, and treated as a corpus document under CC BY-SA. The adapter
extracts readable plain text from wikitext; nothing is scraped from the rendered
page.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import (
    ReleaseEntity,
    ReviewDocument,
    ReviewSource,
    SourcePolicy,
)

_API_BASE = "https://en.wikipedia.org/w/api.php"
_USER_AGENT = "Linerfy/0.0 (music-criticism companion; rights@linerfy.local)"

# Section headings that carry the critical reception.
_RECEPTION_HEADINGS = (
    "reception",
    "critical reception",
    "critical response",
    "critical reviews",
    "reception and legacy",
)

_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL | re.IGNORECASE)
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
_LINK_RE = re.compile(r"\[\[([^\]|]*\|)?([^\]]*)\]\]")
_TAG_RE = re.compile(r"<[^>]+>")


def strip_wikitext(raw: str) -> str:
    """Extract plain text from a section's wikitext.

    This is a conservative, best-effort cleanup for corpus use: references and
    templates are removed, wiki links collapse to their visible label, and the
    result is whitespace-normalised.
    """
    text = _REF_RE.sub("", raw)
    # Nested templates are rare in reception prose; strip a bounded depth.
    for _ in range(4):
        text = _TEMPLATE_RE.sub("", text)
    text = _LINK_RE.sub(lambda m: m.group(2) or m.group(1) or "", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("'''", "").replace("''", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return " ".join(line for line in lines if line).strip()


@dataclass(frozen=True)
class ReceptionSection:
    title: str
    plain_text: str


class WikipediaAdapter:
    """Read-only MediaWiki client, stubbable via ``_get_json`` for tests."""

    def __init__(self, user_agent: str = _USER_AGENT) -> None:
        self.user_agent = user_agent

    def _get_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_sections(self, title: str) -> list[dict[str, Any]]:
        url = (
            f"{_API_BASE}?action=parse&page={urllib.parse.quote(title)}"
            f"&prop=sections&format=json"
        )
        payload = self._get_json(url)
        return payload.get("parse", {}).get("sections", [])

    def section_wikitext(self, title: str, index: str) -> str:
        url = (
            f"{_API_BASE}?action=parse&page={urllib.parse.quote(title)}"
            f"&prop=wikitext&section={index}&format=json"
        )
        payload = self._get_json(url)
        return payload.get("parse", {}).get("wikitext", {}).get("*", "")

    def reception_section(self, title: str) -> ReceptionSection | None:
        """Return the critical-reception section, or None when absent."""
        for section in self.list_sections(title):
            line = (section.get("line") or "").strip().lower()
            if line in _RECEPTION_HEADINGS:
                index = str(section.get("index", ""))
                if index:
                    wikitext = self.section_wikitext(title, index)
                    return ReceptionSection(
                        title=section.get("line", "Reception"),
                        plain_text=strip_wikitext(wikitext),
                    )
        return None


WIKIPEDIA_SOURCE = ReviewSource(
    id="wikipedia",
    publication="Wikipedia",
    homepage_url="https://en.wikipedia.org",
)

WIKIPEDIA_POLICY = SourcePolicy(
    source_id="wikipedia",
    crawl_allowed=True,
    requests_per_minute=30,
    retention_days=30,
    excerpt_max_chars=280,
    attribution_required=True,
    removal_contact="rights@linerfy.local",
    license_id="CC BY-SA 4.0",
    license_url="https://creativecommons.org/licenses/by-sa/4.0/",
)


def page_url(title: str) -> str:
    """Canonical Wikipedia URL for an article title."""
    return f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def to_document(
    section: ReceptionSection, release: ReleaseEntity, article_title: str
) -> ReviewDocument:
    """Wrap a reception section in a ReviewDocument for the given release."""
    excerpt = section.plain_text[: WIKIPEDIA_POLICY.excerpt_max_chars]
    return ReviewDocument(
        id=f"wikipedia-{release.id}-reception",
        release_id=release.id,
        source_id=WIKIPEDIA_SOURCE.id,
        source_url=page_url(article_title),
        title=f"{release.title} — {section.title}",
        author=None,
        published_at=None,
        score=None,
        score_scale=None,
        public_excerpt=excerpt,
        content=section.plain_text,
        policy=WIKIPEDIA_POLICY,
    )
