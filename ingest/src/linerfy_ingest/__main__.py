"""CLI for the Linerfy ingest pipeline.

Every mode is explicit. Running with no arguments prints help and exits without
touching the database.

Modes
-----
``--fixture [--reset]``
    Load the offline fixture. It inserts only rows that are absent, so it can
    never overwrite a real record; it is a pure contract check (test-only).
``--summarize <release-slug>``
    Summarize a release's published review bodies into a traceable Chinese
    summary (requires ``MODEL_API_KEY``). The model call happens outside any
    transaction; the write is one atomic transaction, so a failure leaves the
    previous published summary untouched.
``--run-enrichment``
    Run one enrichment worker tick.
``--prepare-test-db``
    Apply the catalog migration to the target and mark it as the dedicated test
    database. Run once against a throwaway/test database, never production.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .adapter import FixtureSourceAdapter
from .admin import list_jobs, purge_expired, retry_failed, set_pause
from .budget import BudgetError, BudgetLedger
from .critiquebrainz import CritiqueBrainzAdapter
from .db import (
    apply_migration,
    connect,
    prepare_test_db,
    require_test_db,
    reset,
    seed,
    verify,
)
from .jobs import PostgresJobStore, run_once
from .musicbrainz import MusicBrainzAdapter
from .pipeline import PipelineDeps, build_handlers
from .providers import ChatProvider, ModelConfig, resolve_provider
from .summarize import read_corpus, summarize, write_summary
from .wikipedia import WikipediaAdapter

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "reviews.json"

_HELP = """usage: python -m linerfy_ingest <mode> [options]

modes:
  --fixture [--reset]          load the offline fixture (insert-only, never overwrites)
  --summarize <release-slug>   summarize a release's published bodies into Chinese claims
  --run-enrichment             run one enrichment worker tick (claim + advance one job)
  --pause / --resume           set / clear the global model-generation pause
  --jobs                       list the enrichment queue
  --retry-failed               re-queue failed jobs (reset retry count)
  --purge                      delete private bodies past their retention window
  --prepare-test-db            migrate and mark the target as the dedicated test DB
  --help                       show this help

examples:
  python -m linerfy_ingest --fixture
  python -m linerfy_ingest --summarize norman-fucking-rockwell
  python -m linerfy_ingest --run-enrichment
  python -m linerfy_ingest --pause
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


def _run_prepare_test_db() -> None:
    with connect() as conn:
        prepare_test_db(conn)
    print("prepared test database: applied migration and marked it")


def _build_enrichment_handlers():
    """Construct the real five-stage handlers from live dependencies.

    The model provider is resolved lazily on the first model call, so resolve
    and fetch stages still run when MODEL_API_KEY is absent.
    """
    ledger = BudgetLedger(_budget_path())
    max_tokens = int(os.environ.get("MODEL_MAX_TOKENS", "2048"))
    provider_cache: dict[str, ChatProvider] = {}

    def chat(messages):
        if "provider" not in provider_cache:
            provider_cache["provider"] = _resolve_model()
        provider = provider_cache["provider"]
        ledger.check(provider.model, max_tokens)
        result = provider.chat(messages)
        ledger.settle(provider.model, result.usage)
        return result

    deps = PipelineDeps(
        store=PostgresJobStore(),
        musicbrainz=MusicBrainzAdapter(),
        critiquebrainz=CritiqueBrainzAdapter(),
        wikipedia=WikipediaAdapter(),
        model=os.environ.get("MODEL_NAME", "deepseek-chat"),
        chat=chat,
    )
    return build_handlers(deps)


def _run_enrichment() -> None:
    """Run one worker tick: reap leases, claim one job, run one bounded unit.

    External HTTP and model calls happen outside any database transaction; each
    job operation is its own short transaction guarded by a lease CAS.
    """
    handlers = _build_enrichment_handlers()
    processed = run_once(PostgresJobStore(), handlers)
    print(f"enrichment tick: processed {processed} job(s)")


def _run_pause(paused: bool) -> None:
    with connect() as conn:
        set_pause(conn, paused)
    print(f"model generation {'paused' if paused else 'resumed'}")


def _run_jobs() -> None:
    with connect() as conn:
        jobs = list_jobs(conn)
    if not jobs:
        print("no enrichment jobs")
        return
    for job in jobs:
        error = f" ({job['last_error']})" if job["last_error"] else ""
        print(
            f"{job['entity_id']}\t{job['stage']}\t{job['state']}"
            f"\tretries={job['retry_count']}{error}"
        )


def _run_retry_failed() -> None:
    with connect() as conn:
        count = retry_failed(conn)
    print(f"re-queued {count} failed job(s)")


def _run_purge() -> None:
    with connect() as conn:
        count = purge_expired(conn)
    print(f"purged {count} expired private body/bodies")


def _resolve_model() -> ChatProvider:
    """Build the single active provider from environment configuration."""
    protocol = os.environ.get("MODEL_PROTOCOL", "openai-compatible")
    api_key = os.environ.get("MODEL_API_KEY", "")
    if not api_key:
        raise SystemExit("MODEL_API_KEY is required")
    config = ModelConfig(
        protocol=protocol,
        model=os.environ.get("MODEL_NAME", "deepseek-chat"),
        api_key=api_key,
        base_url=os.environ.get("MODEL_BASE_URL", "https://api.deepseek.com"),
        max_tokens=int(os.environ.get("MODEL_MAX_TOKENS", "2048")),
    )
    return resolve_provider(config)


def _budget_path() -> str:
    return os.environ.get(
        "MODEL_BUDGET_PATH", str(Path.home() / ".linerfy" / "model-budget.json")
    )


def _run_summarize(release_slug: str) -> None:
    with connect() as conn:
        corpus = read_corpus(conn, release_slug)
    if not corpus:
        raise SystemExit(f"no published review bodies for release '{release_slug}'")

    provider = _resolve_model()
    max_tokens = int(os.environ.get("MODEL_MAX_TOKENS", "2048"))
    ledger = BudgetLedger(_budget_path())

    def chat(messages):
        # Worst-case pre-call check, then settle the actual usage after.
        ledger.check(provider.model, max_tokens)
        result = provider.chat(messages)
        ledger.settle(provider.model, result.usage)
        return result

    try:
        # Network call, deliberately outside any database transaction.
        summary = summarize(corpus, model=provider.model, chat=chat)
    except BudgetError as exc:
        raise SystemExit(f"refusing real model call: {exc}") from exc

    with connect(autocommit=False) as conn:
        written = write_summary(conn, release_slug, summary, status="published")

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
    elif "--prepare-test-db" in args:
        _run_prepare_test_db()
    elif "--summarize" in args:
        index = args.index("--summarize")
        if index + 1 >= len(args):
            raise SystemExit("usage: python -m linerfy_ingest --summarize <release-slug>")
        _run_summarize(args[index + 1])
    elif "--run-enrichment" in args:
        _run_enrichment()
    elif "--pause" in args:
        _run_pause(True)
    elif "--resume" in args:
        _run_pause(False)
    elif "--jobs" in args:
        _run_jobs()
    elif "--retry-failed" in args:
        _run_retry_failed()
    elif "--purge" in args:
        _run_purge()
    else:
        print(_HELP)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
