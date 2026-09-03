"""Persistent enrichment job lifecycle with short, atomic leases.

An enrichment job walks a release through five idempotent stages --
``resolve_entity -> fetch_sources -> build_source_summaries -> build_consensus
-> publish``. A worker performs external HTTP and model work OUTSIDE any
database transaction, so the job row is never locked across a network call.

Claiming writes a fresh ``lease_id`` + ``lease_expires_at`` in one short
transaction; committing a result is a compare-and-set on ``(id, lease_id)``, so
a stale worker whose lease was reaped can never overwrite a newer claim. Jobs
are claimed with ``FOR UPDATE SKIP LOCKED`` so concurrent workers never process
the same row, retried at most ``MAX_RETRIES`` times, and model stages are gated
behind a global pause flag.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, Protocol

import psycopg
from pydantic import BaseModel, Field

from .db import connect

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
LEASE_SECONDS = 120
PAUSE_FLAG = "model_generation_paused"


class EnrichmentJob(BaseModel):
    """A single release's position in the enrichment pipeline.

    ``entity_id`` holds the request fingerprint (the dedup key); ``payload``
    holds the bounded, untrusted now-playing metadata; ``resolved_release_group_id``
    and ``resolution_status`` are filled by ``resolve_entity``.
    """

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    stage: Stage
    state: JobState
    retry_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    corpus_hash: str | None = None
    payload: dict = Field(default_factory=dict)
    resolved_release_group_id: str | None = None
    resolution_status: str = "pending"


@dataclass(frozen=True)
class ClaimedJob:
    """A job plus the fresh lease that owns it, needed for compare-and-set."""

    job: EnrichmentJob
    lease_id: str


class StaleLease(Exception):
    """A commit was refused because the lease no longer matches the row."""


class JobUnavailable(Exception):
    """Raised by a stage to mark a job terminally unavailable (no retry)."""


class JobStore(Protocol):
    """Queue operations the worker performs, each a short transaction."""

    def paused(self) -> bool: ...

    def reap_and_claim(
        self, *, skip_model_stages: bool = False
    ) -> ClaimedJob | None: ...

    def commit(
        self,
        job_id: str,
        lease_id: str,
        *,
        stage: Stage | None,
        state: JobState,
    ) -> None: ...

    def renew(self, job_id: str, lease_id: str) -> None: ...

    def fail(self, job_id: str, lease_id: str, error: str) -> None: ...

    def set_corpus_hash(self, job_id: str, lease_id: str, corpus_hash: str) -> None: ...

    def set_resolution(
        self, job_id: str, lease_id: str, release_group_id: str | None, status: str
    ) -> None: ...


class StageHandler(Protocol):
    """One pipeline stage; raising marks the job failed (and retryable)."""

    def __call__(self, job: EnrichmentJob, lease_id: str) -> None: ...


def next_stage(stage: Stage) -> Stage | None:
    """The stage after ``stage``, or None at the end of the pipeline."""
    index = STAGES.index(stage)
    return STAGES[index + 1] if index + 1 < len(STAGES) else None


def run_job(
    job: EnrichmentJob,
    lease_id: str,
    handlers: dict[Stage, StageHandler],
    store: JobStore,
) -> None:
    """Run a claimed job's current stage and advance it, idempotently."""
    handler = handlers.get(job.stage)
    if handler is None:
        _fail(store, job.id, lease_id, f"no handler for stage {job.stage}")
        return
    try:
        advance = handler(job, lease_id)
    except JobUnavailable:
        _commit(store, job.id, lease_id, stage=None, state="unavailable")
        return
    except StaleLease:
        return  # another worker took over this job; do nothing
    except Exception as exc:  # the job boundary absorbs stage errors for retry
        _fail(store, job.id, lease_id, str(exc))
        return
    if not advance:
        return  # the handler re-queued itself; do not advance again
    following = next_stage(job.stage)
    _commit(
        store,
        job.id,
        lease_id,
        stage=following,
        state="ready" if following is None else "queued",
    )


def _commit(store: JobStore, job_id: str, lease_id: str, *, stage, state) -> None:
    # A stale commit is not a failure: a newer claim owns this job now.
    with suppress(StaleLease):
        store.commit(job_id, lease_id, stage=stage, state=state)


def _fail(store: JobStore, job_id: str, lease_id: str, error: str) -> None:
    # A stale fail is not a failure: a newer claim owns this job now.
    with suppress(StaleLease):
        store.fail(job_id, lease_id, error)


def run_once(store: JobStore, handlers: dict[Stage, StageHandler]) -> int:
    """One worker tick: reap timeouts, then process at most one job."""
    claimed = store.reap_and_claim(skip_model_stages=store.paused())
    if claimed is None:
        return 0
    run_job(claimed.job, claimed.lease_id, handlers, store)
    return 1


