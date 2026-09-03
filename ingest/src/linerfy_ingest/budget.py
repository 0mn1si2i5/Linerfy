"""A small, auditable CNY cost ledger for pre-launch real model calls.

Every real call is charged against an explicit per-model rate (input/output/
cache tokens), with a worst-case estimate reserved before the call and the
actual usage settled after. The cumulative total is capped at 100 CNY; once
reached, no further real call is allowed. Unknown models and models without a
declared rate are refused outright (fail closed) rather than assumed cheap.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .db import connect
from .providers import TokenUsage

BUDGET_YUAN = 100.0


@dataclass(frozen=True)
class ModelRate:
    """Price in CNY per one million tokens."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


class BudgetError(RuntimeError):
    """Raised when a real model call cannot be charged to the budget."""


# Approximate list prices in CNY per 1M tokens, as of 2026-09. These are
# conservative placeholders for pre-launch spend control, not a billing source;
# review and adjust via MODEL_RATES_JSON before production use. Any model not
# present here is refused for real calls.
_MODEL_RATES: dict[str, ModelRate] = {
    "deepseek-chat": ModelRate(input=2.0, output=8.0, cache_read=0.5, cache_write=2.0),
    "deepseek-reasoner": ModelRate(input=4.0, output=16.0),
    "gpt-5": ModelRate(input=8.75, output=35.0, cache_read=0.875),
    "gpt-5-mini": ModelRate(input=1.75, output=7.0, cache_read=0.175),
    "claude-sonnet-5": ModelRate(input=21.0, output=105.0, cache_read=2.1, cache_write=26.25),
    "claude-haiku-4-5": ModelRate(input=7.0, output=35.0, cache_read=0.7, cache_write=8.75),
}


def load_rates(raw: str | None) -> dict[str, ModelRate]:
    """Merge an optional ``MODEL_RATES_JSON`` override onto the defaults.

    The override is a JSON object mapping model id to a rate object with any of
    ``input``/``output``/``cache_read``/``cache_write`` (CNY per 1M tokens).
    """
    if not raw:
        return dict(_MODEL_RATES)
    rates = dict(_MODEL_RATES)
    override = json.loads(raw)
    for model, value in override.items():
        rates[model] = ModelRate(
            input=float(value.get("input", 0)),
            output=float(value.get("output", 0)),
            cache_read=float(value.get("cache_read", 0)),
            cache_write=float(value.get("cache_write", 0)),
        )
    return rates


def estimate_cost_cny(usage: TokenUsage, rate: ModelRate) -> float:
    """Estimated CNY cost of a usage against a rate."""
    cost = (
        usage.input * rate.input
        + usage.output * rate.output
        + usage.cache_read * rate.cache_read
        + usage.cache_write * rate.cache_write
    )
    return cost / 1_000_000


def worst_case_usage(max_tokens: int) -> TokenUsage:
    """Conservative pre-call estimate: assume the full budget on both sides."""
    return TokenUsage(input=max_tokens, output=max_tokens)


@dataclass
class LedgerEntry:
    request_id: str
    model: str
    kind: str  # "reserved" | "settled"
    cost_cny: float
    usage: TokenUsage = field(default_factory=TokenUsage)


class BudgetLedger:
    """Persists ledger entries to a JSON file; reads and writes are atomic.

    ``check`` reserves a worst-case estimate before a real call; ``settle``
    records the actual usage and cost after. Both fail closed on an unknown or
    unrated model.
    """

    def __init__(
        self,
        path: str,
        *,
        budget_yuan: float = BUDGET_YUAN,
        rates: dict[str, ModelRate] | None = None,
    ) -> None:
        self.path = path
        self.budget_yuan = budget_yuan
        self.rates = rates if rates is not None else load_rates(os.environ.get("MODEL_RATES_JSON"))
        self._entries = self._load()

    def _load(self) -> list[LedgerEntry]:
        try:
            raw = json.loads(Path(self.path).read_text())
        except (OSError, ValueError):
            return []
        return [
            LedgerEntry(
                request_id=e.get("request_id", ""),
                model=e.get("model", ""),
                kind=e.get("kind", "settled"),
                cost_cny=float(e.get("cost_cny", 0)),
                usage=TokenUsage(
                    input=int(e.get("input", 0)),
                    output=int(e.get("output", 0)),
                    cache_read=int(e.get("cache_read", 0)),
                    cache_write=int(e.get("cache_write", 0)),
                ),
            )
            for e in raw
        ]

    def _write(self) -> None:
        payload = [
            {
                "request_id": e.request_id,
                "model": e.model,
                "kind": e.kind,
                "cost_cny": round(e.cost_cny, 6),
                "input": e.usage.input,
                "output": e.usage.output,
                "cache_read": e.usage.cache_read,
                "cache_write": e.usage.cache_write,
            }
            for e in self._entries
        ]
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{self.path}.{uuid.uuid4().hex}.tmp"
        Path(tmp).write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.path)

    def rate(self, model: str) -> ModelRate:
        rate = self.rates.get(model)
        if rate is None:
            raise BudgetError(f"unknown model {model!r}; refusing real call")
        return rate

    def committed_cny(self) -> float:
        return sum(entry.cost_cny for entry in self._entries)

    def check(self, model: str, max_tokens: int) -> None:
        """Reserve a worst-case estimate before a real call."""
        rate = self.rate(model)
        worst = estimate_cost_cny(worst_case_usage(max_tokens), rate)
        if self.committed_cny() + worst > self.budget_yuan:
            raise BudgetError(
                f"budget exhausted ({self.committed_cny():.4f} CNY committed)"
            )

    def settle(
        self, model: str, usage: TokenUsage, request_id: str | None = None
    ) -> float:
        """Record actual usage after a call; returns the estimated CNY cost."""
        rate = self.rate(model)
        cost = estimate_cost_cny(usage, rate)
        self._entries.append(
            LedgerEntry(
                request_id=request_id or uuid.uuid4().hex,
                model=model,
                kind="settled",
                cost_cny=cost,
                usage=usage,
            )
        )
        self._write()
        return cost


