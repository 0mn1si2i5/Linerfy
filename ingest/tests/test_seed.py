from pathlib import Path

from linerfy_ingest import FixtureSourceAdapter, to_rows

FIXTURE = Path(__file__).parent.parent / "fixtures" / "reviews.json"


def rows():
    return to_rows(FixtureSourceAdapter(FIXTURE).fetch())


def test_emits_every_catalog_table() -> None:
    assert set(rows()) == {
        "artists",
        "releases",
        "genres",
        "review_sources",
        "source_policies",
        "review_documents",
        "review_document_bodies",
        "review_excerpts",
        "genre_sources",
        "summary_runs",
        "claims",
        "claim_sources",
    }


def test_entities_carry_their_canonical_slug() -> None:
    r = rows()

    assert r["artists"][0]["slug"] == "lana-del-rey"
    assert r["releases"][0]["slug"] == "norman-fucking-rockwell"
    assert {row["slug"] for row in r["review_documents"]} == {
        "pitchfork-nfr",
        "guardian-nfr",
    }


def test_foreign_keys_resolve_across_tables() -> None:
    r = rows()

    artist_ids = {row["id"] for row in r["artists"]}
    release_ids = {row["id"] for row in r["releases"]}
    genre_ids = {row["id"] for row in r["genres"]}
    source_ids = {row["id"] for row in r["review_sources"]}
    document_ids = {row["id"] for row in r["review_documents"]}
    summary_ids = {row["id"] for row in r["summary_runs"]}
    claim_ids = {row["id"] for row in r["claims"]}

    assert all(row["artist_id"] in artist_ids for row in r["releases"])
    assert all(row["release_id"] in release_ids for row in r["review_documents"])
    assert all(row["release_id"] in release_ids for row in r["genres"])
    assert all(row["source_id"] in source_ids for row in r["review_documents"])
    assert all(row["source_id"] in source_ids for row in r["source_policies"])
    assert all(row["document_id"] in document_ids for row in r["review_excerpts"])
    assert all(row["genre_id"] in genre_ids for row in r["genre_sources"])
    assert all(row["document_id"] in document_ids for row in r["genre_sources"])
    assert all(row["release_id"] in release_ids for row in r["summary_runs"])
    assert all(row["summary_run_id"] in summary_ids for row in r["claims"])
    assert all(row["claim_id"] in claim_ids for row in r["claim_sources"])
    assert all(row["document_id"] in document_ids for row in r["claim_sources"])
    assert all(
        row["document_id"] in document_ids for row in r["review_document_bodies"]
    )


def test_one_policy_per_source() -> None:
    r = rows()

    assert len(r["source_policies"]) == len(r["review_sources"])
    policy_source_ids = {row["source_id"] for row in r["source_policies"]}
    assert policy_source_ids == {row["id"] for row in r["review_sources"]}


def test_only_published_rows_are_emitted() -> None:
    r = rows()

    assert all(row["status"] == "published" for row in r["review_documents"])
    assert all(row["status"] == "published" for row in r["summary_runs"])


def test_claim_sources_match_claim_provenance() -> None:
    context = FixtureSourceAdapter(FIXTURE).fetch()
    r = to_rows(context)

    expected_links = sum(
        len(claim.source_ids) for summary in context.summaries for claim in summary.claims
    )
    assert len(r["claim_sources"]) == expected_links


def test_each_summary_is_scoped_by_kind_and_pool() -> None:
    r = rows()

    assert len(r["summary_runs"]) == 3
    kinds = {row["summary_kind"] for row in r["summary_runs"]}
    assert kinds == {"source", "consensus"}
    assert all(row["license_pool"] == "proprietary" for row in r["summary_runs"])
    # Source summaries and the consensus block are distinct rows (no id collision).
    assert len({row["id"] for row in r["summary_runs"]}) == 3


def test_seed_is_deterministic() -> None:
    assert to_rows(FixtureSourceAdapter(FIXTURE).fetch()) == rows()
