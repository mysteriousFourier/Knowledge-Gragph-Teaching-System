from __future__ import annotations

import gc
import hashlib
import os
from pathlib import Path
from typing import Any


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    payload = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:20]


def _write_fp32_external_cache(fp16_path: Path, fp32_path: Path, *, chunk_mb: int) -> None:
    import numpy as np

    expected_size = fp16_path.stat().st_size * 2
    if fp32_path.exists() and fp32_path.stat().st_size == expected_size:
        return

    fp32_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = fp32_path.with_suffix(fp32_path.suffix + ".tmp")
    chunk_size = max(chunk_mb, 1) * 1024 * 1024
    if chunk_size % 2:
        chunk_size += 1

    with fp16_path.open("rb") as source, tmp_path.open("wb") as target:
        while True:
            raw = source.read(chunk_size)
            if not raw:
                break
            if len(raw) % 2:
                raw += source.read(1)
            fp32 = np.frombuffer(raw, dtype=np.float16).astype(np.float32)
            target.write(fp32.tobytes())
            del fp32
    os.replace(tmp_path, fp32_path)


def _patch_model_external_data(model: Any, *, external_location: str) -> int:
    import onnx

    count = 0
    for tensor in model.graph.initializer:
        if tensor.data_location != onnx.TensorProto.EXTERNAL:
            continue
        values = {entry.key: entry.value for entry in tensor.external_data}
        offset = values.get("offset", "0")
        length = values.get("length")
        del tensor.external_data[:]
        for key, value in (
            ("location", external_location),
            ("offset", offset),
            ("length", length),
        ):
            if value is None:
                continue
            entry = tensor.external_data.add()
            entry.key = key
            entry.value = str(value)
        tensor.data_location = onnx.TensorProto.EXTERNAL
        count += 1
    return count


def _low_memory_session_options(onnxruntime: Any, sess_options: Any | None) -> Any:
    options = sess_options or onnxruntime.SessionOptions()
    if _env_flag("KGTS_TTS_ONNX_LOW_MEMORY_OPTIONS", True):
        options.intra_op_num_threads = max(_env_int("KGTS_TTS_ONNX_INTRA_OP_THREADS", 1), 1)
        options.inter_op_num_threads = max(_env_int("KGTS_TTS_ONNX_INTER_OP_THREADS", 1), 1)
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = _env_flag("KGTS_TTS_ONNX_CPU_MEM_ARENA", False)
        options.enable_mem_pattern = _env_flag("KGTS_TTS_ONNX_MEM_PATTERN", False)
    return options


def patch_genie_tts_low_memory(*, cache_dir: str | Path | None = None) -> bool:
    """Patch Genie-TTS so fp16 external weights are expanded on disk, not in one Python buffer.

    Genie converted models keep FP16 external weights on disk while the ONNX graph
    points at FP32 offsets. The upstream loader expands the entire FP16 file into
    a FP32 bytes object, injects it into the ModelProto, then serializes the full
    model again for ONNX Runtime. On a 1 GB VM that creates multiple large copies
    during model loading. This patch preserves the existing ONNX FP32 layout but
    streams the FP16 file into a cached FP32 external-data file and lets ORT load
    that file directly.
    """
    if not _env_flag("KGTS_TTS_GENIE_LOW_MEMORY", True):
        return False

    import onnx
    import onnxruntime
    from onnxruntime import InferenceSession

    from genie_tts import ModelManager

    if getattr(ModelManager, "_kgts_low_memory_patch", False):
        return True

    root = Path(cache_dir or os.getenv("KGTS_TTS_ONNX_CACHE_DIR") or ".runtime/tts/onnx-fp32-cache")
    root.mkdir(parents=True, exist_ok=True)
    chunk_mb = max(_env_int("KGTS_TTS_ONNX_CONVERT_CHUNK_MB", 8), 1)

    def load_session_with_external_fp32_cache(
        onnx_path: str,
        fp16_bin_path: str,
        providers: list[str],
        sess_options: Any | None = None,
    ) -> InferenceSession:
        source_onnx = Path(onnx_path)
        source_fp16 = Path(fp16_bin_path)
        if not source_onnx.exists():
            raise FileNotFoundError(f"ONNX Model not found: {onnx_path}")
        if not source_fp16.exists():
            raise FileNotFoundError(f"FP16 Weight file not found: {fp16_bin_path}")

        model_key = hashlib.sha256(
            f"{_fingerprint(source_onnx)}:{_fingerprint(source_fp16)}".encode("utf-8")
        ).hexdigest()[:20]
        weights_key = _fingerprint(source_fp16)
        fp32_cache = root / f"{source_fp16.stem}-{weights_key}.fp32.bin"
        patched_onnx = root / f"{source_onnx.stem}-{model_key}.onnx"

        _write_fp32_external_cache(source_fp16, fp32_cache, chunk_mb=chunk_mb)

        if not patched_onnx.exists() or patched_onnx.stat().st_mtime_ns < source_onnx.stat().st_mtime_ns:
            model = onnx.load(str(source_onnx), load_external_data=False)
            external_count = _patch_model_external_data(model, external_location=fp32_cache.name)
            if external_count == 0:
                return InferenceSession(
                    str(source_onnx),
                    providers=providers,
                    sess_options=_low_memory_session_options(onnxruntime, sess_options),
                )
            tmp_onnx = patched_onnx.with_suffix(".onnx.tmp")
            onnx.save(model, str(tmp_onnx))
            os.replace(tmp_onnx, patched_onnx)
            del model
            gc.collect()

        return InferenceSession(
            str(patched_onnx),
            providers=providers,
            sess_options=_low_memory_session_options(onnxruntime, sess_options),
        )

    ModelManager.load_session_with_fp16_conversion = load_session_with_external_fp32_cache
    ModelManager._kgts_low_memory_patch = True
    return True
