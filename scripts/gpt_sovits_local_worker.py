from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import traceback
import unicodedata
import wave
from pathlib import Path
from typing import Any

_LOG_PATH: Path | None = None
_PIPELINE: Any | None = None
_PIPELINE_CONFIG_KEY: str | None = None
_GPT_SOVITS_UNSAFE_CJK_SPEECH = {
    "兙": "克",
    "兡": "百克",
    "呣": "母",
    "嗯": "恩",
    "嗧": "加仑",
    "噷": "亨",
    "桛": "线轴",
    "烪": "火",
    "瓧": "十瓦",
    "瓰": "分瓦",
    "瓱": "毫瓦",
    "瓼": "厘瓦",
    "甅": "厘米",
}
_CONTROL_CATEGORY_PREFIXES = {"C"}


def _configure_stdio_encoding() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _configure_temp_environment() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    runtime_tmp = workspace_root / ".runtime" / "tts" / "tmp-env"
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    numba_cache_dir = runtime_tmp / "numba-cache"
    numba_cache_dir.mkdir(parents=True, exist_ok=True)

    os.environ["TMP"] = str(runtime_tmp)
    os.environ["TEMP"] = str(runtime_tmp)
    os.environ["TMPDIR"] = str(runtime_tmp)
    os.environ["NUMBA_CACHE_DIR"] = str(numba_cache_dir)


def _configure_external_python_path() -> None:
    executable = Path(sys.executable).resolve()
    env_root = executable.parent
    if not (env_root / "Library" / "bin").exists() and executable.parent.name.lower() == "scripts":
        env_root = executable.parent.parent
    candidate_dirs = [
        env_root / "Library" / "bin",
        env_root / "Scripts",
        env_root,
    ]
    existing_dirs = [str(path) for path in candidate_dirs if path.exists()]
    if not existing_dirs:
        return
    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    for path_text in reversed(existing_dirs):
        if path_text not in path_parts:
            path_parts.insert(0, path_text)
    os.environ["PATH"] = os.pathsep.join(path_parts)


def _log(message: str) -> None:
    import time

    text = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(text, file=sys.stderr, flush=True)
    if _LOG_PATH is not None:
        try:
            _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError:
            pass


def _write_wav(output_path: Path, sample_rate: int, chunks: list[Any]) -> None:
    _log("Writing wav")
    import numpy as np

    audio_data = np.concatenate([np.asarray(chunk) for chunk in chunks])
    if audio_data.dtype != np.int16:
        if audio_data.max(initial=0) <= 1.0 and audio_data.min(initial=0) >= -1.0:
            audio_data = (audio_data * 32767).astype(np.int16)
        else:
            audio_data = audio_data.astype(np.int16)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())


def _sanitize_worker_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for char, speech in _GPT_SOVITS_UNSAFE_CJK_SPEECH.items():
        text = text.replace(char, speech)
    text = "".join(" " if unicodedata.category(char)[0] in _CONTROL_CATEGORY_PREFIXES else char for char in text)
    return re.sub(r"\s+", " ", text).strip()


def _install_inference_stubs() -> None:
    import types

    import torch

    if "pytorch_lightning" not in sys.modules:
        lightning_module = types.ModuleType("pytorch_lightning")

        class LightningModule(torch.nn.Module):
            def save_hyperparameters(self, *args: Any, **kwargs: Any) -> None:
                return None

            def log(self, *args: Any, **kwargs: Any) -> None:
                return None

        lightning_module.LightningModule = LightningModule
        sys.modules["pytorch_lightning"] = lightning_module

    if "torchmetrics.classification" not in sys.modules:
        torchmetrics_module = types.ModuleType("torchmetrics")
        classification_module = types.ModuleType("torchmetrics.classification")

        class MulticlassAccuracy(torch.nn.Module):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__()

            def forward(self, *args: Any, **kwargs: Any) -> torch.Tensor:
                return torch.tensor(0.0)

            __call__ = forward

        classification_module.MulticlassAccuracy = MulticlassAccuracy
        torchmetrics_module.classification = classification_module
        sys.modules.setdefault("torchmetrics", torchmetrics_module)
        sys.modules["torchmetrics.classification"] = classification_module


