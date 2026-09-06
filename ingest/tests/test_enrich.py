"""Tests for license-pool isolation in the enrichment composition.

Uses the real adapter and summarizer code with fakes for the network and model,
so the tests prove that incompatible licenses are never merged into one corpus
or one claim.
"""

from __future__ import annotations

import json
import re

from linerfy_ingest.critiquebrainz import CritiqueBrainzAdapter
from linerfy_ingest.critiquebrainz import to_document as cb_document
from linerfy_ingest.enrich import (
    corpus_from_documents,
    enrich_release,
    fetch_documents_parallel,
    genres_from_release_group,
    group_by_pool,
)
from linerfy_ingest.entities import MusicBrainzGenre, ReleaseGroup
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
    "average_rating": {"rating": 4.0, "count": 1},
    "reviews": [
        {
            "id": "cb-1",
            "entity_id": "rg-nfr",
            "entity_type": "release_group",
            "text": "A lush, sprawling record.",
            "language": "en",
            "license_id": "CC BY-SA 3.0",
            "rating": 4,
            "user": {"display_name": "reviewer-one"},
            "created": "Fri, 06 Mar 2026 04:06:52 GMT",
        }
    ],
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
    listing = FakeCB(_CB_PAYLOAD).search_reviews("rg-nfr")
    document = cb_document(listing.reviews[0], _RELEASE)
    assert document is not None
    corpus = corpus_from_documents([document])
    assert corpus[0].id == "critiquebrainz-cb-1"
    assert corpus[0].text == "A lush, sprawling record."


def test_musicbrainz_genres_become_metadata_genres_without_review_citations() -> None:
    group = ReleaseGroup(
        mbid="rg-tags",
        title="Album",
        artist="Artist",
        genres=(
            MusicBrainzGenre(name="art pop", count=10),
            MusicBrainzGenre(name="Art Pop", count=9),
            MusicBrainzGenre(name="baroque pop", count=8),
            MusicBrainzGenre(name="dream pop", count=7),
        ),
    )

    genres = genres_from_release_group(group)
    assert [genre.name for genre in genres] == [
        "Art Pop",
        "Baroque Pop",
        "Dream Pop",
    ]
    assert all(genre.source_ids == [] for genre in genres)


def test_musicbrainz_genres_are_ranked_deduplicated_and_capped() -> None:
    group = ReleaseGroup(
        mbid="rg-rank",
        title="Album",
        artist="Artist",
        genres=(
            MusicBrainzGenre(name="rock", count=3),
            MusicBrainzGenre(name="indie rock", count=1),
            MusicBrainzGenre(name="psychedelic rock", count=6),
            MusicBrainzGenre(name="dream pop", count=2),
            MusicBrainzGenre(name="synth-pop", count=1),
            MusicBrainzGenre(name="electronic", count=1),
        ),
    )

    assert [genre.name for genre in genres_from_release_group(group)] == [
        "Psychedelic Rock",
        "Rock",
        "Dream Pop",
        "Indie Rock",
        "Synth-Pop",
    ]


def test_group_by_pool_separates_incompatible_licenses() -> None:
    listing = FakeCB(_CB_PAYLOAD).search_reviews("rg-nfr")
    wiki = FakeWiki(_WIKI_SECTIONS, _WIKI_TEXT).reception_section("Norman Fucking Rockwell!")
    cb = cb_document(listing.reviews[0], _RELEASE)
    assert cb is not None
    documents: list[ReviewDocument] = [
        cb,
        wiki_document(wiki, _RELEASE, "Norman Fucking Rockwell!"),
    ]
    grouped = group_by_pool(documents)
    assert set(grouped) == {"CC BY-SA 3.0", "CC BY-SA 4.0"}


def test_same_license_documents_share_one_pool() -> None:
    listing = FakeCB(_CB_PAYLOAD).search_reviews("rg-nfr")
    doc1 = cb_document(listing.reviews[0], _RELEASE)
    assert doc1 is not None
    doc2 = doc1.model_copy(update={"id": "critiquebrainz-cb-2"})
    grouped = group_by_pool([doc1, doc2])
    assert set(grouped) == {"CC BY-SA 3.0"}
    assert len(grouped["CC BY-SA 3.0"]) == 2


def test_fetch_documents_parallel_isolates_a_source_failure() -> None:
    class FailingCB(CritiqueBrainzAdapter):
        def search_reviews(self, mbid):
            raise ValueError("boom")

    results = list(
        fetch_documents_parallel(
            _RELEASE_GROUP,
            _RELEASE,
            "Norman Fucking Rockwell!",
            FailingCB(),
            FakeWiki(_WIKI_SECTIONS, _WIKI_TEXT),
        )
    )
    by_source = {result.source.id: result for result in results}

    assert by_source["critiquebrainz"].documents == []
    assert by_source["critiquebrainz"].error == "ValueError"
    assert len(by_source["wikipedia"].documents) == 1
    assert by_source["wikipedia"].error is None


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
    assert set(summaries) == {"CC BY-SA 3.0", "CC BY-SA 4.0"}

    critiquebrainz = _claim_sources(summaries["CC BY-SA 3.0"])
    wikipedia = _claim_sources(summaries["CC BY-SA 4.0"])

    assert critiquebrainz == {"critiquebrainz-cb-1"}
    assert wikipedia == {"wikipedia-norman-fucking-rockwell-reception"}
    # No summary's claims cite a source from the other pool.
    assert critiquebrainz.isdisjoint(wikipedia)
