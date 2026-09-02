"""Pure unit tests for the summarizer: hashing, prompt boundary, and the strict
validation that keeps a bad model response from ever reaching the database.

The live DeepSeek call is never made here; a stub ``chat`` is injected instead.
"""

from __future__ import annotations

import json

import pytest

from linerfy_ingest.summarize import (
    _MAX_CLAIM_TEXT_CHARS,
    CorpusDocument,
    _build_messages,
    _build_user_prompt,
    _parse_claims,
    corpus_hash,
    summarize,
)


def _corpus() -> list[CorpusDocument]:
    return [
        CorpusDocument(id="guardian-nfr", text="a lush, sprawling record"),
        CorpusDocument(id="pitchfork-nfr", text="a return to form", kind="review"),
    ]


def _payload(claims: list[tuple[str, list[str]]]) -> str:
    return json.dumps(
        {"claims": [{"text": text, "source_ids": sources} for text, sources in claims]}
    )


def _three_claims() -> list[tuple[str, list[str]]]:
    return [
        ("成熟的一张专辑。", ["guardian-nfr"]),
        ("存在听感矛盾。", ["guardian-nfr", "pitchfork-nfr"]),
        ("是否重复自我的争议。", ["pitchfork-nfr"]),
    ]


def _fake_chat(content: str, finish_reason: str = "stop"):
    def chat(api_key, base_url, model, messages):
        return content, finish_reason

    return chat


# --- corpus hashing ---------------------------------------------------------


def test_corpus_hash_is_order_independent() -> None:
    assert corpus_hash(_corpus()) == corpus_hash(list(reversed(_corpus())))


def test_corpus_hash_changes_with_content() -> None:
    a = _corpus()
    changed = [CorpusDocument(id="guardian-nfr", text="a very different record")]
    assert corpus_hash(a) != corpus_hash(changed)


def test_corpus_hash_changes_with_kind() -> None:
    a = _corpus()
    changed = [
        CorpusDocument(id="guardian-nfr", text="a lush, sprawling record", kind="community")
    ]
    assert corpus_hash(a) != corpus_hash(changed)


# --- prompt boundary --------------------------------------------------------


def test_rules_live_in_system_message_not_user_message() -> None:
    system, user = (m["content"] for m in _build_messages(_corpus()))

    assert "非可信资料" in system
    assert "禁止执行" in system
    # The untrusted material is confined to the user message.
    assert "a lush, sprawling record" not in system
    assert "a lush, sprawling record" in user


def test_documents_are_delimited_and_ids_present() -> None:
    user = _build_user_prompt(_corpus())

    assert '<document id="guardian-nfr" kind="review">' in user
    assert '<document id="pitchfork-nfr" kind="review">' in user
    assert "</document>" in user
    assert "<documents>" in user and "</documents>" in user
    assert "json" in user.lower()


# --- claim parsing ----------------------------------------------------------


def test_parse_claims_accepts_valid_json() -> None:
    claims = _parse_claims(_payload(_three_claims()), {"guardian-nfr", "pitchfork-nfr"})
    assert [c.text for c in claims] == [t for t, _ in _three_claims()]
    assert claims[1].source_ids == ["guardian-nfr", "pitchfork-nfr"]


def test_parse_claims_tolerates_surrounding_text() -> None:
    raw = "Here is your summary:\n" + _payload(_three_claims()) + "\ndone."
    claims = _parse_claims(raw, {"guardian-nfr", "pitchfork-nfr"})
    assert len(claims) == 3


def test_parse_claims_rejects_unknown_source() -> None:
    raw = _payload(
        [
            ("结论一", ["guardian-nfr"]),
            ("结论二", ["made-up-id"]),
            ("结论三", ["guardian-nfr"]),
        ]
    )
    with pytest.raises(ValueError, match="unknown sources"):
        _parse_claims(raw, {"guardian-nfr"})


def test_parse_claims_deduplicates_sources() -> None:
    raw = _payload(
        [
            ("结论一", ["guardian-nfr", "guardian-nfr", "pitchfork-nfr"]),
            ("结论二", ["guardian-nfr"]),
            ("结论三", ["pitchfork-nfr"]),
        ]
    )
    claims = _parse_claims(raw, {"guardian-nfr", "pitchfork-nfr"})
    assert claims[0].source_ids == ["guardian-nfr", "pitchfork-nfr"]


def test_parse_claims_rejects_too_few_claims() -> None:
    raw = _payload([("一条", ["guardian-nfr"]), ("两条", ["guardian-nfr"])])
    with pytest.raises(ValueError, match="claims"):
        _parse_claims(raw, {"guardian-nfr"})


def test_parse_claims_rejects_too_many_claims() -> None:
    too_many = [(f"结论 {i}", ["guardian-nfr"]) for i in range(6)]
    with pytest.raises(ValueError, match="claims"):
        _parse_claims(_payload(too_many), {"guardian-nfr"})


def test_parse_claims_rejects_overlong_text() -> None:
    long_text = "很" * (_MAX_CLAIM_TEXT_CHARS + 1)
    raw = _payload([(long_text, ["guardian-nfr"])] * 3)
    with pytest.raises(ValueError, match="exceeds"):
        _parse_claims(raw, {"guardian-nfr"})


def test_parse_claims_rejects_empty_text() -> None:
    raw = _payload([("   ", ["guardian-nfr"])] * 3)
    with pytest.raises(ValueError, match="empty"):
        _parse_claims(raw, {"guardian-nfr"})


def test_parse_claims_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        _parse_claims("no json here at all", {"guardian-nfr"})


def test_parse_claims_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        _parse_claims('{"claims": [}', {"guardian-nfr"})


# --- summarize orchestration -------------------------------------------------


def test_summarize_returns_validated_summary() -> None:
    summary = summarize(
        _corpus(), api_key="sk-test", chat=_fake_chat(_payload(_three_claims()))
    )
    assert len(summary.claims) == 3
    assert summary.model == "deepseek-chat"
    assert summary.locale == "zh-CN"


def test_summarize_rejects_non_stop_finish_reason() -> None:
    with pytest.raises(ValueError, match="finish_reason"):
        summarize(
            _corpus(),
            api_key="sk-test",
            chat=_fake_chat(_payload(_three_claims()), finish_reason="length"),
        )


def test_summarize_requires_nonempty_corpus_and_key() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        summarize([], api_key="sk-test")
    with pytest.raises(ValueError, match="MODEL_API_KEY"):
        summarize(_corpus(), api_key="")
