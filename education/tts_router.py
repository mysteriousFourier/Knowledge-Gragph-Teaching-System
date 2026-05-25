from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from KGTS.core.tts_service import (
    genie_tts_service,
    get_tts_settings,
    get_tts_status,
    gpt_sovits_local_service,
    is_tts_cache_admin_enabled,
    tts_audio_cache,
)
from KGTS.core.tts_text import normalize_tts_text


router = APIRouter(prefix="/api/tts", tags=["tts"])

DEFAULT_SEGMENT_CHARS = 260


def _tts_log(message: str) -> None:
    print(f"[tts] {time.strftime('%H:%M:%S')} {message}", flush=True)


class TtsLoadCharacterRequest(BaseModel):
    character_name: str | None = None
    predefined_character: str | None = None
    model_dir: str | None = None
    language: str | None = None


class TtsReferenceAudioRequest(BaseModel):
    character_name: str | None = None
    audio_path: str
    audio_text: str | None = None
    language: str | None = None


class TtsSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    character_name: str | None = None
    split_sentence: bool = True
    model_dir: str | None = None
    language: str | None = None
    reference_audio_path: str | None = None
    reference_text: str | None = None
    reference_language: str | None = None
    speed_factor: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    temperature: float | None = None
    repetition_penalty: float | None = None
    text_split_method: str | None = None


class TtsSegmentRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: str | None = None
    max_chars: int | None = Field(default=None, ge=80, le=800)


class TtsUnloadCharacterRequest(BaseModel):
    character_name: str


