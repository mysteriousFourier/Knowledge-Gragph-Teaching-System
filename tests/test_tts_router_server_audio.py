from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from KGTS.education import tts_router


class _FakeAsyncClient:
    def __init__(self, *, timeout: Any = None) -> None:
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>not audio</html>" * 8,
            headers={"content-type": "text/html"},
            request=httpx.Request("POST", url),
        )


def test_synthesize_via_server_rejects_non_wav_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KGTS_TTS_PROVIDER", "genie_server")
    monkeypatch.setenv("KGTS_TTS_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(tts_router.httpx, "AsyncClient", _FakeAsyncClient)

    payload = tts_router.TtsSynthesizeRequest(text="测试语音。")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(tts_router._synthesize_via_server(payload))

    assert exc_info.value.status_code == 502
    assert "valid WAV" in str(exc_info.value.detail)
    assert not list(tmp_path.glob("*.wav"))
