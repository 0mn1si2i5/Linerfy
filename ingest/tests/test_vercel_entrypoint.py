"""The Vercel Python runtime contract for the enrichment function.

The runtime auto-detects ``api/enrichment.py`` and requires a top-level
``handler`` that subclasses ``http.server.BaseHTTPRequestHandler`` (lowercase
``handler``, not the old ``Handler``). These tests load the real file as a
module and exercise the HTTP layer with a stubbed ``advance_once``, so they need
no database and no Vercel login.
"""

from __future__ import annotations

import importlib.util
import io
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

API_PATH = Path(__file__).resolve().parents[1] / "api" / "enrichment.py"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("_linerfy_enrichment", API_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Request:
    """A socket stand-in exposing the two file objects ``BaseHTTPRequestHandler``
    derives from the request's ``makefile``."""

    def __init__(self) -> None:
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs):
        return self.rfile if "r" in mode else self.wfile


def _instance(module):
    # Subclass so __init__ does not auto-dispatch do_* (handle) or close the
    # response stream (finish); the test drives the methods directly.
    class Silent(module.handler):
        wbufsize = -1  # makefile('wb') instead of socketserver._SocketWriter

        def handle(self) -> None:
            return

        def finish(self) -> None:
            return

    request = _Request()
    instance = Silent(request, ("127.0.0.1", 0), object())
    # These attributes are normally populated by parse_request()/handle(), which
    # the test does not run; supply them so the header machinery works.
    instance.request_version = "HTTP/1.1"
    instance.requestline = "POST / HTTP/1.1"
    instance.headers = {}
    return instance, request


def test_exports_lowercase_handler_subclass() -> None:
    module = _load_entrypoint()
    assert hasattr(module, "handler")
    assert issubclass(module.handler, BaseHTTPRequestHandler)


def test_do_get_is_a_health_check() -> None:
    instance, request = _instance(_load_entrypoint())
    instance.do_GET()
    assert b"200" in request.wfile.getvalue()
    assert b'"ok": true' in request.wfile.getvalue()


def test_do_post_rejects_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINERFY_WORKER_SECRET", raising=False)
    instance, request = _instance(_load_entrypoint())
    instance.do_POST()
    body = request.wfile.getvalue()
    assert b"503" in body
    assert b"worker not configured" in body


def test_do_post_rejects_bad_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINERFY_WORKER_SECRET", "s3cret")
    instance, request = _instance(_load_entrypoint())
    instance.headers = {"Authorization": "Bearer wrong"}
    instance.do_POST()
    assert b"401" in request.wfile.getvalue()


def test_do_post_valid_auth_enters_worker_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINERFY_WORKER_SECRET", "s3cret")
    module = _load_entrypoint()
    instance, request = _instance(module)
    instance.headers = {"Authorization": "Bearer s3cret"}
    monkeypatch.setattr(module, "advance_once", lambda: 1)
    instance.do_POST()
    assert b'"processed": 1' in request.wfile.getvalue()


def test_do_post_controlled_error_leaks_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LINERFY_WORKER_SECRET", "s3cret")
    module = _load_entrypoint()
    instance, request = _instance(module)
    instance.headers = {"Authorization": "Bearer s3cret"}

    def boom() -> int:
        raise RuntimeError("a secret review body and api-key must not leak")

    monkeypatch.setattr(module, "advance_once", boom)
    instance.do_POST()

    body = request.wfile.getvalue()
    assert b"500" in body
    assert b"worker error" in body
    assert b"a secret review body" not in body

    stderr = capsys.readouterr().err
    assert "a secret review body" not in stderr
    assert "Traceback" not in stderr
    assert "RuntimeError" in stderr  # only the error category is logged
