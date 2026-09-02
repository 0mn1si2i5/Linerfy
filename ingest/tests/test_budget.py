"""Tests for the pre-launch model-usage budget guard."""

from __future__ import annotations

from linerfy_ingest.budget import BUDGET_MAX_TOKENS, BudgetGuard


def test_guard_starts_at_zero_without_file(tmp_path) -> None:
    guard = BudgetGuard(str(tmp_path / "budget.json"))
    assert guard.total_tokens() == 0
    assert not guard.exceeded()


def test_guard_records_and_persists_usage(tmp_path) -> None:
    path = tmp_path / "budget.json"
    guard = BudgetGuard(str(path))
    guard.record(100)
    guard.record(50)

    reloaded = BudgetGuard(str(path))
    assert reloaded.total_tokens() == 150
    assert not reloaded.exceeded()


def test_guard_exceeds_at_cap(tmp_path) -> None:
    guard = BudgetGuard(str(tmp_path / "budget.json"), max_tokens=100)
    guard.record(90)
    assert not guard.exceeded()
    guard.record(10)
    assert guard.exceeded()


def test_guard_tolerates_corrupt_file(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text("not json")
    guard = BudgetGuard(str(path))
    assert guard.total_tokens() == 0


def test_default_cap_derives_from_budget() -> None:
    # The default cap is the 100 CNY budget expressed in tokens; it must be a
    # positive, sane ceiling rather than zero or negative.
    assert BUDGET_MAX_TOKENS > 0
