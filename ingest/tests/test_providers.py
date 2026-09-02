"""Fixture-based tests for the two model provider protocols, no network."""

from __future__ import annotations

import json

from linerfy_ingest.providers import (
    AnthropicProvider,
    ModelConfig,
    OpenAICompatibleProvider,
    _normalize_anthropic_stop_reason,
    resolve_provider,
)

_MESSAGES = [
    {"role": "system", "content": "you are a summarizer"},
    {"role": "user", "content": "summarize this"},
]


class _FakeOpenAI(OpenAICompatibleProvider):
    def __init__(self, payload: dict):
        super().__init__("https://api.deepseek.com", "deepseek-chat", "sk-test")
        self.payload = payload
        self.sent: tuple[str, dict, dict] | None = None

    def _post_json(self, url, headers, body):
        self.sent = (url, headers, json.loads(body))
        return self.payload


class _FakeAnthropic(AnthropicProvider):
    def __init__(self, payload: dict):
        super().__init__("claude-sonnet-5", "sk-ant-test")
        self.payload = payload
        self.sent: tuple[str, dict, dict] | None = None

    def _post_json(self, url, headers, body):
        self.sent = (url, headers, json.loads(body))
        return self.payload


def test_openai_provider_builds_chat_completions_request() -> None:
    provider = _FakeOpenAI(
        {
            "choices": [
                {
                    "message": {"content": '{"claims": []}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 123},
        }
    )
    result = provider.chat(_MESSAGES)

    url, headers, body = provider.sent
    assert url == "https://api.deepseek.com/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == "deepseek-chat"
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 2048
    assert body["messages"] == _MESSAGES

    assert result.content == '{"claims": []}'
    assert result.finish_reason == "stop"
    assert result.usage_tokens == 123


def test_openai_provider_reports_length_truncation() -> None:
    provider = _FakeOpenAI(
        {
            "choices": [{"message": {"content": "x"}, "finish_reason": "length"}],
            "usage": {},
        }
    )
    result = provider.chat(_MESSAGES)
    assert result.finish_reason == "length"
    assert result.usage_tokens == 0


def test_anthropic_provider_splits_system_and_maps_stop_reason() -> None:
    provider = _FakeAnthropic(
        {
            "content": [{"type": "text", "text": '{"claims": []}'}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
    )
    result = provider.chat(_MESSAGES)

    url, headers, body = provider.sent
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == "you are a summarizer"
    assert body["messages"] == [{"role": "user", "content": "summarize this"}]

    assert result.content == '{"claims": []}'
    assert result.finish_reason == "stop"
    assert result.usage_tokens == 30


def test_anthropic_provider_maps_max_tokens_to_length() -> None:
    provider = _FakeAnthropic(
        {"content": [{"type": "text", "text": "cut"}], "stop_reason": "max_tokens"}
    )
    result = provider.chat(_MESSAGES)
    assert result.finish_reason == "length"


def test_normalize_anthropic_stop_reason() -> None:
    assert _normalize_anthropic_stop_reason("end_turn") == "stop"
    assert _normalize_anthropic_stop_reason("max_tokens") == "length"
    assert _normalize_anthropic_stop_reason("stop_sequence") == "stop_sequence"


def test_resolve_provider_picks_openai_compatible_by_default() -> None:
    provider = resolve_provider(
        ModelConfig(protocol="openai-compatible", model="m", api_key="k")
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://api.deepseek.com"


def test_resolve_provider_picks_anthropic() -> None:
    provider = resolve_provider(
        ModelConfig(protocol="anthropic", model="claude-sonnet-5", api_key="k")
    )
    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-sonnet-5"


def test_resolve_provider_uses_custom_openai_base_url() -> None:
    provider = resolve_provider(
        ModelConfig(
            protocol="openai-compatible",
            model="gpt-5",
            api_key="k",
            base_url="https://api.openai.com/v1",
        )
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://api.openai.com/v1"
    assert provider.model == "gpt-5"
