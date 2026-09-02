"""CLI: apply the catalog migration and seed catalog data into Supabase.

By default this loads the offline fixture. Pass ``--reset`` to first drop the
catalog tables (refused unless the target is a marked local/test database).
Pass ``--guardian <article-path>`` to fetch one real review from The Guardian's
Content API and load it instead (its full body is stored privately). The path is
the article id, e.g. ``music/2019/aug/30/lana-del-rey-norman-fucking-rockwell-review``.
Pass ``--summarize <release-slug>`` to summarize that release's published review
bodies into a traceable Chinese summary (requires ``MODEL_API_KEY``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .adapter import FixtureSourceAdapter
from .db import apply_migration, connect, reset, seed, verify
from .guardian import GuardianAdapter, build_context
from .summarize import read_corpus, summarize, write_summary

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "reviews.json"


def _run_fixture() -> None:
    context = FixtureSourceAdapter(_FIXTURE).fetch()
    with connect() as conn:
        if "--reset" in sys.argv[1:]:
            reset(conn)
        apply_migration(conn)
        written = seed(conn, context)
    print(f"applied migration; wrote {written} rows for {context.release.title}")
    print(verify())


def _run_guardian(article_path: str) -> None:
    review = GuardianAdapter(os.environ.get("GUARDIAN_API_KEY", "")).fetch_review(
        article_path
    )
    context = build_context(review)
    with connect() as conn:
        apply_migration(conn)
        written = seed(conn, context)
    print(f"fetched {article_path}; wrote {written} rows")
    print(verify())


def _run_summarize(release_slug: str) -> None:
    with connect() as conn:
        corpus = read_corpus(conn, release_slug)
        if not corpus:
            raise SystemExit(f"no published review bodies for release '{release_slug}'")
        summary = summarize(
            corpus, api_key=os.environ.get("MODEL_API_KEY", "")
        )
        written = write_summary(conn, release_slug, summary)
    print(
        f"summarized {release_slug}: {len(summary.claims)} claims "
        f"from {len(corpus)} documents; wrote {written} rows"
    )


def main() -> None:
    if "--guardian" in sys.argv[1:]:
        index = sys.argv.index("--guardian")
        if index + 1 >= len(sys.argv):
            raise SystemExit("usage: python -m linerfy_ingest --guardian <article-path>")
        _run_guardian(sys.argv[index + 1])
    elif "--summarize" in sys.argv[1:]:
        index = sys.argv.index("--summarize")
        if index + 1 >= len(sys.argv):
            raise SystemExit("usage: python -m linerfy_ingest --summarize <release-slug>")
        _run_summarize(sys.argv[index + 1])
    else:
        _run_fixture()


if __name__ == "__main__":
    main()
