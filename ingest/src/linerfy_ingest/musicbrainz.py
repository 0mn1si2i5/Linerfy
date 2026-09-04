"""MusicBrainz and Cover Art Archive adapters plus release-group matching.

MusicBrainz is the v1 authority for entities, tags and ratings; the Cover Art
Archive supplies artwork as a fallback to the player's own artwork. Matching is
deliberately conservative: a result below the score threshold is reported as
``unreliable`` and never written as a polluted entity.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from .entities import EntityMatchResult, ReleaseGroup

_MB_BASE = "https://musicbrainz.org/ws/2"
_CAA_BASE = "https://coverartarchive.org"
# MusicBrainz requires an identifying, contact-bearing User-Agent.
_USER_AGENT = "Linerfy/0.1 (https://github.com/0mn1si2i5/Linerfy)"
_MIN_REQUEST_INTERVAL_SECONDS = 1.05
_RETRYABLE_HTTP_STATUS = frozenset({429, 502, 503, 504})
_MAX_ATTEMPTS = 3

# MusicBrainz Lucene search scores range 0-100; below this we refuse to match.
MATCH_THRESHOLD = 80


def _artist_name(payload: dict) -> str:
    credits = payload.get("artist-credit", [])
    if not credits:
        return ""
    return str(credits[0].get("name", "")).strip()


def front_url(release_group_mbid: str) -> str:
    """Cover Art Archive front-image URL for a release group (no HTTP needed)."""
    return f"{_CAA_BASE}/release-group/{release_group_mbid}/front"


class MusicBrainzAdapter:
    """Read-only MusicBrainz client, stubbable via ``_get_json`` for tests."""

    def __init__(
        self,
        user_agent: str = _USER_AGENT,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None

    def _wait_for_request_slot(self) -> None:
        if self._last_request_at is not None:
            remaining = (
                _MIN_REQUEST_INTERVAL_SECONDS
                - (self._clock() - self._last_request_at)
            )
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _get_json(self, url: str) -> dict:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        for attempt in range(_MAX_ATTEMPTS):
            self._wait_for_request_slot()
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if (
                    exc.code not in _RETRYABLE_HTTP_STATUS
                    or attempt == _MAX_ATTEMPTS - 1
                ):
                    raise
        raise AssertionError("unreachable")

    def search_release_groups(self, artist: str, album: str) -> list[ReleaseGroup]:
        query = f'releasegroup:"{album}" AND artist:"{artist}"'
        url = (
            f"{_MB_BASE}/release-group/?query={urllib.parse.quote(query)}"
            f"&fmt=json&limit=5"
        )
        payload = self._get_json(url)
        return [
            ReleaseGroup(
                mbid=item["id"],
                title=item.get("title", ""),
                artist=_artist_name(item),
                score=item.get("score"),
                first_release_date=item.get("first-release-date"),
            )
            for item in payload.get("release-groups", [])
        ]

    def get_release_group(self, mbid: str) -> ReleaseGroup:
        url = f"{_MB_BASE}/release-group/{mbid}?inc=tags+ratings+artist-credits&fmt=json"
        payload = self._get_json(url)
        rating = payload.get("rating", {}) or {}
        tags = tuple(item["name"] for item in payload.get("tags", []))
        return ReleaseGroup(
            mbid=mbid,
            title=payload.get("title", ""),
            artist=_artist_name(payload),
            first_release_date=payload.get("first-release-date"),
            tags=tags,
            rating=rating.get("value"),
            rating_votes=rating.get("votes-count", 0) or 0,
            artwork_url=front_url(mbid),
        )


def resolve_release_group(
    artist: str, album: str, adapter: MusicBrainzAdapter
) -> EntityMatchResult:
    """Resolve a track's artist+album to a MusicBrainz release group, or refuse.

    Only a result whose search score meets ``MATCH_THRESHOLD`` is treated as a
    match. Anything below the threshold, or with no candidates, is returned as
    ``unreliable``/``not-found`` so callers never persist a guessed entity.
    """
    candidates = adapter.search_release_groups(artist, album)
    if not candidates:
        return EntityMatchResult(
            status="not-found",
            reason="no MusicBrainz release group matched the query",
        )

    top = candidates[0]
    if top.score is None or top.score < MATCH_THRESHOLD:
        return EntityMatchResult(
            status="unreliable",
            candidates=tuple(candidates),
            reason=f"top score {top.score} is below threshold {MATCH_THRESHOLD}",
        )

    enriched = adapter.get_release_group(top.mbid)
    return EntityMatchResult(status="matched", release_group=enriched)
