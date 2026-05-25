from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
PARENT_DIR = ROOT_DIR.parent
for path in (PARENT_DIR, ROOT_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ["KGTS_TTS_PROVIDER"] = "genie"
os.environ.setdefault("KGTS_TTS_GENIE_LOW_MEMORY", "1")
os.environ.setdefault("KGTS_TTS_ONNX_INTRA_OP_THREADS", "1")
os.environ.setdefault("KGTS_TTS_ONNX_INTER_OP_THREADS", "1")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from KGTS.config import load_root_env
from KGTS.core.tts_service import (
    _prepare_genie_runtime,
    _prepare_genie_import_path,
    genie_tts_service,
    get_tts_settings,
    get_tts_status,
)
from KGTS.core.tts_text import normalize_tts_text


load_root_env()
os.environ["KGTS_TTS_PROVIDER"] = "genie"
_prepare_genie_runtime(get_tts_settings())

_prepare_genie_import_path()
from KGTS.core.genie_low_memory import patch_genie_tts_low_memory

LOW_MEMORY_PATCHED = patch_genie_tts_low_memory()

app = FastAPI(title="KGTS Genie-TTS Proxy", version="1.0.0")


class LoadCharacterRequest(BaseModel):
    character_name: str | None = None
    predefined_character: str | None = None
    model_dir: str | None = None
    language: str | None = None


class ReferenceAudioRequest(BaseModel):
    character_name: str | None = None
    audio_path: str | None = None
    audio_text: str | None = None
    language: str | None = None


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1)
    character_name: str | None = None
    split_sentence: bool = True
    model_dir: str | None = None
    language: str | None = None
    reference_audio_path: str | None = None
    reference_text: str | None = None
    reference_language: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "success": True,
        "service": "kgts-genie-tts-proxy",
        "low_memory_patch": LOW_MEMORY_PATCHED,
    }


@app.get("/status")
def status() -> dict[str, Any]:
    payload = get_tts_status()
    payload["service"] = "kgts-genie-tts-proxy"
    payload["low_memory_patch"] = LOW_MEMORY_PATCHED
    return payload


@app.post("/load_character")
def load_character(payload: LoadCharacterRequest) -> dict[str, Any]:
    try:
        character_name = genie_tts_service.load_character(
            character_name=payload.character_name,
            predefined_character=payload.predefined_character,
            model_dir=payload.model_dir,
            language=payload.language,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "character_name": character_name}


@app.post("/set_reference_audio")
def set_reference_audio(payload: ReferenceAudioRequest) -> dict[str, Any]:
    try:
        genie_tts_service.set_reference_audio(
            character_name=payload.character_name,
            audio_path=payload.audio_path,
            audio_text=payload.audio_text,
            language=payload.language,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True}


@app.post("/tts")
def synthesize(payload: TtsRequest) -> FileResponse:
    settings = get_tts_settings()
    normalized = normalize_tts_text(payload.text, settings.language, payload.language)
    if not normalized.normalized_text:
        raise HTTPException(status_code=400, detail="Text is empty after cleaning.")
    if len(normalized.normalized_text) > settings.max_chars:
        raise HTTPException(status_code=413, detail=f"Text is too long. Limit: {settings.max_chars} characters.")

    started_at = time.perf_counter()
    try:
        audio_path = genie_tts_service.synthesize(
            text=normalized.normalized_text,
            character_name=payload.character_name,
            split_sentence=payload.split_sentence,
            model_dir=payload.model_dir,
            language=normalized.text_lang,
            reference_audio_path=payload.reference_audio_path,
            reference_text=payload.reference_text,
            reference_language=payload.reference_language,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    elapsed = time.perf_counter() - started_at
    print(
        f"[genie-proxy] synthesize done chars={len(normalized.normalized_text)} "
        f"file={audio_path.name} elapsed={elapsed:.1f}s",
        flush=True,
    )
    return FileResponse(audio_path, media_type="audio/wav", filename=audio_path.name)


@app.post("/stop")
def stop() -> dict[str, Any]:
    return {"success": True, "stopped": genie_tts_service.stop()}


@app.post("/clear_reference_audio_cache")
def clear_reference_audio_cache() -> dict[str, Any]:
    return {"success": True, "cleared": genie_tts_service.clear_reference_audio_cache()}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("KGTS_TTS_PROXY_HOST", "127.0.0.1")
    port = int(os.getenv("KGTS_TTS_PROXY_PORT", "9880"))
    uvicorn.run(app, host=host, port=port, workers=1)
