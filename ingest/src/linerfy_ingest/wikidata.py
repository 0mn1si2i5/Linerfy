"""Minimal Wikidata adapter for entity mapping.

Wikidata links an entity to its MusicBrainz release-group id (property P436),
so an incoming Wikipedia/Wikidata mention can be resolved to the catalog entity.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

_WD_API = "https://www.wikidata.org/w/api.php"
_USER_AGENT = "Linerfy/0.0 (music-criticism companion; rights@linerfy.local)"
_MUSICBRAINZ_RELEASE_GROUP_PROP = "P436"


class WikidataAdapter:
    """Read-only Wikidata client, stubbable via ``_get_json`` for tests."""

    def __init__(self, user_agent: str = _USER_AGENT) -> None:
        self.user_agent = user_agent

    def _get_json(self, url: str) -> dict:
        request = urllib.request.Request(
            url, headers={"User-Agent": self.user_agent}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def search_entities(self, query: str, limit: int = 5) -> list[dict]:
        url = (
            f"{_WD_API}?action=wbsearchentities&search={urllib.parse.quote(query)}"
            f"&language=en&format=json&limit={limit}"
        )
        payload = self._get_json(url)
        return [
            {
                "id": item["id"],
                "label": item.get("label", ""),
                "description": item.get("description", ""),
            }
            for item in payload.get("search", [])
        ]

    def musicbrainz_release_group_id(self, qid: str) -> str | None:
        url = f"{_WD_API}?action=wbgetentities&ids={qid}&props=claims&format=json"
        payload = self._get_json(url)
        claims = payload.get("entities", {}).get(qid, {}).get("claims", {})
        for claim in claims.get(_MUSICBRAINZ_RELEASE_GROUP_PROP, []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if value:
                return str(value)
        return None
