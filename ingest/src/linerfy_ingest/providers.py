"""Model provider protocol boundaries.

v1 supports exactly two wire protocols:

* OpenAI-compatible chat completions (DeepSeek, OpenAI, and other drop-ins).
* Anthropic Messages (Claude).

Only one provider is active at a time, chosen from configuration. There is no
automatic fallback between providers: if the configured provider errors, that
error surfaces to the caller instead of being silently masked by another
vendor's model.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"

_DEFAULT_OPENAI_BASE = "https://api.deepseek.com"


@dataclass(frozen=True)
class TokenUsage:
    """Token usage split by input/output/cache so cost can be estimated.

    Cache read/write are recorded only when a provider reports them; otherwise
    they stay zero.
    """

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass(frozen=True)
class ChatResult:
    """A provider response normalized to a common shape.

    ``finish_reason`` is normalized to ``"stop"`` for a normal end-of-turn and
    ``"length"`` for a truncation, matching what the summarizer already checks.
    ``usage`` carries split token counts for the budget ledger.
    """

    content: str
    finish_reason: str
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass(frozen=True)
class ModelConfig:
    """The single active model, resolved from environment by the caller."""

    protocol: str  # "openai-compatible" | "anthropic"
    model: str
    api_key: str
    base_url: str | None = None
    max_tokens: int = 2048


class ChatProvider(Protocol):
    """A provider exposes a single ``chat`` that maps messages to a result."""

    model: str

    def chat(self, messages: list[dict[str, str]]) -> ChatResult: ...


class OpenAICompatibleProvider:
    """An OpenAI-compatible ``/chat/completions`` client (DeepSeek, OpenAI, ...)."""

    def __init__(
        self, base_url: str, model: str, api_key: str, max_tokens: int = 2048
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict[str, str]]) -> ChatResult:
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        payload = self._post_json(
            url,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            body,
        )
        choice = payload["choices"][0]
        usage = payload.get("usage", {}) or {}
        details = usage.get("prompt_tokens_details", {}) or {}
        return ChatResult(
            content=choice["message"]["content"],
            finish_reason=choice.get("finish_reason", ""),
            usage=TokenUsage(
                input=usage.get("prompt_tokens", 0) or 0,
                output=usage.get("completion_tokens", 0) or 0,
                cache_read=details.get("cached_tokens", 0) or 0,
            ),
        )

    def _post_json(self, url: str, headers: dict[str, str], body: bytes) -> dict:
        """POST and parse JSON; stubbable for tests."""
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))


class AnthropicProvider:
    """An Anthropic Messages API client (Claude)."""

    def __init__(self, model: str, api_key: str, max_tokens: int = 2048) -> None:
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict[str, str]]) -> ChatResult:
        # Anthropic carries the system prompt in a dedicated field, not as a
        # message in the turn list, so split it out before sending.
        system = "\n\n".join(
            m["content"] for m in messages if m["role"] == "system"
        )
        turns = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] != "system"
        ]
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system,
                "messages": turns,
            }
        ).encode("utf-8")
        payload = self._post_json(
            _ANTHROPIC_ENDPOINT,
            {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
            body,
        )
        content = "".join(
            block.get("text", "") for block in payload.get("content", [])
        )
        stop_reason = payload.get("stop_reason", "")
        finish_reason = _normalize_anthropic_stop_reason(stop_reason)
        usage = payload.get("usage", {}) or {}
        return ChatResult(
            content=content,
            finish_reason=finish_reason,
            usage=TokenUsage(
                input=usage.get("input_tokens", 0) or 0,
                output=usage.get("output_tokens", 0) or 0,
                cache_read=usage.get("cache_read_input_tokens", 0) or 0,
                cache_write=usage.get("cache_creation_input_tokens", 0) or 0,
            ),
        )

    def _post_json(self, url: str, headers: dict[str, str], body: bytes) -> dict:
        """POST and parse JSON; stubbable for tests."""
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))


def _normalize_anthropic_stop_reason(stop_reason: str) -> str:
    if stop_reason == "end_turn":
        return "stop"
    if stop_reason == "max_tokens":
        return "length"
    return stop_reason


def resolve_provider(config: ModelConfig) -> ChatProvider:
    """Build the single active provider from configuration, no fallback."""
    if config.protocol == "anthropic":
        return AnthropicProvider(config.model, config.api_key, config.max_tokens)
    base_url = config.base_url or _DEFAULT_OPENAI_BASE
    return OpenAICompatibleProvider(
        base_url, config.model, config.api_key, config.max_tokens
    )