def _run_status(runtime_root: Path, device: str) -> dict[str, Any]:
    modules = [
        "torch",
        "transformers",
        "librosa",
        "soundfile",
        "ffmpeg",
        "yaml",
        "LangSegment",
        "tqdm",
        "cn2an",
        "g2p_en",
        "wordsegment",
        "gradio",
        "pandas",
        "einops",
        "opencc",
        "typeguard",
        "onnxruntime",
        "scipy",
        "jieba_fast",
        "pypinyin",
    ]
    import importlib.util

    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    cuda_error = None
    if device.startswith("cuda") and "torch" not in missing:
        try:
            import torch

            if not torch.cuda.is_available():
                cuda_error = "CUDA requested by KGTS_TTS_GPT_SOVITS_DEVICE, but torch.cuda.is_available() is false."
        except Exception as exc:
            cuda_error = f"CUDA availability check failed: {exc}"

    return {
        "success": not missing and cuda_error is None,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "runtime_root": str(runtime_root),
        "missing_dependencies": missing,
        "cuda_error": cuda_error,
    }


def _get_pipeline(payload: dict[str, Any]) -> Any:
    global _PIPELINE, _PIPELINE_CONFIG_KEY

    config_path = str(payload["config_path"])
    config_key = str(payload.get("config_key") or config_path)
    runtime_root = Path(payload["runtime_root"]).resolve()
    if _PIPELINE is not None and _PIPELINE_CONFIG_KEY == config_key:
        return _PIPELINE

    _log(f"Using runtime root: {runtime_root}")
    os.chdir(runtime_root)

    for path in (runtime_root, runtime_root / "GPT_SoVITS"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)

    _log("Installing inference stubs")
    _install_inference_stubs()
    _log("Importing GPT-SoVITS TTS module")
    from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

    _log("Loading GPT-SoVITS config")
    tts_config = TTS_Config(config_path)
    _log("Initializing GPT-SoVITS pipeline")
    _PIPELINE = TTS(tts_config)
    _PIPELINE_CONFIG_KEY = config_key
    return _PIPELINE


def _run_synthesis(payload: dict[str, Any]) -> dict[str, Any]:
    _log("Importing numpy")
    import numpy as np

    output_path = Path(payload["output_path"]).resolve()
    pipeline = _get_pipeline(payload)
    inputs = dict(payload["inputs"])
    inputs["text"] = _sanitize_worker_text(str(inputs.get("text", "")))
    inputs["prompt_text"] = _sanitize_worker_text(str(inputs.get("prompt_text", "")))
    _log("Running GPT-SoVITS inference")
    chunks = []
    sample_rate = None
    for sr, audio in pipeline.run(inputs):
        sample_rate = int(sr)
        chunks.append(np.asarray(audio))
        _log(f"Received audio chunk at {sample_rate} Hz")

    if sample_rate is None or not chunks:
        raise RuntimeError("GPT-SoVITS completed without audio data.")

    _write_wav(output_path, sample_rate, chunks)
    _log(f"Finished synthesis: {output_path}")
    if not output_path.is_file() or output_path.stat().st_size <= 44:
        raise RuntimeError("GPT-SoVITS produced an empty wav file.")

    return {
        "success": True,
        "output_path": str(output_path),
        "file_size": output_path.stat().st_size,
        "sample_rate": sample_rate,
    }


@contextlib.contextmanager
def _protocol_response_stream():
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        protocol_fd = os.dup(sys.stdout.fileno())
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    except (AttributeError, OSError):
        yield sys.stdout
        return

    with os.fdopen(protocol_fd, "w", encoding="utf-8", errors="replace", buffering=1) as stream:
        yield stream


def _serve() -> int:
    with _protocol_response_stream() as response_stream:
        _log("Starting persistent worker")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            request_id = None
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("Worker request must be an object.")
                request_id = request.get("id")
                payload = request.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError("Worker request payload must be an object.")
                with contextlib.redirect_stdout(sys.stderr):
                    result = _run_synthesis(payload)
                result["id"] = request_id
                print(json.dumps(result, ensure_ascii=False), file=response_stream, flush=True)
            except BaseException as exc:
                response = {
                    "success": False,
                    "id": request_id,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                print(json.dumps(response, ensure_ascii=False), file=response_stream, flush=True)
    return 0


def main() -> int:
    _configure_stdio_encoding()
    _configure_temp_environment()
    _configure_external_python_path()
    os.environ.setdefault("PYTORCH_JIT", "0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    parser = argparse.ArgumentParser(description="KGTS GPT-SoVITS local subprocess worker")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--runtime-root")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--payload")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()

    try:
        if args.serve:
            return _serve()
        if args.status:
            if not args.runtime_root:
                raise ValueError("--runtime-root is required with --status")
            result = _run_status(Path(args.runtime_root).resolve(), args.device)
        else:
            if not args.payload:
                raise ValueError("--payload is required")
            payload_path = Path(args.payload)
            global _LOG_PATH
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            _LOG_PATH = Path(payload.get("log_path")).resolve() if payload.get("log_path") else payload_path.with_suffix(".log")
            _log(f"Loaded payload: {payload_path}")
            result = _run_synthesis(payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("success", False) else 2
    except BaseException as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