def _split_tts_text(text: str, *, max_chars: int) -> list[str]:
    normalized = re.sub(r"[ \t\f\v]+", " ", text.replace("\r\n", "\n")).strip()
    if not normalized:
        return []

    def split_oversized(piece: str) -> list[str]:
        if len(piece) <= max_chars:
            return [piece]
        for pattern in (r"(?<=[。！？!?])\s*", r"(?<=[；;])\s*", r"(?<=[，,、:：])\s+|(?<=[，,、:：])"):
            parts = [part.strip() for part in re.split(pattern, piece) if part.strip()]
            if len(parts) > 1 and max(len(part) for part in parts) < len(piece):
                result: list[str] = []
                for part in parts:
                    result.extend(split_oversized(part))
                return result
        return [piece[start : start + max_chars].strip() for start in range(0, len(piece), max_chars) if piece[start : start + max_chars].strip()]

    pieces: list[str] = []
    for paragraph in [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n+", normalized) if part.strip()] or [re.sub(r"\s+", " ", normalized).strip()]:
        pieces.extend(split_oversized(paragraph))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{piece}" if not current else f"{current} {piece}"
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _long_text_error(length: int, limit: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=(
            f"Text is too long for one TTS request ({length} normalized characters, limit {limit}). "
            "Call /api/tts/segments first and synthesize segments while playing previous audio."
        ),
    )


def _audio_url(path: Path) -> str:
    return f"/api/tts/audio/{path.name}"


def _resolve_audio_path(file_name: str) -> Path:
    settings = get_tts_settings()
    requested = Path(file_name)
    if requested.name != file_name or requested.suffix.lower() != ".wav":
        raise HTTPException(status_code=404, detail="Audio file not found.")

    search_dirs = [
        settings.output_dir / "cache",
        settings.output_dir,
    ]
    for base_dir in search_dirs:
        base = base_dir.resolve()
        candidate = (base / requested.name).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    raise HTTPException(status_code=404, detail="Audio file not found.")


def _ensure_tts_enabled(provider: str | None = None) -> None:
    settings = get_tts_settings()
    if not settings.enabled:
        raise HTTPException(status_code=503, detail="TTS is disabled. Set KGTS_TTS_ENABLED=1 locally to enable it.")
    if provider and settings.provider != provider:
        raise HTTPException(status_code=400, detail=f"TTS provider is {settings.provider}, not {provider}.")


def _ensure_cache_admin_enabled() -> None:
    if not is_tts_cache_admin_enabled():
        raise HTTPException(status_code=403, detail="TTS cache administration is disabled in this environment.")


async def _synthesize_via_server(payload: TtsSynthesizeRequest) -> Path:
    settings = get_tts_settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalize_tts_text(payload.text, settings.language, payload.language)
    body: dict[str, Any] = {
        "text": normalized.normalized_text,
        "character_name": payload.character_name or settings.character_name or settings.predefined_character,
        "split_sentence": payload.split_sentence,
    }
    if normalized.text_lang:
        body["language"] = normalized.text_lang

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(f"{settings.server_url}/tts", json=body)
        response.raise_for_status()
        media_type = response.headers.get("content-type", "")
        if "application/json" in media_type:
            data = response.json()
            audio_url = data.get("audio_url") or data.get("url") or data.get("file")
            if not audio_url:
                raise HTTPException(status_code=502, detail="Genie-TTS server did not return an audio URL.")
            audio_url_text = str(audio_url)
            if audio_url_text.startswith("/"):
                audio_url_text = f"{settings.server_url}{audio_url_text}"
            audio_response = await client.get(audio_url_text)
            audio_response.raise_for_status()
            content = audio_response.content
        else:
            content = response.content

    audio_path = settings.output_dir / f"tts-server-{hashlib.sha256(content).hexdigest()[:24]}.wav"
    audio_path.write_bytes(content)
    genie_tts_service.cleanup_audio_dir(settings.output_dir, settings.max_audio_files)
    return audio_path


async def _synthesize_via_gpt_sovits_server(payload: TtsSynthesizeRequest) -> Path:
    settings = get_tts_settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalize_tts_text(payload.text, settings.language, payload.language)
    body: dict[str, Any] = {
        "text": normalized.normalized_text,
        "text_lang": normalized.text_lang,
        "ref_audio_path": payload.reference_audio_path or settings.reference_audio_path,
        "prompt_text": payload.reference_text or settings.reference_text,
        "prompt_lang": payload.reference_language or settings.reference_language or settings.language,
        "top_k": payload.top_k or settings.top_k,
        "top_p": payload.top_p if payload.top_p is not None else settings.top_p,
        "temperature": payload.temperature if payload.temperature is not None else settings.temperature,
        "text_split_method": payload.text_split_method or settings.text_split_method,
        "batch_size": settings.batch_size,
        "batch_threshold": settings.batch_threshold,
        "split_bucket": settings.split_bucket,
        "speed_factor": payload.speed_factor if payload.speed_factor is not None else settings.speed_factor,
        "streaming_mode": False,
        "parallel_infer": settings.parallel_infer,
        "repetition_penalty": payload.repetition_penalty
        if payload.repetition_penalty is not None
        else settings.repetition_penalty,
    }

    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(f"{settings.server_url}/tts", json=body)
        response.raise_for_status()
        media_type = response.headers.get("content-type", "")
        if "application/json" in media_type:
            data = response.json()
            message = data.get("message") or data.get("detail") or data.get("Exception") or str(data)
            raise HTTPException(status_code=502, detail=f"GPT-SoVITS server did not return audio: {message}")
        content = response.content

    if not content:
        raise HTTPException(status_code=502, detail="GPT-SoVITS server returned an empty audio response.")

    audio_path = settings.output_dir / f"tts-gpt-sovits-{hashlib.sha256(content).hexdigest()[:24]}.wav"
    audio_path.write_bytes(content)
    genie_tts_service.cleanup_audio_dir(settings.output_dir, settings.max_audio_files)
    return audio_path


@router.get("/status")
async def tts_status() -> dict[str, Any]:
    return get_tts_status()


@router.get("/cache/status")
async def cache_status() -> dict[str, Any]:
    _ensure_cache_admin_enabled()
    settings = get_tts_settings()
    return {"success": True, **tts_audio_cache.status(settings)}


@router.post("/cache/clear")
async def clear_audio_cache() -> dict[str, Any]:
    _ensure_cache_admin_enabled()
    settings = get_tts_settings()
    result = tts_audio_cache.clear(settings, preserve_keys=gpt_sovits_local_service.active_cache_keys())
    return {"success": True, **result}


@router.post("/segments")
async def split_segments(payload: TtsSegmentRequest) -> dict[str, Any]:
    settings = get_tts_settings()
    normalized = normalize_tts_text(payload.text, settings.language, payload.language)
    max_chars = payload.max_chars or min(settings.max_chars, DEFAULT_SEGMENT_CHARS)
    segments = _split_tts_text(normalized.normalized_text, max_chars=max_chars)
    _tts_log(
        "segments "
        f"provider={settings.provider} chars={len(normalized.normalized_text)} "
        f"segments={len(segments)} max_chars={max_chars} lang={normalized.text_lang}"
    )
    return {
        "success": True,
        "segments": [{"index": index, "text": text, "length": len(text)} for index, text in enumerate(segments)],
        "segment_count": len(segments),
        "normalized_text_length": len(normalized.normalized_text),
        "text_lang": normalized.text_lang,
        "max_chars": max_chars,
    }


@router.post("/load-character")
async def load_character(payload: TtsLoadCharacterRequest) -> dict[str, Any]:
    _ensure_tts_enabled("genie")
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


@router.post("/reference-audio")
async def set_reference_audio(payload: TtsReferenceAudioRequest) -> dict[str, Any]:
    _ensure_tts_enabled("genie")
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


@router.post("/synthesize")
async def synthesize(payload: TtsSynthesizeRequest) -> dict[str, Any]:
    settings = get_tts_settings()
    _ensure_tts_enabled()
    normalized = normalize_tts_text(payload.text, settings.language, payload.language)
    text = normalized.normalized_text
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty after cleaning.")
    if len(text) > settings.max_chars:
        raise _long_text_error(len(text), settings.max_chars)

    started_at = time.perf_counter()
    request_id = hashlib.sha256(f"{time.time_ns()}:{text}".encode("utf-8")).hexdigest()[:8]
    _tts_log(
        "synthesize:start "
        f"id={request_id} provider={settings.provider} chars={len(text)} "
        f"lang={normalized.text_lang}"
    )

    try:
        if settings.provider == "gpt_sovits_local":
            result = await run_in_threadpool(
                gpt_sovits_local_service.synthesize,
                text=payload.text,
                language=payload.language,
                reference_audio_path=payload.reference_audio_path,
                reference_text=payload.reference_text,
                reference_language=payload.reference_language,
                speed_factor=payload.speed_factor,
                top_k=payload.top_k,
                top_p=payload.top_p,
                temperature=payload.temperature,
                repetition_penalty=payload.repetition_penalty,
                text_split_method=payload.text_split_method,
            )
            elapsed = time.perf_counter() - started_at
            _tts_log(
                "synthesize:done "
                f"id={request_id} provider={result.provider} "
                f"cache={'hit' if result.cache_hit else 'miss'} "
                f"file={result.path.name} elapsed={elapsed:.1f}s"
            )
            return {
                "success": True,
                "provider": result.provider,
                "audio_url": _audio_url(result.path),
                "cache_hit": result.cache_hit,
                "cache_key": result.cache_key,
                "normalized_text_length": result.normalized_text_length,
                "text_length": result.normalized_text_length,
                "text_lang": result.text_lang,
            }
        if settings.provider == "genie_server":
            audio_path = await _synthesize_via_server(payload.model_copy(update={"text": text}))
        elif settings.provider == "gpt_sovits_server":
            audio_path = await _synthesize_via_gpt_sovits_server(payload.model_copy(update={"text": text}))
        elif settings.provider == "genie":
            audio_path = await run_in_threadpool(
                genie_tts_service.synthesize,
                text=text,
                character_name=payload.character_name,
                split_sentence=payload.split_sentence,
                model_dir=payload.model_dir,
                language=normalized.text_lang,
                reference_audio_path=payload.reference_audio_path,
                reference_text=payload.reference_text,
                reference_language=payload.reference_language,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported TTS provider: {settings.provider}")
    except HTTPException:
        elapsed = time.perf_counter() - started_at
        _tts_log(
            "synthesize:failed "
            f"id={request_id} provider={settings.provider} elapsed={elapsed:.1f}s "
            f"status=HTTPException"
        )
        raise
    except ValueError as exc:
        elapsed = time.perf_counter() - started_at
        _tts_log(
            "synthesize:failed "
            f"id={request_id} provider={settings.provider} elapsed={elapsed:.1f}s "
            f"error={exc}"
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        elapsed = time.perf_counter() - started_at
        _tts_log(
            "synthesize:failed "
            f"id={request_id} provider={settings.provider} elapsed={elapsed:.1f}s "
            f"error={exc}"
        )
        raise HTTPException(status_code=502, detail=f"TTS server request failed: {exc}") from exc
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        _tts_log(
            "synthesize:failed "
            f"id={request_id} provider={settings.provider} elapsed={elapsed:.1f}s "
            f"error={exc}"
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed = time.perf_counter() - started_at
    _tts_log(
        "synthesize:done "
        f"id={request_id} provider={settings.provider} cache=miss "
        f"file={audio_path.name} elapsed={elapsed:.1f}s"
    )
    return {
        "success": True,
        "provider": settings.provider,
        "audio_url": _audio_url(audio_path),
        "cache_hit": False,
        "cache_key": None,
        "normalized_text_length": len(text),
        "text_length": len(text),
        "text_lang": normalized.text_lang,
    }


@router.get("/audio/{file_name}", include_in_schema=False)
async def audio_file(file_name: str) -> FileResponse:
    path = _resolve_audio_path(file_name)
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=path.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/unload-character")
async def unload_character(payload: TtsUnloadCharacterRequest) -> dict[str, Any]:
    _ensure_tts_enabled("genie")
    try:
        unloaded = genie_tts_service.unload_character(payload.character_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "unloaded": unloaded}


@router.post("/stop")
async def stop_tts() -> dict[str, Any]:
    _ensure_tts_enabled("genie")
    try:
        stopped = genie_tts_service.stop()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, "stopped": stopped}


@router.post("/clear-cache")
async def clear_legacy_cache() -> dict[str, Any]:
    _ensure_tts_enabled()
    settings = get_tts_settings()
    try:
        cleared_provider_cache = False
        if settings.provider == "genie":
            cleared_provider_cache = genie_tts_service.clear_reference_audio_cache()
        removed_audio_files = 0
        if settings.output_dir.exists():
            for path in settings.output_dir.glob("*.wav"):
                path.unlink(missing_ok=True)
                removed_audio_files += 1
        temp_dir = settings.output_dir / "tmp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        cache_result = tts_audio_cache.clear(settings, preserve_keys=gpt_sovits_local_service.active_cache_keys())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "success": True,
        "cleared_provider_cache": cleared_provider_cache,
        "removed_audio_files": removed_audio_files + int(cache_result.get("removed_files", 0)),
    }
