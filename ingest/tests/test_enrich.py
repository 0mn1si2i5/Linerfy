"""Integration test composing entity resolution + source fetch + summarization.

Uses the real adapter and summarizer code with fakes for the network and model,
so a single test proves the v1 pipeline contracts line up end to end.
"""

from __future__ import annotations

import json

from linerfy_ingest.critiquebrainz import CritiqueBrainzAdapter
from linerfy_ingest.critiquebrainz import to_document as cb_document
from linerfy_ingest.enrich import corpus_from_documents, enrich_release
from linerfy_ingest.entities import ReleaseGroup
from linerfy_ingest.models import ReleaseEntity
from linerfy_ingest.providers import ChatResult
from linerfy_ingest.wikipedia import WikipediaAdapter

_RELEASE = ReleaseEntity(
    id="norman-fucking-rockwell",
    title="Norman Fucking Rockwell!",
    artist_id="lana-del-rey",
    year=2019,
)
_RELEASE_GROUP = ReleaseGroup(
    mbid="rg-nfr", title="Norman Fucking Rockwell!", artist="Lana Del Rey"
)

_CB_PAYLOAD = {
    "reviews": [
        {
            "id": "cb-1",
            "entity_id": "rg-nfr",
            "text": "A lush, sprawling record.",
            "language": "en",
            "license": {"id": "CC BY-NC-SA 3.0"},
            "rating": 4,
            "user": {"display_name": "reviewer-one"},
            "created": "2019-09-03T10:00:00Z",
        }
    ]
}
_WIKI_SECTIONS = {
    "parse": {"sections": [{"index": "1", "line": "Critical reception", "level": "2"}]}
}
_WIKI_TEXT = {"parse": {"wikitext": {"*": "Praised for its songwriting and restraint."}}}


class FakeCB(CritiqueBrainzAdapter):
    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload

    def _get_json(self, url: str) -> dict:
        return self.payload


class FakeWiki(WikipediaAdapter):
    def __init__(self, sections: dict, wikitext: dict):
        super().__init__()
        self.sections = sections
        self.wikitext = wikitext

    def _get_json(self, url: str) -> dict:
        return self.sections if "prop=sections" in url else self.wikitext


def _chat(content: str):
    def chat(messages):
        return ChatResult(content=content, finish_reason="stop")

    return chat


def _claims_payload() -> str:
    return json.dumps(
        {
            "claims": [
                {"text": "一致好评。", "source_ids": ["critiquebrainz-cb-1"]},
                {
                    "text": "songwriting 被称赞。",
                    "source_ids": ["wikipedia-norman-fucking-rockwell-reception"],
                },
                {
                    "text": "听感华丽、克制。",
                    "source_ids": [
                        "critiquebrainz-cb-1",
                        "wikipedia-norman-fucking-rockwell-reception",
                    ],
                },
            ]
        }
    )


def test_corpus_from_documents_maps_id_and_full_body() -> None:
    reviews = FakeCB(_CB_PAYLOAD).search_reviews("rg-nfr")
    document = cb_document(reviews[0], _RELEASE)
    corpus = corpus_from_documents([document])
    assert corpus[0].id == "critiquebrainz-cb-1"
    assert corpus[0].text == "A lush, sprawling record."


def test_enrich_release_composes_fetch_and_summary() -> None:
    summary = enrich_release(
        _RELEASE,
        _RELEASE_GROUP,
        "Norman Fucking Rockwell!",
        FakeCB(_CB_PAYLOAD),
        FakeWiki(_WIKI_SECTIONS, _WIKI_TEXT),
        model="deepseek-chat",
        chat=_chat(_claims_payload()),
    )
    assert len(summary.claims) == 3
    cited = {source for claim in summary.claims for source in claim.source_ids}
    assert cited == {
        "critiquebrainz-cb-1",
        "wikipedia-norman-fucking-rockwell-reception",
    }
    assert summary.corpus_hash
