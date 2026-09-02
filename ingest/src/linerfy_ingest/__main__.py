"""CLI for the Linerfy ingest pipeline.

Every mode is explicit. Running with no arguments prints help and exits without
touching the database.

Modes
-----
``--fixture [--reset]``
    Load the offline fixture. It inserts only rows that are absent, so it can
    never overwrite a real record; it is a pure contract check.
``--guardian <article-path>``
    Fetch one review from The Guardian's official Content API and upsert it (a
    real fetch replaces an earlier placeholder). The full body is stored privately.
``--summarize <release-slug>``
    Summarize a release's published review bodies into a traceable Chinese
    summary (requires ``MODEL_API_KEY``). The model call happens outside any
    transaction; the write is one atomic transaction, so a failure leaves the
    previous published summary untouched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .adapter import FixtureSourceAdapter
from .db import apply_migration, connect, require_test_db, reset, seed, verify
from .guardian import GuardianAdapter, build_context
from .summarize import read_corpus, summarize, write_summary

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "reviews.json"

_HELP = """usage: python -m linerfy_ingest <mode> [options]

modes:
  --fixture [--reset]          load the offline fixture (insert-only, never overwrites)
  --guardian <article-path>    fetch one review from The Guardian's Content API
  --summarize <release-slug>   summarize a release's published bodies into Chinese claims
  --help                       show this help

examples:
  python -m linerfy_ingest --fixture
  python -m linerfy_ingest --guardian music/2019/aug/30/lana-del-rey-norman-fucking-rockwell-review
  python -m linerfy_ingest --summarize norman-fucking-rockwell
"""


def _run_fixture() -> None:
    context = FixtureSourceAdapter(_FIXTURE).fetch()
    with connect() as conn:
        # The fixture is a test-only bootstrap; refuse to write it into the real
        # remote catalog (the same guard as --reset).
        require_test_db(conn)
        if "--reset" in sys.argv[1:]:
            reset(conn)
        apply_migration(conn)
        written = seed(conn, context, overwrite=False)
    print(f"loaded fixture; wrote {written} new rows for {context.release.title}")
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

    # Network call, deliberately outside any database transaction.
    summary = summarize(corpus, api_key=os.environ.get("MODEL_API_KEY", ""))

    with connect(autocommit=False) as conn:
        written = write_summary(conn, release_slug, summary)

    print(
        f"summarized {release_slug}: {len(summary.claims)} claims "
        f"from {len(corpus)} documents; wrote {written} rows"
    )


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(_HELP)
        raise SystemExit(2)
    if "--help" in args or "-h" in args:
        print(_HELP)
        raise SystemExit(0)

    if "--fixture" in args:
        _run_fixture()
    elif "--guardian" in args:
        index = args.index("--guardian")
        if index + 1 >= len(args):
            raise SystemExit("usage: python -m linerfy_ingest --guardian <article-path>")
        _run_guardian(args[index + 1])
    elif "--summarize" in args:
        index = args.index("--summarize")
        if index + 1 >= len(args):
            raise SystemExit("usage: python -m linerfy_ingest --summarize <release-slug>")
        _run_summarize(args[index + 1])
    else:
        print(_HELP)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
