"""Pure unit tests for the summarizer (hash, prompt, parsing, guardrails).

The live DeepSeek call is not exercised here; these tests cover everything that
does not require the network or a database.
"""

from __future__ import annotations

import pytest

from linerfy_ingest.summarize import (
    CorpusDocument,
    _build_prompt,
    _parse_claims,
    corpus_hash,
    summarize,
)


def _corpus() -> list[CorpusDocument]:
    return [
        CorpusDocument(id="guardian-nfr", text="a lush, sprawling record"),
        CorpusDocument(id="pitchfork-nfr", text="a return to form", kind="review"),
    ]


def test_corpus_hash_is_order_independent() -> None:
    a = _corpus()
    b = list(reversed(a))
    assert corpus_hash(a) == corpus_hash(b)


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


def test_prompt_contains_ids_and_text() -> None:
    prompt = _build_prompt(_corpus())
    assert "guardian-nfr" in prompt
    assert "pitchfork-nfr" in prompt
    assert "a lush, sprawling record" in prompt
    assert "claims" in prompt


def test_parse_claims_accepts_valid_json() -> None:
    raw = (
        '{"claims": [{"text": "这是一张成熟的专辑。", '
        '"source_ids": ["guardian-nfr", "pitchfork-nfr"]}]}'
    )
    claims = _parse_claims(raw, {"guardian-nfr", "pitchfork-nfr"})
    assert len(claims) == 1
    assert claims[0].text == "这是一张成熟的专辑。"
    assert claims[0].source_ids == ["guardian-nfr", "pitchfork-nfr"]


def test_parse_claims_tolerates_surrounding_text() -> None:
    raw = (
        "Here is your summary:\n"
        '{"claims": [{"text": "结论", "source_ids": ["guardian-nfr"]}]}\n'
        "done."
    )
    claims = _parse_claims(raw, {"guardian-nfr"})
    assert claims[0].text == "结论"


def test_parse_claims_rejects_unknown_source() -> None:
    raw = '{"claims": [{"text": "结论", "source_ids": ["made-up-id"]}]}'
    with pytest.raises(ValueError, match="unknown sources"):
        _parse_claims(raw, {"guardian-nfr"})


def test_parse_claims_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        _parse_claims("no json here at all", {"guardian-nfr"})


def test_summarize_requires_nonempty_corpus_and_key() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        summarize([], api_key="sk-test")
    with pytest.raises(ValueError, match="MODEL_API_KEY"):
        summarize(_corpus(), api_key="")