class DbBudgetLedger:
    """A durable, concurrency-safe budget ledger backed by Postgres.

    The Vercel worker is serverless, so a local JSON file cannot be the
    authority. Before a real call ``reserve`` atomically locks the single-row
    running total, checks ``committed + reserved + worst <= budget``, and writes
    a reservation. After the call ``settle`` releases the reserved amount and
    records the actual cost. Concurrent invocations serialise on the row lock,
    so they can never jointly exceed the cap.
    """

    def __init__(
        self,
        *,
        budget_yuan: float = BUDGET_YUAN,
        rates: dict[str, ModelRate] | None = None,
        reservation_seconds: int = 3600,
    ) -> None:
        self.budget_yuan = budget_yuan
        self.rates = (
            rates if rates is not None else load_rates(os.environ.get("MODEL_RATES_JSON"))
        )
        self.reservation_seconds = reservation_seconds

    def rate(self, model: str) -> ModelRate:
        rate = self.rates.get(model)
        if rate is None:
            raise BudgetError(f"unknown model {model!r}; refusing real call")
        return rate

    def committed_cny(self) -> float:
        with connect() as conn:
            row = conn.execute(
                "SELECT committed_cny, reserved_cny FROM public.model_budget WHERE id = 1"
            ).fetchone()
            return float(row[0]) if row else 0.0

    def reserve(
        self,
        *,
        model: str,
        max_tokens: int,
        request_id: str,
        provider: str = "",
        job_id: str | None = None,
    ) -> float:
        """Atomically reserve a worst-case cost; returns the reserved CNY."""
        rate = self.rate(model)
        worst = estimate_cost_cny(worst_case_usage(max_tokens), rate)
        with connect(autocommit=False) as conn:
            row = conn.execute(
                "SELECT committed_cny, reserved_cny FROM public.model_budget "
                "WHERE id = 1 FOR UPDATE"
            ).fetchone()
            committed = float(row[0]) if row else 0.0
            reserved = float(row[1]) if row else 0.0
            if committed + reserved + worst > self.budget_yuan:
                raise BudgetError(
                    f"budget exhausted ({committed + reserved:.4f} CNY committed+reserved)"
                )
            conn.execute(
                "UPDATE public.model_budget SET reserved_cny = reserved_cny + %s "
                "WHERE id = 1",
                (worst,),
            )
            conn.execute(
                "INSERT INTO public.model_usage_reservations "
                "(request_id, job_id, provider, model, reserved_cny, status, expires_at) "
                "VALUES (%s,%s,%s,%s,%s,'reserved', now() + make_interval(secs => %s)) "
                "ON CONFLICT (request_id) DO NOTHING",
                (
                    request_id,
                    uuid.UUID(job_id) if job_id else None,
                    provider,
                    model,
                    worst,
                    self.reservation_seconds,
                ),
            )
            conn.commit()
        return worst

    def settle(
        self,
        *,
        request_id: str,
        model: str,
        usage: TokenUsage,
    ) -> float:
        """Release the reservation and record the actual cost; idempotent."""
        rate = self.rate(model)
        actual = estimate_cost_cny(usage, rate)
        with connect(autocommit=False) as conn:
            row = conn.execute(
                "SELECT reserved_cny, status, settled_cny FROM public.model_usage_reservations "
                "WHERE request_id = %s FOR UPDATE",
                (request_id,),
            ).fetchone()
            if row is None:
                raise BudgetError(f"no reservation for request {request_id}")
            if row[1] == "settled":
                return float(row[2] or 0.0)  # already settled; idempotent
            reserved = float(row[0] or 0.0)
            conn.execute(
                "UPDATE public.model_budget "
                "SET reserved_cny = reserved_cny - %s, committed_cny = committed_cny + %s "
                "WHERE id = 1",
                (reserved, actual),
            )
            conn.execute(
                "UPDATE public.model_usage_reservations "
                "SET status = 'settled', settled_cny = %s, input_tokens = %s, "
                "output_tokens = %s, cache_read_tokens = %s, cache_write_tokens = %s, "
                "settled_at = now() WHERE request_id = %s",
                (
                    actual,
                    usage.input,
                    usage.output,
                    usage.cache_read,
                    usage.cache_write,
                    request_id,
                ),
            )
            conn.commit()
        return actual

    def expire_stale(self) -> int:
        """Release reservations past their deadline, returning the count."""
        with connect(autocommit=False) as conn:
            rows = conn.execute(
                "SELECT request_id, reserved_cny FROM public.model_usage_reservations "
                "WHERE status = 'reserved' AND expires_at < now() FOR UPDATE"
            ).fetchall()
            for request_id, reserved in rows:
                conn.execute(
                    "UPDATE public.model_budget SET reserved_cny = reserved_cny - %s "
                    "WHERE id = 1",
                    (float(reserved),),
                )
                conn.execute(
                    "UPDATE public.model_usage_reservations SET status = 'expired' "
                    "WHERE request_id = %s",
                    (request_id,),
                )
            conn.commit()
            return len(rows)
