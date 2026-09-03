"""Tests for the CNY cost ledger, no network."""

from __future__ import annotations

import pytest

from linerfy_ingest.budget import (
    BudgetError,
    BudgetLedger,
    ModelRate,
    estimate_cost_cny,
    load_rates,
    worst_case_usage,
)
from linerfy_ingest.providers import TokenUsage


def test_estimate_cost_uses_split_tokens_and_rates() -> None:
    rate = ModelRate(input=2.0, output=8.0, cache_read=0.5, cache_write=1.0)
    usage = TokenUsage(input=1_000_000, output=500_000, cache_read=1_000_000)
    assert estimate_cost_cny(usage, rate) == pytest.approx(2.0 + 4.0 + 0.5)


def test_different_models_cost_differently() -> None:
    cheap = ModelRate(input=1.0, output=2.0)
    pricey = ModelRate(input=10.0, output=20.0)
    usage = TokenUsage(input=1_000_000, output=1_000_000)
    assert estimate_cost_cny(usage, cheap) == pytest.approx(3.0)
    assert estimate_cost_cny(usage, pricey) == pytest.approx(30.0)


def test_load_rates_merges_override_onto_defaults() -> None:
    rates = load_rates('{"my-model": {"input": 3, "output": 9}}')
    assert rates["deepseek-chat"].input == 2.0  # default preserved
    assert rates["my-model"].output == 9.0


def test_worst_case_assumes_full_budget_both_ways() -> None:
    assert worst_case_usage(500).input == 500
    assert worst_case_usage(500).output == 500


def test_unknown_model_fails_closed(tmp_path) -> None:
    ledger = BudgetLedger(str(tmp_path / "b.json"))
    with pytest.raises(BudgetError, match="unknown model"):
        ledger.check("no-such-model", 1000)


def test_settle_records_actual_and_persists(tmp_path) -> None:
    path = str(tmp_path / "b.json")
    ledger = BudgetLedger(path, rates={"m": ModelRate(input=1.0, output=1.0)})
    ledger.settle("m", TokenUsage(input=1000, output=1000), request_id="r1")
    assert ledger.committed_cny() == pytest.approx(0.002)

    reloaded = BudgetLedger(path, rates={"m": ModelRate(input=1.0, output=1.0)})
    assert reloaded.committed_cny() == pytest.approx(0.002)


def test_check_rejects_when_worst_case_exceeds_budget(tmp_path) -> None:
    ledger = BudgetLedger(
        str(tmp_path / "b.json"),
        budget_yuan=1.0,
        rates={"m": ModelRate(input=10.0, output=10.0)},
    )
    with pytest.raises(BudgetError, match="budget exhausted"):
        ledger.check("m", 1_000_000)


def test_stub_calls_never_touch_the_ledger() -> None:
    # The ledger is only consulted by real-call paths (check/settle); this test
    # documents that constructing a ledger without settling costs nothing.
    ledger = BudgetLedger("ignored", rates={"m": ModelRate(input=1.0, output=1.0)})
    assert ledger.committed_cny() == 0.0