class PostgresJobStore:
    """Job queue backed by ``enrichment_jobs``; each op is a short transaction."""

    def __init__(self, *, lease_seconds: int = LEASE_SECONDS) -> None:
        self.lease_seconds = lease_seconds

    def paused(self) -> bool:
        with connect() as conn:
            row = conn.execute(
                "SELECT value FROM public.service_flags WHERE key = %s",
                (PAUSE_FLAG,),
            ).fetchone()
            return row is not None and row[0] == "true"

    def reap_and_claim(self, *, skip_model_stages: bool = False) -> ClaimedJob | None:
        with connect(autocommit=False) as conn:
            self._reap(conn)
            claimed = self._claim(conn, skip_model_stages)
            conn.commit()
            return claimed

    def _reap(self, conn: psycopg.Connection) -> None:
        """Expire leases past their deadline, atomically with the next claim."""
        conn.execute(
            "UPDATE public.enrichment_jobs SET retry_count = retry_count + 1, "
            "state = CASE WHEN retry_count < %s THEN 'queued' ELSE 'failed' END, "
            "last_error = 'lease expired', lease_id = NULL, lease_expires_at = NULL, "
            "updated_at = now() "
            "WHERE state = 'running' AND lease_expires_at < now()",
            (MAX_RETRIES,),
        )

    def _claim(
        self, conn: psycopg.Connection, skip_model_stages: bool
    ) -> ClaimedJob | None:
        stage_filter = ""
        if skip_model_stages:
            stage_filter = (
                "AND j.stage NOT IN ('build_source_summaries','build_consensus')"
            )
        row = conn.execute(
            "SELECT id, entity_id, stage, retry_count, last_error, corpus_hash, "
            "payload, resolved_release_group_id, resolution_status "
            "FROM public.enrichment_jobs j "
            f"WHERE j.state = 'queued' {stage_filter} "
            "ORDER BY j.updated_at FOR UPDATE SKIP LOCKED LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        lease_id = str(uuid.uuid4())
        conn.execute(
            "UPDATE public.enrichment_jobs SET state = 'running', "
            "lease_id = %s, lease_expires_at = now() + make_interval(secs => %s), "
            "attempt = attempt + 1, updated_at = now() WHERE id = %s",
            (lease_id, self.lease_seconds, row[0]),
        )
        return ClaimedJob(
            job=EnrichmentJob(
                id=row[0],
                entity_id=row[1],
                stage=row[2],
                state="running",
                retry_count=row[3],
                last_error=row[4],
                corpus_hash=row[5],
                payload=row[6] or {},
                resolved_release_group_id=row[7],
                resolution_status=row[8] or "pending",
            ),
            lease_id=lease_id,
        )

    def _assert_cas(self, cursor: psycopg.Cursor) -> None:
        if cursor.rowcount == 0:
            raise StaleLease("lease no longer matches; refusing to commit")

    def commit(
        self,
        job_id: str,
        lease_id: str,
        *,
        stage: Stage | None,
        state: JobState,
    ) -> None:
        with connect(autocommit=False) as conn:
            cursor = conn.execute(
                "UPDATE public.enrichment_jobs SET stage = COALESCE(%s, stage), "
                "state = %s, lease_id = NULL, lease_expires_at = NULL, "
                "last_error = NULL, updated_at = now() "
                "WHERE id = %s AND lease_id = %s",
                (stage, state, job_id, lease_id),
            )
            self._assert_cas(cursor)
            conn.commit()

    def renew(self, job_id: str, lease_id: str) -> None:
        """Extend the lease deadline, guarded by compare-and-set on the lease.

        A stage that spends a long time outside the database (an HTTP fetch or a
        model call) renews before that work so a concurrent reaper cannot take
        the job mid-stage. A stale worker's renew is refused just like a commit.
        """
        with connect(autocommit=False) as conn:
            cursor = conn.execute(
                "UPDATE public.enrichment_jobs SET "
                "lease_expires_at = now() + make_interval(secs => %s), "
                "updated_at = now() WHERE id = %s AND lease_id = %s",
                (self.lease_seconds, job_id, lease_id),
            )
            self._assert_cas(cursor)
            conn.commit()

    def fail(self, job_id: str, lease_id: str, error: str) -> None:
        with connect(autocommit=False) as conn:
            cursor = conn.execute(
                "UPDATE public.enrichment_jobs SET retry_count = retry_count + 1, "
                "state = CASE WHEN retry_count < %s THEN 'queued' ELSE 'failed' END, "
                "last_error = %s, lease_id = NULL, lease_expires_at = NULL, "
                "updated_at = now() WHERE id = %s AND lease_id = %s",
                (MAX_RETRIES, error, job_id, lease_id),
            )
            self._assert_cas(cursor)
            conn.commit()

    def set_corpus_hash(self, job_id: str, lease_id: str, corpus_hash: str) -> None:
        with connect(autocommit=False) as conn:
            cursor = conn.execute(
                "UPDATE public.enrichment_jobs SET corpus_hash = %s, "
                "updated_at = now() WHERE id = %s AND lease_id = %s",
                (corpus_hash, job_id, lease_id),
            )
            self._assert_cas(cursor)
            conn.commit()

    def set_resolution(
        self, job_id: str, lease_id: str, release_group_id: str | None, status: str
    ) -> None:
        with connect(autocommit=False) as conn:
            cursor = conn.execute(
                "UPDATE public.enrichment_jobs SET resolved_release_group_id = %s, "
                "resolution_status = %s, updated_at = now() "
                "WHERE id = %s AND lease_id = %s",
                (release_group_id, status, job_id, lease_id),
            )
            self._assert_cas(cursor)
            conn.commit()
