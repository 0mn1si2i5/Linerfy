"""DB integration tests for the worker-wake function's privilege boundary.

``public.wake_worker`` reads the worker URL and bearer secret from Vault and
POSTs asynchronously via pg_net, so it must run as ``security definer`` and be
callable only by ``service_role``. A stray grant to ``anon``/``authenticated``/
``public`` would let anonymous callers trigger worker wakes carrying the server
secret. These tests check the function metadata and ACL against the marked test
database; they never invoke the function, so Vault and pg_net are not required.
"""

from __future__ import annotations

import os

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.db import connect

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)


def test_wake_worker_is_security_definer() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        row = conn.execute(
            "SELECT prosecdef FROM pg_proc "
            "WHERE proname = 'wake_worker' "
            "AND pronamespace = 'public'::regnamespace"
        ).fetchone()
        assert row is not None, "public.wake_worker() is missing"
        assert row[0] is True, "wake_worker must run as security definer"


def test_wake_worker_granted_only_to_service_role() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
        rows = conn.execute(
            "SELECT grantee, privilege_type "
            "FROM information_schema.role_routine_grants "
            "WHERE routine_name = 'wake_worker' AND specific_schema = 'public'"
        ).fetchall()
        exec_grantees = {grantee for grantee, priv in rows if priv == "EXECUTE"}
        # The anonymous roles must never trigger a worker wake carrying the
        # server secret. The owner (postgres) and service_role may; they are the
        # migration runner and the worker entrypoint respectively.
        forbidden = {"public", "anon", "authenticated"}
        leaked = exec_grantees & forbidden
        assert not leaked, f"wake_worker must not be executable by {sorted(leaked)}"
        assert "service_role" in exec_grantees, "service_role must retain EXECUTE"
