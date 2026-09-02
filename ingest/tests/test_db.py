import pytest

from linerfy_ingest.db import _reset_permitted


def test_reset_permitted_for_local_host() -> None:
    assert _reset_permitted("localhost")
    assert _reset_permitted("127.0.0.1")
    assert _reset_permitted("::1")


def test_reset_refused_for_remote_host_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LINERFY_RESET_ALLOWED", raising=False)
    assert not _reset_permitted("aws-0-ap-southeast-1.pooler.supabase.com")


def test_reset_permitted_when_explicitly_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINERFY_RESET_ALLOWED", "1")
    assert _reset_permitted("aws-0-ap-southeast-1.pooler.supabase.com")
