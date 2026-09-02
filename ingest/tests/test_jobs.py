"""Tests for the enrichment job lifecycle state machine, no database."""

from __future__ import annotations

from linerfy_ingest.jobs import (
    MAX_RETRIES,
    EnrichmentJob,
    failure_outcome,
    next_stage,
    run_job,
    run_once,
)


class FakeStore:
    def __init__(self, jobs=None, *, paused=False):
        self.jobs = list(jobs or [])
        self.paused_flag = paused
        self.reaped = 0
        self.claim_skips: list[bool] = []
        self.actions: list[tuple] = []

    def paused(self) -> bool:
        return self.paused_flag

    def reap_timeouts(self) -> int:
        self.reaped += 1
        return 0

    def claim_next(self, *, skip_model_stages=False):
        self.claim_skips.append(skip_model_stages)
        return self.jobs.pop(0) if self.jobs else None

    def advance(self, job, *, stage, state):
        self.actions.append(("advance", stage, state))

    def fail(self, job, error):
        self.actions.append(("fail", error))

    def set_corpus_hash(self, job, corpus_hash):
        self.actions.append(("corpus_hash", corpus_hash))


def _job(stage, retry_count=0):
    return EnrichmentJob(
        id="j1", entity_id="nfr", stage=stage, state="running", retry_count=retry_count
    )


def test_next_stage_walks_the_pipeline() -> None:
    assert next_stage("resolve_entity") == "fetch_sources"
    assert next_stage("build_consensus") == "publish"
    assert next_stage("publish") is None


def test_failure_outcome_retries_then_fails() -> None:
    assert failure_outcome(_job("resolve_entity", 0)) == "queued"
    assert failure_outcome(_job("resolve_entity", MAX_RETRIES - 1)) == "queued"
    assert failure_outcome(_job("resolve_entity", MAX_RETRIES)) == "failed"


def test_run_job_advances_to_next_stage() -> None:
    store = FakeStore()
    run_job(_job("resolve_entity"), {"resolve_entity": lambda job: None}, store)
    assert store.actions == [("advance", "fetch_sources", "queued")]


def test_run_job_completes_after_publish() -> None:
    store = FakeStore()
    run_job(_job("publish"), {"publish": lambda job: None}, store)
    assert store.actions == [("advance", None, "ready")]


def test_run_job_fails_when_handler_raises() -> None:
    store = FakeStore()

    def boom(job):
        raise RuntimeError("upstream down")

    run_job(_job("fetch_sources"), {"fetch_sources": boom}, store)
    assert store.actions == [("fail", "upstream down")]


def test_run_job_fails_without_a_handler() -> None:
    store = FakeStore()
    run_job(_job("resolve_entity"), {}, store)
    assert store.actions == [("fail", "no handler for stage resolve_entity")]


def test_run_once_reaps_then_claims_one_job() -> None:
    store = FakeStore([_job("resolve_entity")])
    processed = run_once(store, {"resolve_entity": lambda job: None})
    assert store.reaped == 1
    assert processed == 1
    assert store.actions == [("advance", "fetch_sources", "queued")]


def test_run_once_skips_model_stages_when_paused() -> None:
    store = FakeStore([_job("resolve_entity")], paused=True)
    run_once(store, {"resolve_entity": lambda job: None})
    assert store.claim_skips == [True]


def test_run_once_is_idle_with_no_jobs() -> None:
    store = FakeStore()
    assert run_once(store, {}) == 0
    assert store.actions == []
