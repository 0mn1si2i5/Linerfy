"""Tests for the pure admin decisions: pause value and retention expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from linerfy_ingest.admin import is_expired, pause_value


def test_pause_value() -> None:
    assert pause_value(True) == "true"
    assert pause_value(False) == "false"


def test_is_expired_zero_retention_never_expires() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    fetched = now - timedelta(days=1000)
    assert not is_expired(fetched, 0, now)


def test_is_expired_after_window() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert is_expired(now - timedelta(days=30), 30, now)
    assert not is_expired(now - timedelta(days=29), 30, now)
