"""DB integration tests for the durable, concurrency-safe budget ledger."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from _db_helpers import skip_unless_test_db

from linerfy_ingest.budget import (
    BudgetError,
    DbBudgetLedger,
    load_rates,
    reserve_cost_cny,
)
from linerfy_ingest.db import connect
from linerfy_ingest.providers import TokenUsage

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("DATABASE_URL")
        and os.environ.get("LINERFY_DB_TESTS_ALLOWED") == "1"
    ),
    reason="set DATABASE_URL and LINERFY_DB_TESTS_ALLOWED=1 to run DB integration tests",
)

_RATE = load_rates(None)["deepseek-chat"]


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
        reserved = ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=request_id,
        )
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


def test_reserve_is_idempotent_for_same_request_id() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        first = ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=request_id,
        )
        second = ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=request_id,
        )
        assert first == pytest.approx(second)
        # Reserved exactly once, not doubled.
        with connect() as conn:
            row = conn.execute(
                "SELECT reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            assert float(row[0]) == pytest.approx(first)
    finally:
        _reset_budget()


def test_reserve_rejects_replay_with_different_parameters() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=request_id,
        )
        with pytest.raises(BudgetError, match="different parameters"):
            ledger.reserve(
                model="deepseek-chat",
                input_tokens=2000,
                max_output_tokens=1000,
                request_id=request_id,
            )
        with pytest.raises(BudgetError, match="different model"):
            ledger.reserve(
                model="gpt-5",
                input_tokens=1000,
                max_output_tokens=1000,
                request_id=request_id,
            )
    finally:
        _reset_budget()


def test_settle_is_idempotent() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=request_id,
        )
        first = ledger.settle(
            request_id=request_id, model="deepseek-chat", usage=TokenUsage(100, 100)
        )
        second = ledger.settle(
            request_id=request_id, model="deepseek-chat", usage=TokenUsage(999, 999)
        )
        assert first == pytest.approx(second)
    finally:
        _reset_budget()


def test_release_is_idempotent_and_returns_reservation() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=request_id,
        )
        ledger.release(request_id=request_id)
        # A second release has no further effect.
        ledger.release(request_id=request_id)
        with connect() as conn:
            row = conn.execute(
                "SELECT reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            assert float(row[0]) == 0.0
        # Settling a released reservation is refused.
        with pytest.raises(BudgetError, match="released/expired"):
            ledger.settle(
                request_id=request_id,
                model="deepseek-chat",
                usage=TokenUsage(100, 100),
            )
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
                input_tokens=100_000,
                max_output_tokens=100_000,
                request_id=uuid.uuid4().hex,
            )
    finally:
        _reset_budget()


def test_very_large_prompt_is_rejected_before_the_call() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=1.0)
        # A huge prompt alone (tiny output) must be refused up front.
        with pytest.raises(BudgetError):
            ledger.reserve(
                model="deepseek-chat",
                input_tokens=10_000_000,
                max_output_tokens=10,
                request_id=uuid.uuid4().hex,
            )
        # A modest prompt plus full output fits and reserves the worst case.
        r = ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=uuid.uuid4().hex,
        )
        assert r == pytest.approx(reserve_cost_cny(_RATE, 1000, 1000))
    finally:
        _reset_budget()


def test_unknown_model_is_refused() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        with pytest.raises(BudgetError):
            ledger.reserve(
                model="no-such-model",
                input_tokens=100,
                max_output_tokens=100,
                request_id=uuid.uuid4().hex,
            )
    finally:
        _reset_budget()


def test_concurrent_reserves_never_exceed_the_cap() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        unit = reserve_cost_cny(_RATE, 1000, 1000)
        # Budget fits exactly one reservation but not two.
        ledger = DbBudgetLedger(budget_yuan=unit * 1.5)
        results: list[str] = []

        def reserve_one(i: int) -> None:
            try:
                ledger.reserve(
                    model="deepseek-chat",
                    input_tokens=1000,
                    max_output_tokens=1000,
                    request_id=f"conc-{i}",
                )
                results.append("ok")
            except BudgetError:
                results.append("rejected")

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(reserve_one, range(2)))

        assert results.count("ok") == 1
        assert results.count("rejected") == 1
        with connect() as conn:
            row = conn.execute(
                "SELECT reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            assert float(row[0]) <= unit * 1.5 + 1e-9
    finally:
        _reset_budget()


def test_settle_overrun_pauses_and_fails_closed() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        # Reserve a tiny worst case, then settle with far more tokens than the
        # reservation anticipated — the model returned beyond its cap.
        ledger.reserve(
            model="deepseek-chat",
            input_tokens=1,
            max_output_tokens=1,
            request_id=request_id,
        )
        with pytest.raises(BudgetError, match="pausing model calls"):
            ledger.settle(
                request_id=request_id,
                model="deepseek-chat",
                usage=TokenUsage(input=1000, output=1000),
            )
        with connect() as conn:
            # Real cost is recorded, the reservation is released, and the global
            # pause flag is set (fail-closed) rather than silently under-billing.
            row = conn.execute(
                "SELECT committed_cny, reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            assert float(row[0]) > 0.0
            assert float(row[1]) == 0.0
            flag = conn.execute(
                "SELECT value FROM public.service_flags "
                "WHERE key = 'model_generation_paused'"
            ).fetchone()
            assert flag is not None and flag[0] == "true"
    finally:
        _reset_budget()
        with connect() as conn:
            conn.execute(
                "UPDATE public.service_flags SET value = 'false' "
                "WHERE key = 'model_generation_paused'"
            )


def test_expire_stale_releases_reservation() -> None:
    with connect() as conn:
        skip_unless_test_db(conn)
    try:
        ledger = DbBudgetLedger(budget_yuan=100.0)
        request_id = uuid.uuid4().hex
        ledger.reserve(
            model="deepseek-chat",
            input_tokens=1000,
            max_output_tokens=1000,
            request_id=request_id,
        )
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
