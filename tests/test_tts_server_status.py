from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from KGTS.core import tts_service


class _JsonResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _set_genie_server_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KGTS_TTS_ENABLED", "1")
    monkeypatch.setenv("KGTS_TTS_PROVIDER", "genie_server")
    monkeypatch.setenv("KGTS_TTS_SERVER_URL", "http://127.0.0.1:9880")


def test_genie_server_status_uses_health_before_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_genie_server_env(monkeypatch)
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float = 0):
        calls.append(url)
        if url.endswith("/health"):
            return _JsonResponse({"success": True, "service": "proxy"})
        return _JsonResponse({"success": True, "available": True, "detail": "ready"})

    monkeypatch.setattr(tts_service.urllib.request, "urlopen", fake_urlopen)

    status = tts_service.get_tts_status()

    assert status["server_reachable"] is True
    assert status["available"] is True
    assert status["detail"] == "ready"
    assert calls == ["http://127.0.0.1:9880/health", "http://127.0.0.1:9880/status"]


def test_genie_server_status_distinguishes_reachable_proxy_from_failed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_genie_server_env(monkeypatch)

    def fake_urlopen(url: str, timeout: float = 0):
        if url.endswith("/health"):
            return _JsonResponse({"success": True, "service": "proxy"})
        raise TimeoutError("status timed out")

    monkeypatch.setattr(tts_service.urllib.request, "urlopen", fake_urlopen)

    status = tts_service.get_tts_status()

    assert status["server_reachable"] is True
    assert status["available"] is False
    assert "reachable" in status["detail"]
    assert "status endpoint failed" in status["detail"]


def test_genie_server_status_falls_back_when_health_endpoint_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_genie_server_env(monkeypatch)

    def fake_urlopen(url: str, timeout: float = 0):
        if url.endswith("/health"):
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        return _JsonResponse({"success": True, "available": True})

    monkeypatch.setattr(tts_service.urllib.request, "urlopen", fake_urlopen)

    status = tts_service.get_tts_status()

    assert status["server_reachable"] is True
    assert status["available"] is True
