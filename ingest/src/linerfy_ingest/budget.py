"""Cumulative usage guard for pre-launch real model calls.

The pre-launch budget is a hard, visible cap: every real call records its token
usage to a JSON file, and once the cap is reached no further real call is made.
The cap is expressed in tokens, converted from the 100 CNY budget via a
documented, deliberately conservative per-token rate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Conservative blended rate: assume 1 CNY per 1M tokens. DeepSeek, OpenAI and
# Claude blended costs are all below this for our workload, so the cap is a
# safety net against runaway spend, not a pricing estimate.
YUAN_PER_MILLION_TOKENS = 1.0
BUDGET_YUAN = 100.0
BUDGET_MAX_TOKENS = int(BUDGET_YUAN / YUAN_PER_MILLION_TOKENS * 1_000_000)


@dataclass
class BudgetGuard:
    """Records cumulative token usage to a JSON file and refuses at the cap."""

    path: str
    max_tokens: int = BUDGET_MAX_TOKENS

    def __post_init__(self) -> None:
        self._state = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(Path(self.path).read_text())
        except (OSError, ValueError):
            return {"total_tokens": 0}

    def total_tokens(self) -> int:
        return int(self._state.get("total_tokens", 0))

    def exceeded(self) -> bool:
        return self.total_tokens() >= self.max_tokens

    def record(self, tokens: int) -> None:
        self._state["total_tokens"] = self.total_tokens() + tokens
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.path).write_text(json.dumps(self._state, indent=2))
