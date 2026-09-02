"""Persistent enrichment job lifecycle.

An enrichment job walks a release through five idempotent stages --
``resolve_entity -> fetch_sources -> build_source_summaries -> build_consensus
-> publish`` -- each advancing atomically so a worker crash or timeout can never
leave the catalog half-written. Jobs are claimed with ``FOR UPDATE SKIP LOCKED``
so concurrent workers never process the same row, retried at most
``MAX_RETRIES`` times, and model stages are gated behind a global pause flag.
"""

from __future__ import annotations

from typing import Literal, Protocol

import psycopg
from pydantic import BaseModel, Field

Stage = Literal[
    "resolve_entity",
    "fetch_sources",
    "build_source_summaries",
    "build_consensus",
    "publish",
]
JobState = Literal["queued", "running", "ready", "unavailable", "failed"]

STAGES: tuple[Stage, ...] = (
    "resolve_entity",
    "fetch_sources",
    "build_source_summaries",
    "build_consensus",
    "publish",
)
# Stages that invoke a model; paused while the global model-generation flag is on.
MODEL_STAGES: frozenset[Stage] = frozenset(
    {"build_source_summaries", "build_consensus"}
)
MAX_RETRIES = 2
STAGE_TIMEOUT_SECONDS = 120
PAUSE_FLAG = "model_generation_paused"


class EnrichmentJob(BaseModel):
    """A single release's position in the enrichment pipeline."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    stage: Stage
    state: JobState
    retry_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    corpus_hash: str | None = None


class JobStore(Protocol):
    """The queue operations the worker performs, injectable for tests."""

    def paused(self) -> bool: ...

    def reap_timeouts(self) -> int: ...

    def claim_next(self, *, skip_model_stages: bool = False) -> EnrichmentJob | None: ...

    def advance(
        self, job: EnrichmentJob, *, stage: Stage | None, state: JobState
    ) -> None: ...

    def fail(self, job: EnrichmentJob, error: str) -> None: ...

    def set_corpus_hash(self, job: EnrichmentJob, corpus_hash: str) -> None: ...


class StageHandler(Protocol):
    """One pipeline stage; raising marks the job failed (and retryable)."""

    def __call__(self, job: EnrichmentJob) -> None: ...


def next_stage(stage: Stage) -> Stage | None:
    """The stage after ``stage``, or None at the end of the pipeline."""
    index = STAGES.index(stage)
    return STAGES[index + 1] if index + 1 < len(STAGES) else None


def failure_outcome(job: EnrichmentJob) -> JobState:
    """Whether a failed job is retried (queued) or exhausted (failed)."""
    return "queued" if job.retry_count < MAX_RETRIES else "failed"


def run_job(
    job: EnrichmentJob,
    handlers: dict[Stage, StageHandler],
    store: JobStore,
) -> None:
    """Run a claimed job's current stage and advance it, idempotently."""
    handler = handlers.get(job.stage)
    if handler is None:
        store.fail(job, f"no handler for stage {job.stage}")
        return
    try:
        handler(job)
    except Exception as exc:  # the job boundary absorbs stage errors for retry
        store.fail(job, str(exc))
        return
    following = next_stage(job.stage)
    if following is None:
        store.advance(job, stage=None, state="ready")
    else:
        store.advance(job, stage=following, state="queued")


def run_once(store: JobStore, handlers: dict[Stage, StageHandler]) -> int:
    """One worker tick: reap timeouts, then process at most one job."""
    store.reap_timeouts()
    job = store.claim_next(skip_model_stages=store.paused())
    if job is None:
        return 0
    run_job(job, handlers, store)
    return 1


class PostgresJobStore:
    """Job queue backed by the ``enrichment_jobs`` and ``service_flags`` tables."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def paused(self) -> bool:
        row = self.conn.execute(
            "SELECT value FROM public.service_flags WHERE key = %s", (PAUSE_FLAG,)
        ).fetchone()
        return row is not None and row[0] == "true"

    def reap_timeouts(self) -> int:
        rows = self.conn.execute(
            "SELECT id, retry_count FROM public.enrichment_jobs "
            "WHERE state = 'running' AND timeout_at < now() FOR UPDATE"
        ).fetchall()
        for job_id, retry_count in rows:
            outcome = "queued" if retry_count < MAX_RETRIES else "failed"
            self.conn.execute(
                "UPDATE public.enrichment_jobs SET retry_count = retry_count + 1, "
                "state = %s, last_error = 'stage timeout', claimed_at = NULL, "
                "timeout_at = NULL, updated_at = now() WHERE id = %s",
                (outcome, job_id),
            )
        return len(rows)

    def claim_next(self, *, skip_model_stages: bool = False) -> EnrichmentJob | None:
        stage_filter = ""
        if skip_model_stages:
            stage_filter = "AND j.stage NOT IN ('build_source_summaries','build_consensus')"
        row = self.conn.execute(
            f"SELECT id, entity_id, stage, retry_count, last_error, corpus_hash "
            "FROM public.enrichment_jobs j "
            f"WHERE j.state = 'queued' {stage_filter} "
            "ORDER BY j.updated_at FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        self.conn.execute(
            "UPDATE public.enrichment_jobs SET state = 'running', claimed_at = now(), "
            "timeout_at = now() + interval '%s seconds', updated_at = now() WHERE id = %s",
            (STAGE_TIMEOUT_SECONDS, row[0]),
        )
        return EnrichmentJob(
            id=row[0],
            entity_id=row[1],
            stage=row[2],
            state="running",
            retry_count=row[3],
            last_error=row[4],
            corpus_hash=row[5],
        )

    def advance(
        self, job: EnrichmentJob, *, stage: Stage | None, state: JobState
    ) -> None:
        self.conn.execute(
            "UPDATE public.enrichment_jobs SET stage = COALESCE(%s, stage), "
            "state = %s, claimed_at = NULL, timeout_at = NULL, last_error = NULL, "
            "updated_at = now() WHERE id = %s",
            (stage, state, job.id),
        )

    def fail(self, job: EnrichmentJob, error: str) -> None:
        outcome = failure_outcome(job)
        self.conn.execute(
            "UPDATE public.enrichment_jobs SET retry_count = retry_count + 1, "
            "state = %s, last_error = %s, claimed_at = NULL, timeout_at = NULL, "
            "updated_at = now() WHERE id = %s",
            (outcome, error, job.id),
        )

    def set_corpus_hash(self, job: EnrichmentJob, corpus_hash: str) -> None:
        self.conn.execute(
            "UPDATE public.enrichment_jobs SET corpus_hash = %s, updated_at = now() "
            "WHERE id = %s",
            (corpus_hash, job.id),
        )
