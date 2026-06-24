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


def test_synthesize_force_skips_existing_course_audio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KGTS_TTS_ENABLED", "1")
    monkeypatch.setenv("KGTS_TTS_PROVIDER", "genie")
    monkeypatch.setenv("KGTS_TTS_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(tts_router, "_ensure_tts_enabled", lambda provider=None: None)

    calls: list[str] = []
    source_audio = tmp_path / "fresh.wav"
    source_audio.write_bytes(b"fresh-audio")

    def fake_synthesize(**kwargs):
        calls.append(kwargs["text"])
        return source_audio

    monkeypatch.setattr(tts_router.genie_tts_service, "synthesize", fake_synthesize)
    monkeypatch.setattr(tts_router, "validate_wav_audio_file", lambda path, label="audio": path)

    payload = tts_router.TtsSynthesizeRequest(
        text="当前页讲稿。",
        chapter_id="chapter-a",
        segment_id="slide-1-chunk-1",
        content_hash="stable",
    )
    persistent_path = tts_router._course_audio_path(payload, "当前页讲稿。", "zh")
    assert persistent_path is not None
    persistent_path.parent.mkdir(parents=True, exist_ok=True)
    persistent_path.write_bytes(b"old-audio")

    cached = asyncio.run(tts_router.synthesize(payload))
    refreshed = asyncio.run(tts_router.synthesize(payload.model_copy(update={"force": True})))

    assert calls == ["当前页讲稿。"]
    assert cached["cache_hit"] is True
    assert refreshed["cache_hit"] is False
    assert persistent_path.read_bytes() == b"fresh-audio"
