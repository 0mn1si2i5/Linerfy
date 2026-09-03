"""DB integration tests for the durable, concurrency-safe budget ledger."""

from __future__ import annotations

import os
import uuid

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.budget import BudgetError, DbBudgetLedger
from linerfy_ingest.db import connect
from linerfy_ingest.providers import TokenUsage

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)


def _reset_budget() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM public.model_usage_reservations")
        conn.execute(
            "UPDATE public.model_budget SET committed_cny = 0, reserved_cny = 0 WHERE id = 1"
        )


def test_reserve_and_settle_releases_reserved() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        reserved = ledger.reserve(model="deepseek-chat", max_tokens=1000, request_id=request_id)
        assert reserved > 0

        with connect() as conn:
            row = conn.execute(
                "SELECT committed_cny, reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            assert float(row[1]) == pytest.approx(reserved)

        cost = ledger.settle(
            request_id=request_id,
            model="deepseek-chat",
            usage=TokenUsage(input=500, output=500),
        )
        assert cost >= 0
        with connect() as conn:
            row = conn.execute(
                "SELECT committed_cny, reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            assert float(row[1]) == 0.0  # reservation fully released
            assert float(row[0]) == pytest.approx(cost)
    finally:
        _reset_budget()


def test_settle_is_idempotent() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        ledger.reserve(model="deepseek-chat", max_tokens=1000, request_id=request_id)
        first = ledger.settle(
            request_id=request_id, model="deepseek-chat", usage=TokenUsage(100, 100)
        )
        second = ledger.settle(
            request_id=request_id, model="deepseek-chat", usage=TokenUsage(999, 999)
        )
        assert first == pytest.approx(second)
    finally:
        _reset_budget()


def test_reserve_exceeding_budget_raises() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=0.001)
        with pytest.raises(BudgetError):
            ledger.reserve(
                model="deepseek-chat",
                max_tokens=100_000,
                request_id=uuid.uuid4().hex,
            )
    finally:
        _reset_budget()


def test_unknown_model_is_refused() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        with pytest.raises(BudgetError):
            ledger.reserve(model="no-such-model", max_tokens=100, request_id=uuid.uuid4().hex)
    finally:
        _reset_budget()


def test_expire_stale_releases_reservation() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        ledger.reserve(model="deepseek-chat", max_tokens=1000, request_id=request_id)
        with connect() as conn:
            conn.execute(
                "UPDATE public.model_usage_reservations "
                "SET expires_at = now() - interval '1 second' WHERE request_id = %s",
                (request_id,),
            )
        assert ledger.expire_stale() == 1
        with connect() as conn:
            row = conn.execute(
                "SELECT reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            assert float(row[0]) == 0.0
    finally:
        _reset_budget()
