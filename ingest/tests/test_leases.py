"""DB integration tests for short leases and compare-and-set commits.

Proves the worker lifecycle guarantees: a claim writes a fresh lease, a stale
lease can never commit, reaping an expired lease requeues the job, and a worker
holding an old lease cannot overwrite a newer claim. Gated like the other DB
integration tests.
"""

from __future__ import annotations

import os

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.db import connect
from linerfy_ingest.jobs import PostgresJobStore, StaleLease

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)


def _insert_job(conn, entity_id: str) -> None:
    conn.execute(
        "INSERT INTO public.enrichment_jobs "
        "(entity_id, entity_kind, stage, state, payload) "
        "VALUES (%s, 'release', 'resolve_entity', 'queued', '{}')",
        (entity_id,),
    )


def _delete_job(entity_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM public.enrichment_jobs WHERE entity_id = %s", (entity_id,)
        )


def test_claim_writes_lease_and_increments_attempt() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        with connect() as conn:
            _insert_job(conn, "lease-1")
        store = PostgresJobStore()
        claimed = store.reap_and_claim()
        assert claimed is not None and claimed.lease_id
        with connect() as conn:
            row = conn.execute(
                "SELECT state, lease_id, attempt FROM public.enrichment_jobs "
                "WHERE entity_id = 'lease-1'"
            ).fetchone()
            assert row[0] == "running"
            assert str(row[1]) == claimed.lease_id
            assert row[2] == 1
    finally:
        _delete_job("lease-1")


def test_claim_is_exclusive() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        with connect() as conn:
            _insert_job(conn, "lease-2")
        store = PostgresJobStore()
        first = store.reap_and_claim()
        assert first is not None
        # The job is now running, so a second claim finds nothing to claim.
        assert store.reap_and_claim() is None
    finally:
        _delete_job("lease-2")


def test_stale_lease_commit_is_rejected() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        with connect() as conn:
            _insert_job(conn, "lease-3")
        store = PostgresJobStore()
        claimed = store.reap_and_claim()
        assert claimed is not None
        # Simulate a reap + re-claim by another worker: replace the lease.
        with connect() as conn:
            conn.execute(
                "UPDATE public.enrichment_jobs "
                "SET lease_id = '00000000-0000-0000-0000-000000000000' "
                "WHERE entity_id = 'lease-3'"
            )
        with pytest.raises(StaleLease):
            store.commit(claimed.job.id, claimed.lease_id, stage=None, state="ready")
    finally:
        _delete_job("lease-3")


def test_expired_lease_is_reaped_and_old_worker_cannot_overwrite() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        with connect() as conn:
            _insert_job(conn, "lease-4")
        store = PostgresJobStore()
        old = store.reap_and_claim()
        assert old is not None
        # Force the lease to expire.
        with connect() as conn:
            conn.execute(
                "UPDATE public.enrichment_jobs SET lease_expires_at = now() - interval '1 second' "
                "WHERE entity_id = 'lease-4'"
            )
        # Reap requeues the job, then a fresh claim takes it with a new lease.
        fresh = store.reap_and_claim()
        assert fresh is not None and fresh.lease_id != old.lease_id
        # The old worker's commit must now be refused.
        with pytest.raises(StaleLease):
            store.commit(old.job.id, old.lease_id, stage=None, state="ready")
        # The fresh worker's commit succeeds.
        store.commit(fresh.job.id, fresh.lease_id, stage=None, state="ready")
    finally:
        _delete_job("lease-4")
