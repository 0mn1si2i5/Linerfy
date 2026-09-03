"""Pure unit tests for the prompt token estimate.

The estimate must be a conservative upper bound: it can over-count but never
under-count, because it feeds the pre-call budget reservation and an under-count
would let a model call exceed its reservation.
"""

from __future__ import annotations

from linerfy_ingest.worker import _estimate_input_tokens


def test_empty_messages_yield_at_least_one_token() -> None:
    assert _estimate_input_tokens([]) == 1


def test_cjk_estimate_is_at_least_the_character_count() -> None:
    # CJK characters are ~1 token each; the byte-length bound (3 bytes/char) must
    # never produce an estimate below the character count.
    text = "这是一段中文评论，用于验证预算预估。"  # 19 characters, 57 bytes
    messages = [{"role": "user", "content": text}]
    assert _estimate_input_tokens(messages) >= len(text)


def test_utf8_multibyte_is_not_underestimated() -> None:
    # A mix of emoji (4 bytes) and CJK (3 bytes) must estimate at least as high
    # as the UTF-8 byte length of the content itself.
    text = "👍🎵 音乐评论 🎶"
    messages = [{"role": "user", "content": text}]
    estimate = _estimate_input_tokens(messages)
    assert estimate >= len(text.encode("utf-8"))


def test_estimate_grows_with_more_messages() -> None:
    one = [{"role": "user", "content": "hello"}]
    two = [{"role": "system", "content": "hi"}, {"role": "user", "content": "hello"}]
    assert _estimate_input_tokens(two) > _estimate_input_tokens(one)
