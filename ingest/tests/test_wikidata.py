"""Fixture-based tests for the minimal Wikidata entity-mapping adapter."""

from __future__ import annotations

from linerfy_ingest.wikidata import WikidataAdapter


class FakeWikidata(WikidataAdapter):
    def __init__(self, search_payload: dict, entity_payload: dict):
        super().__init__()
        self.search_payload = search_payload
        self.entity_payload = entity_payload

    def _get_json(self, url: str) -> dict:
        if "wbsearchentities" in url:
            return self.search_payload
        return self.entity_payload


def test_search_entities_returns_qid_label_description() -> None:
    adapter = FakeWikidata(
        {"search": [{"id": "Q123", "label": "Norman Fucking Rockwell!", "description": "album"}]},
        {},
    )
    results = adapter.search_entities("Norman Fucking Rockwell")
    assert results == [{"id": "Q123", "label": "Norman Fucking Rockwell!", "description": "album"}]


def test_musicbrainz_release_group_id_extracts_p436() -> None:
    adapter = FakeWikidata(
        {},
        {
            "entities": {
                "Q123": {
                    "claims": {
                        "P436": [{"mainsnak": {"datavalue": {"value": "rg-nfr"}}}]
                    }
                }
            }
        },
    )
    assert adapter.musicbrainz_release_group_id("Q123") == "rg-nfr"


def test_musicbrainz_release_group_id_is_none_when_absent() -> None:
    adapter = FakeWikidata({}, {"entities": {"Q456": {"claims": {}}}})
    assert adapter.musicbrainz_release_group_id("Q456") is None
