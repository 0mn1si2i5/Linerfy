"""Tests for license-pool isolation in the enrichment composition.

Uses the real adapter and summarizer code with fakes for the network and model,
so the tests prove that incompatible licenses are never merged into one corpus
or one claim.
"""

from __future__ import annotations

import json
import re

import linerfy_ingest.pipeline as pipeline
from linerfy_ingest.critiquebrainz import CritiqueBrainzAdapter
from linerfy_ingest.critiquebrainz import to_document as cb_document
from linerfy_ingest.enrich import (
    corpus_from_documents,
    enrich_release,
    group_by_pool,
)
from linerfy_ingest.entities import ReleaseGroup
from linerfy_ingest.models import ReleaseEntity, ReviewDocument
from linerfy_ingest.providers import ChatResult
from linerfy_ingest.wikipedia import WikipediaAdapter
from linerfy_ingest.wikipedia import to_document as wiki_document

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


def _echo_chat():
    """A fake chat that cites only documents actually present in its corpus."""

    def chat(messages):
        user = messages[-1]["content"]
        ids = re.findall(r'<document id="([^"]+)"', user)
        claims = [{"text": f"观点 {i + 1}", "source_ids": [ids[i % len(ids)]]} for i in range(3)]
        return ChatResult(content=json.dumps({"claims": claims}), finish_reason="stop")

    return chat


def _claim_sources(summary) -> set[str]:
    return {source for claim in summary.claims for source in claim.source_ids}


def test_corpus_from_documents_maps_id_and_full_body() -> None:
    reviews = FakeCB(_CB_PAYLOAD).search_reviews("rg-nfr")
    document = cb_document(reviews[0], _RELEASE)
    corpus = corpus_from_documents([document])
    assert corpus[0].id == "critiquebrainz-cb-1"
    assert corpus[0].text == "A lush, sprawling record."


def test_musicbrainz_tags_become_metadata_genres_without_review_citations() -> None:
    group = ReleaseGroup(
        mbid="rg-tags",
        title="Album",
        artist="Artist",
        tags=("art pop", "Art Pop", "baroque pop", "dream pop"),
    )

    helper = getattr(pipeline, "genres_from_release_group", None)
    assert callable(helper)
    assert [genre.name for genre in helper(group)] == [
        "Art Pop",
        "Baroque Pop",
        "Dream Pop",
    ]
    assert all(genre.source_ids == [] for genre in helper(group))


def test_group_by_pool_separates_incompatible_licenses() -> None:
    reviews = FakeCB(_CB_PAYLOAD).search_reviews("rg-nfr")
    wiki = FakeWiki(_WIKI_SECTIONS, _WIKI_TEXT).reception_section("Norman Fucking Rockwell!")
    documents: list[ReviewDocument] = [
        cb_document(reviews[0], _RELEASE),
        wiki_document(wiki, _RELEASE, "Norman Fucking Rockwell!"),
    ]
    grouped = group_by_pool(documents)
    assert set(grouped) == {"CC BY-NC-SA 3.0", "CC BY-SA 4.0"}


def test_same_license_documents_share_one_pool() -> None:
    reviews = FakeCB(_CB_PAYLOAD).search_reviews("rg-nfr")
    doc1 = cb_document(reviews[0], _RELEASE)
    doc2 = doc1.model_copy(update={"id": "critiquebrainz-cb-2"})
    grouped = group_by_pool([doc1, doc2])
    assert set(grouped) == {"CC BY-NC-SA 3.0"}
    assert len(grouped["CC BY-NC-SA 3.0"]) == 2


def test_enrich_release_partitions_by_pool_and_never_crosses() -> None:
    summaries = enrich_release(
        _RELEASE,
        _RELEASE_GROUP,
        "Norman Fucking Rockwell!",
        FakeCB(_CB_PAYLOAD),
        FakeWiki(_WIKI_SECTIONS, _WIKI_TEXT),
        model="deepseek-chat",
        chat=_echo_chat(),
    )
    assert set(summaries) == {"CC BY-NC-SA 3.0", "CC BY-SA 4.0"}

    critiquebrainz = _claim_sources(summaries["CC BY-NC-SA 3.0"])
    wikipedia = _claim_sources(summaries["CC BY-SA 4.0"])

    assert critiquebrainz == {"critiquebrainz-cb-1"}
    assert wikipedia == {"wikipedia-norman-fucking-rockwell-reception"}
    # No summary's claims cite a source from the other pool.
    assert critiquebrainz.isdisjoint(wikipedia)
