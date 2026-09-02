"""Admin operations: pause control, job inspection/retry, and retention.

These are deliberate, operator-invoked actions -- the global model-generation
pause, re-queueing failed jobs, and purging private bodies past their source's
retention window -- kept out of the catalog read path.
"""

from __future__ import annotations

from datetime import datetime

import psycopg

from .jobs import PAUSE_FLAG

_JOB_COLUMNS = ["entity_id", "stage", "state", "retry_count", "last_error", "updated_at"]


def pause_value(paused: bool) -> str:
    return "true" if paused else "false"


def is_expired(fetched_at: datetime, retention_days: int, now: datetime) -> bool:
    """Whether a document past its retention window should be purged.

    ``retention_days == 0`` means retain indefinitely.
    """
    if retention_days <= 0:
        return False
    return (now - fetched_at).days >= retention_days


def set_pause(conn: psycopg.Connection, paused: bool) -> None:
    conn.execute(
        "INSERT INTO public.service_flags (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
        (PAUSE_FLAG, pause_value(paused)),
    )


def list_jobs(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT entity_id, stage, state, retry_count, last_error, updated_at "
        "FROM public.enrichment_jobs ORDER BY updated_at DESC LIMIT 100"
    ).fetchall()
    return [dict(zip(_JOB_COLUMNS, row, strict=True)) for row in rows]


def retry_failed(conn: psycopg.Connection) -> int:
    cursor = conn.execute(
        "UPDATE public.enrichment_jobs SET state = 'queued', retry_count = 0, "
        "last_error = NULL, updated_at = now() WHERE state = 'failed'"
    )
    return cursor.rowcount


def purge_expired(conn: psycopg.Connection) -> int:
    """Delete private review bodies whose source retention window has elapsed."""
    cursor = conn.execute(
        "DELETE FROM public.review_document_bodies b "
        "USING public.review_documents d "
        "JOIN public.source_policies p ON p.source_id = d.source_id "
        "WHERE b.document_id = d.id "
        "AND p.retention_days > 0 "
        "AND d.fetched_at < now() - make_interval(days => p.retention_days)"
    )
    return cursor.rowcount
