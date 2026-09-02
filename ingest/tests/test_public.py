import json
from pathlib import Path

from linerfy_ingest import FixtureSourceAdapter, to_public

FIXTURE = Path(__file__).parent.parent / "fixtures" / "reviews.json"
# The shared fixture both languages agree on: Python produces it, Zod re-validates it.
SHARED = Path(__file__).resolve().parents[2] / "packages" / "domain" / "src" / "nfr.json"


def load_public() -> dict:
    return to_public(FixtureSourceAdapter(FIXTURE).fetch())


def test_public_output_matches_shared_fixture() -> None:
    assert load_public() == json.loads(SHARED.read_text(encoding="utf-8"))


def test_public_output_has_camel_case_shape() -> None:
    public = load_public()

    assert set(public) == {
        "artist",
        "release",
        "recordings",
        "genres",
        "sources",
        "excerpts",
        "summary",
    }
    assert public["release"]["artistId"] == public["artist"]["id"]
    assert public["summary"]["corpusHash"] == "fixture:nfr:v1"


def test_every_citation_resolves_to_a_public_source() -> None:
    public = load_public()

    source_ids = {source["id"] for source in public["sources"]}
    assert all(excerpt["sourceId"] in source_ids for excerpt in public["excerpts"])
    assert all(
        genre_source in source_ids
        for genre in public["genres"]
        for genre_source in genre["sourceIds"]
    )
    assert all(
        claim_source in source_ids
        for claim in public["summary"]["claims"]
        for claim_source in claim["sourceIds"]
    )
