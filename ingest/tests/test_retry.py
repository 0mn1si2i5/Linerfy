"""Real SQL retry boundary, in the marked test database only."""

import os
import uuid

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.db import connect

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or os.getenv("LINERFY_DB_TESTS_ALLOWED") != "1",
    reason="requires marked test database",
)


def test_retry_is_atomic_terminal_only_and_cooldown_bounded() -> None:
    job_id = uuid.uuid4()
    with connect(autocommit=False) as conn:
        skip_unless_test_db(conn)
        try:
            conn.execute(
                "INSERT INTO enrichment_jobs (id, entity_id, state, updated_at) "
                "VALUES (%s, %s, 'failed', now() - interval '1 minute')",
                (job_id, str(job_id)),
            )
            assert conn.execute("SELECT retry_enrichment(%s)", (job_id,)).fetchone()[0]
            assert not conn.execute("SELECT retry_enrichment(%s)", (job_id,)).fetchone()[0]
            conn.execute("UPDATE enrichment_jobs SET state = 'failed' WHERE id = %s", (job_id,))
            assert not conn.execute("SELECT retry_enrichment(%s)", (job_id,)).fetchone()[0]
        finally:
            conn.rollback()
