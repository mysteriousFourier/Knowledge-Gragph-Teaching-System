from __future__ import annotations

import contextlib
import hashlib
import importlib
import importlib.util
import io
import json
import os
import platform
import subprocess
import sys
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .tts_text import FORMULA_POLICY_VERSION, NormalizedTtsText, normalize_tts_text
from .path_policy import outside_project_paths, project_local_only, project_path_error


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TTS_RUNTIME_DIR = ROOT_DIR / ".runtime" / "tts"
DEFAULT_TTS_AUDIO_DIR = DEFAULT_TTS_RUNTIME_DIR / "audio"
DEFAULT_GENIE_REPO_DIR = ROOT_DIR / "third_party" / "Genie-TTS"
DEFAULT_TTS_MODEL_DIR = ROOT_DIR / "models" / "tts"
DEFAULT_GENIE_DATA_DIR = DEFAULT_TTS_MODEL_DIR / "GenieData"
DEFAULT_SHU_GENIE_MODEL_DIR = DEFAULT_TTS_MODEL_DIR / "shu"
DEFAULT_GPT_SOVITS_ROOT = DEFAULT_TTS_RUNTIME_DIR / "gpt-sovits"
DEFAULT_SHU_GPT_WEIGHTS = "GPT_weights_v2/shu-e15.ckpt"
DEFAULT_SHU_SOVITS_WEIGHTS = "SoVITS_weights_v2/shu_e8_s368.pth"
DEFAULT_SHU_REFERENCE_AUDIO = "models/tts/shu/reference/shu.wav"
LEGACY_SHU_REFERENCE_AUDIO = "logs/shu/5-wav32k/交谈1.wav_0000000000_0000142080.wav"
DEFAULT_SHU_REFERENCE_TEXT = "我是谁？答案只在于我所见所遇的一切。"
GPT_SOVITS_WORKER_SCRIPT = ROOT_DIR / "scripts" / "gpt_sovits_local_worker.py"
GPT_SOVITS_DEPENDENCY_MODULES = [
    "torch",
    "pytorch_lightning",
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
    "torchmetrics",
    "einops",
    "opencc",
    "typeguard",
    "onnxruntime",
    "scipy",
    "jieba_fast",
    "pypinyin",
]
_EXTERNAL_ENV_STATUS_LOCK = threading.RLock()
_EXTERNAL_ENV_STATUS_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _env_text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    value = _env_text(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env_text(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _as_path(value: str | None, *, default: Path | None = None) -> Path | None:
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _tts_path_policy_violations(settings: TtsSettings) -> list[dict[str, Any]]:
    return outside_project_paths(
        [
            ("KGTS_TTS_OUTPUT_DIR", settings.output_dir),
            ("KGTS_TTS_GENIE_DATA_DIR", settings.genie_data_dir),
            ("KGTS_TTS_MODEL_DIR", settings.model_dir),
            ("KGTS_TTS_REFERENCE_AUDIO", settings.reference_audio_path),
            ("KGTS_TTS_GPT_SOVITS_ROOT", settings.gpt_sovits_root),
            ("KGTS_TTS_GPT_SOVITS_PYTHON", settings.gpt_sovits_python),
        ]
    )


def _raise_if_tts_paths_outside_project(settings: TtsSettings) -> None:
    violations = _tts_path_policy_violations(settings)
    if violations:
        detail = "; ".join(f"{item['label']}={item['path']}" for item in violations)
        raise RuntimeError(f"TTS path is outside project root while KGTS_PROJECT_LOCAL_ONLY=1: {detail}")


def _default_gpt_sovits_python(gpt_root: Path) -> str:
    candidates = [
        gpt_root / ".conda-tts" / "python.exe",
        gpt_root / ".conda-tts" / "Scripts" / "python.exe",
        gpt_root / ".venv" / "Scripts" / "python.exe",
        gpt_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _file_fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    return f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"


@contextlib.contextmanager
def _pushd(path: Path):
    old_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


@dataclass(frozen=True)
class TtsSettings:
    enabled: bool
    provider: str
    server_url: str
    character_name: str
    predefined_character: str
    model_dir: str
    language: str
    reference_audio_path: str
    reference_text: str
    reference_language: str
    output_dir: Path
    genie_data_dir: Path
    max_chars: int
    max_audio_files: int
    gpt_sovits_root: Path
    gpt_sovits_gpt_weights: str
    gpt_sovits_sovits_weights: str
    gpt_sovits_device: str
    gpt_sovits_python: str
    gpt_sovits_is_half: bool
    text_split_method: str
    batch_size: int
    batch_threshold: float
    split_bucket: bool
    parallel_infer: bool
    speed_factor: float
    top_k: int
    top_p: float
    temperature: float
    repetition_penalty: float
    cache_enabled: bool
    cache_ttl_hours: int
    cache_max_files: int
    cache_max_mb: int


@dataclass(frozen=True)
class TtsSynthesisResult:
    path: Path
    cache_hit: bool
    cache_key: str
    normalized_text_length: int
    provider: str
    text_lang: str


def get_tts_settings() -> TtsSettings:
    provider = _env_text("KGTS_TTS_PROVIDER", "genie").lower()
    enabled_env = os.getenv("KGTS_TTS_ENABLED")
    enabled = _env_flag("KGTS_TTS_ENABLED", provider not in {"", "disabled", "none", "off"})

    if enabled_env and provider in {"", "disabled", "none", "off"}:
        provider = "genie"
    if not enabled:
        provider = "disabled"

    output_dir = _as_path(_env_text("KGTS_TTS_OUTPUT_DIR")) or DEFAULT_TTS_AUDIO_DIR
    genie_data_dir = _as_path(_env_text("KGTS_TTS_GENIE_DATA_DIR")) or DEFAULT_GENIE_DATA_DIR
    gpt_root = _as_path(_env_text("KGTS_TTS_GPT_SOVITS_ROOT"), default=DEFAULT_GPT_SOVITS_ROOT)
    assert gpt_root is not None
    device = _env_text("KGTS_TTS_GPT_SOVITS_DEVICE", "cuda").lower()

    return TtsSettings(
        enabled=enabled,
        provider=provider,
        server_url=_env_text("KGTS_TTS_SERVER_URL", "http://127.0.0.1:9880").rstrip("/"),
        character_name=_env_text("KGTS_TTS_CHARACTER_NAME", "shu"),
        predefined_character=_env_text("KGTS_TTS_PREDEFINED_CHARACTER"),
        model_dir=_env_text("KGTS_TTS_MODEL_DIR", str(DEFAULT_SHU_GENIE_MODEL_DIR)),
        language=_env_text("KGTS_TTS_LANGUAGE", "zh").lower(),
        reference_audio_path=_env_text(
            "KGTS_TTS_REFERENCE_AUDIO",
            DEFAULT_SHU_REFERENCE_AUDIO,
        ),
        reference_text=_env_text("KGTS_TTS_REFERENCE_TEXT", DEFAULT_SHU_REFERENCE_TEXT),
        reference_language=_env_text("KGTS_TTS_REFERENCE_LANGUAGE", "zh").lower(),
        output_dir=output_dir,
        genie_data_dir=genie_data_dir,
        max_chars=_env_int("KGTS_TTS_MAX_CHARS", 1200),
        max_audio_files=max(_env_int("KGTS_TTS_MAX_AUDIO_FILES", 200), 1),
        gpt_sovits_root=gpt_root,
        gpt_sovits_gpt_weights=_env_text("KGTS_TTS_GPT_SOVITS_GPT_WEIGHTS", DEFAULT_SHU_GPT_WEIGHTS),
        gpt_sovits_sovits_weights=_env_text("KGTS_TTS_GPT_SOVITS_SOVITS_WEIGHTS", DEFAULT_SHU_SOVITS_WEIGHTS),
        gpt_sovits_device=device,
        gpt_sovits_python=_env_text("KGTS_TTS_GPT_SOVITS_PYTHON", _default_gpt_sovits_python(gpt_root)),
        gpt_sovits_is_half=_env_flag("KGTS_TTS_GPT_SOVITS_HALF", device != "cpu"),
        text_split_method=_env_text("KGTS_TTS_TEXT_SPLIT_METHOD", "cut5"),
        batch_size=max(_env_int("KGTS_TTS_BATCH_SIZE", 1), 1),
        batch_threshold=_env_float("KGTS_TTS_BATCH_THRESHOLD", 0.75),
        split_bucket=_env_flag("KGTS_TTS_SPLIT_BUCKET", True),
        parallel_infer=_env_flag("KGTS_TTS_PARALLEL_INFER", True),
        speed_factor=_env_float("KGTS_TTS_SPEED_FACTOR", 1.0),
        top_k=max(_env_int("KGTS_TTS_TOP_K", 15), 1),
        top_p=_env_float("KGTS_TTS_TOP_P", 1.0),
        temperature=_env_float("KGTS_TTS_TEMPERATURE", 1.0),
        repetition_penalty=_env_float("KGTS_TTS_REPETITION_PENALTY", 1.35),
        cache_enabled=_env_flag("KGTS_TTS_AUDIO_CACHE_ENABLED", True),
        cache_ttl_hours=max(_env_int("KGTS_TTS_AUDIO_CACHE_TTL_HOURS", 72), 0),
        cache_max_files=max(_env_int("KGTS_TTS_AUDIO_CACHE_MAX_FILES", 300), 1),
        cache_max_mb=max(_env_int("KGTS_TTS_AUDIO_CACHE_MAX_MB", 1024), 1),
    )


def resolve_gpt_sovits_path(settings: TtsSettings, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = settings.gpt_sovits_root / path
    return path


def get_gpt_sovits_paths(settings: TtsSettings) -> dict[str, Path]:
    reference_audio = resolve_gpt_sovits_path(settings, settings.reference_audio_path)
    if not reference_audio.exists() and settings.reference_audio_path in {DEFAULT_SHU_REFERENCE_AUDIO, LEGACY_SHU_REFERENCE_AUDIO}:
        reference_dir = settings.gpt_sovits_root / "logs" / "shu" / "5-wav32k"
        matches = sorted(reference_dir.glob("*_0000000000_0000142080.wav")) if reference_dir.exists() else []
        if matches:
            reference_audio = matches[0]
    return {
        "runtime_root": settings.gpt_sovits_root,
        "tts_module": settings.gpt_sovits_root / "GPT_SoVITS" / "TTS_infer_pack" / "TTS.py",
        "gpt_weights": resolve_gpt_sovits_path(settings, settings.gpt_sovits_gpt_weights),
        "sovits_weights": resolve_gpt_sovits_path(settings, settings.gpt_sovits_sovits_weights),
        "reference_audio": reference_audio,
        "bert_base": settings.gpt_sovits_root / "GPT_SoVITS" / "pretrained_models" / "chinese-roberta-wwm-ext-large",
        "cnhubert_base": settings.gpt_sovits_root / "GPT_SoVITS" / "pretrained_models" / "chinese-hubert-base",
    }


def get_gpt_sovits_model_id(settings: TtsSettings) -> str:
    paths = get_gpt_sovits_paths(settings)
    payload = {
        "gpt": settings.gpt_sovits_gpt_weights,
        "gpt_fingerprint": _file_fingerprint(paths["gpt_weights"]),
        "sovits": settings.gpt_sovits_sovits_weights,
        "sovits_fingerprint": _file_fingerprint(paths["sovits_weights"]),
    }
    return _sha256_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))[:24]


def _prepare_genie_import_path() -> None:
    repo_dir = _as_path(_env_text("KGTS_TTS_GENIE_REPO_DIR")) or DEFAULT_GENIE_REPO_DIR
    error = project_path_error(repo_dir, label="KGTS_TTS_GENIE_REPO_DIR")
    if error:
        raise RuntimeError(error)
    candidate_dirs = [repo_dir, repo_dir / "src"]
    for candidate_dir in candidate_dirs:
        if (candidate_dir / "genie_tts").exists():
            candidate_text = str(candidate_dir)
            if candidate_text not in sys.path:
                sys.path.insert(0, candidate_text)
            break


def _prepare_genie_runtime(settings: TtsSettings) -> None:
    os.environ.setdefault("GENIE_DATA_DIR", str(settings.genie_data_dir))
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if isinstance(stream, io.TextIOBase) and stream.encoding and stream.encoding.lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError, OSError):
                pass


def _get_missing_genie_resources(genie_data_dir: Path) -> list[str]:
    required_paths = [
        genie_data_dir / "chinese-hubert-base",
        genie_data_dir / "speaker_encoder.onnx",
        genie_data_dir / "G2P" / "ChineseG2P",
        genie_data_dir / "G2P" / "ChineseG2P" / "polyphonic.pickle",
    ]
    return [str(path) for path in required_paths if not path.exists()]


def _get_missing_genie_model_files(model_dir: Path) -> list[str]:
    required_files = [
        model_dir / "t2s_encoder_fp32.bin",
        model_dir / "t2s_encoder_fp32.onnx",
        model_dir / "t2s_first_stage_decoder_fp32.onnx",
        model_dir / "t2s_shared_fp16.bin",
        model_dir / "t2s_stage_decoder_fp32.onnx",
        model_dir / "vits_fp16.bin",
        model_dir / "vits_fp32.onnx",
    ]
    return [str(path) for path in required_files if not path.exists()]


class TtsAudioCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    @staticmethod
    def cache_dir(settings: TtsSettings) -> Path:
        return settings.output_dir / "cache"

    @staticmethod
    def tmp_dir(settings: TtsSettings) -> Path:
        return settings.output_dir / "tmp"

    @staticmethod
    def index_path(settings: TtsSettings) -> Path:
        return settings.output_dir / "cache_index.json"

    def _read_index(self, settings: TtsSettings) -> dict[str, Any]:
        path = self.index_path(settings)
        if not path.exists():
            return {"version": 1, "last_cleanup_at": None, "entries": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "last_cleanup_at": None, "entries": {}}
        if not isinstance(data, dict):
            return {"version": 1, "last_cleanup_at": None, "entries": {}}
        entries = data.get("entries")
        if not isinstance(entries, dict):
            data["entries"] = {}
        return data

    def _write_index(self, settings: TtsSettings, index: dict[str, Any]) -> None:
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_path(settings).write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, settings: TtsSettings, cache_key: str, settings_hash: str) -> Path | None:
        if not settings.cache_enabled:
            return None
        with self._lock:
            cache_path = self.cache_dir(settings) / f"{cache_key}.wav"
            if not cache_path.is_file():
                return None
            try:
                stat = cache_path.stat()
            except OSError:
                return None
            index = self._read_index(settings)
            entries = index["entries"]
            entry = entries.get(cache_key)
            if not isinstance(entry, dict) or entry.get("settings_hash") != settings_hash:
                return None
            if int(entry.get("file_size", -1)) != stat.st_size:
                return None
            entry["last_accessed_at"] = _utc_now()
            entry["hit_count"] = int(entry.get("hit_count", 0)) + 1
            self._write_index(settings, index)
            return cache_path

    def store(
        self,
        settings: TtsSettings,
        *,
        cache_key: str,
        tmp_path: Path,
        settings_hash: str,
        metadata: dict[str, Any],
    ) -> Path:
        with self._lock:
            self.cache_dir(settings).mkdir(parents=True, exist_ok=True)
            final_path = self.cache_dir(settings) / f"{cache_key}.wav"
            os.replace(tmp_path, final_path)
            stat = final_path.stat()
            index = self._read_index(settings)
            index["entries"][cache_key] = {
                "cache_key": cache_key,
                "created_at": _utc_now(),
                "last_accessed_at": _utc_now(),
                "hit_count": 0,
                "file_size": stat.st_size,
                "duration_estimate": metadata.get("duration_estimate"),
                "settings_hash": settings_hash,
                **metadata,
            }
            self._write_index(settings, index)
            return final_path

    def cleanup(self, settings: TtsSettings, *, preserve_keys: set[str] | None = None) -> dict[str, Any]:
        preserve_keys = preserve_keys or set()
        removed_files = 0
        removed_bytes = 0
        now = time.time()
        with self._lock:
            tmp_dir = self.tmp_dir(settings)
            if tmp_dir.exists():
                for tmp_path in tmp_dir.glob("*.wav"):
                    try:
                        if now - tmp_path.stat().st_mtime > 3600:
                            removed_bytes += tmp_path.stat().st_size
                            tmp_path.unlink()
                            removed_files += 1
                    except OSError:
                        pass

            cache_dir = self.cache_dir(settings)
            index = self._read_index(settings)
            entries = index["entries"]
            if not cache_dir.exists():
                index["last_cleanup_at"] = _utc_now()
                self._write_index(settings, index)
                return {"removed_files": removed_files, "removed_bytes": removed_bytes}

            def remove_key(key: str) -> None:
                nonlocal removed_files, removed_bytes
                if key in preserve_keys:
                    return
                path = cache_dir / f"{key}.wav"
                try:
                    if path.exists():
                        removed_bytes += path.stat().st_size
                        path.unlink()
                        removed_files += 1
                except OSError:
                    pass
                entries.pop(key, None)

            if settings.cache_ttl_hours:
                cutoff = now - settings.cache_ttl_hours * 3600
                for key, entry in list(entries.items()):
                    if key in preserve_keys or not isinstance(entry, dict):
                        continue
                    accessed = _parse_utc(entry.get("last_accessed_at"))
                    if accessed is not None and accessed < cutoff:
                        remove_key(key)

            existing_files = {path.stem: path for path in cache_dir.glob("*.wav") if path.is_file()}
            for key in list(entries):
                if key not in existing_files:
                    entries.pop(key, None)
            for key, path in existing_files.items():
                entries.setdefault(
                    key,
                    {
                        "cache_key": key,
                        "created_at": _utc_now(),
                        "last_accessed_at": _utc_now(),
                        "hit_count": 0,
                        "file_size": path.stat().st_size,
                        "settings_hash": "",
                    },
                )

            def current_totals() -> tuple[int, int]:
                files = [path for path in cache_dir.glob("*.wav") if path.is_file() and path.stem not in preserve_keys]
                total = 0
                for path in files:
                    try:
                        total += path.stat().st_size
                    except OSError:
                        pass
                return len(files), total

            max_bytes = settings.cache_max_mb * 1024 * 1024
            count, total_bytes = current_totals()
            if count > settings.cache_max_files or total_bytes > max_bytes:
                sortable = []
                for key, entry in entries.items():
                    if key in preserve_keys:
                        continue
                    sortable.append((_parse_utc(entry.get("last_accessed_at")) or 0, key))
                for _, key in sorted(sortable):
                    count, total_bytes = current_totals()
                    if count <= settings.cache_max_files and total_bytes <= max_bytes:
                        break
                    remove_key(key)

            index["last_cleanup_at"] = _utc_now()
            self._write_index(settings, index)
            return {"removed_files": removed_files, "removed_bytes": removed_bytes}

    def status(self, settings: TtsSettings) -> dict[str, Any]:
        with self._lock:
            cache_dir = self.cache_dir(settings)
            total_bytes = 0
            file_count = 0
            if cache_dir.exists():
                for path in cache_dir.glob("*.wav"):
                    if not path.is_file():
                        continue
                    file_count += 1
                    try:
                        total_bytes += path.stat().st_size
                    except OSError:
                        pass
            index = self._read_index(settings)
            entries = index.get("entries", {})
            hit_count = sum(int(entry.get("hit_count", 0)) for entry in entries.values() if isinstance(entry, dict))
            return {
                "cache_enabled": settings.cache_enabled,
                "cache_files": file_count,
                "cache_size_bytes": total_bytes,
                "cache_size_mb": round(total_bytes / 1024 / 1024, 3),
                "hit_count": hit_count,
                "last_cleanup_at": index.get("last_cleanup_at"),
                "cache_dir": str(cache_dir),
            }

    def clear(self, settings: TtsSettings, *, preserve_keys: set[str] | None = None) -> dict[str, Any]:
        preserve_keys = preserve_keys or set()
        removed_files = 0
        removed_bytes = 0
        with self._lock:
            cache_dir = self.cache_dir(settings)
            index = self._read_index(settings)
            if cache_dir.exists():
                for path in cache_dir.glob("*.wav"):
                    if path.stem in preserve_keys:
                        continue
                    try:
                        removed_bytes += path.stat().st_size
                        path.unlink()
                        removed_files += 1
                    except OSError:
                        pass
            index["entries"] = {
                key: value for key, value in index.get("entries", {}).items() if key in preserve_keys
            }
            index["last_cleanup_at"] = _utc_now()
            self._write_index(settings, index)
        return {"removed_files": removed_files, "removed_bytes": removed_bytes}


def _parse_utc(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def _parse_worker_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise RuntimeError(f"GPT-SoVITS worker did not return JSON. Output tail: {output[-1000:]}")


def _run_gpt_sovits_worker(
    python_executable: str,
    args: list[str],
    *,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    if not GPT_SOVITS_WORKER_SCRIPT.is_file():
        raise RuntimeError(f"GPT-SoVITS worker script is missing: {GPT_SOVITS_WORKER_SCRIPT}")
    command = [python_executable, str(GPT_SOVITS_WORKER_SCRIPT), *args]
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"Failed to start GPT-SoVITS worker Python {python_executable}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"GPT-SoVITS worker timed out after {timeout_seconds} seconds.") from exc

    combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    try:
        data = _parse_worker_json(combined_output)
    except RuntimeError as exc:
        if completed.returncode != 0:
            raise RuntimeError(
                f"GPT-SoVITS worker failed with exit code {completed.returncode}. "
                f"Output tail: {combined_output[-2000:]}"
            ) from exc
        raise
    if completed.returncode != 0 or not data.get("success", False):
        message = data.get("error") or data.get("cuda_error") or f"exit code {completed.returncode}"
        traceback_text = data.get("traceback")
        if traceback_text:
            message = f"{message}\n{traceback_text[-1800:]}"
        raise RuntimeError(f"GPT-SoVITS worker failed: {message}")
    return data


def _external_python_status(settings: TtsSettings) -> dict[str, Any] | None:
    if not settings.gpt_sovits_python:
        return None
    _raise_if_tts_paths_outside_project(settings)
    cache_key = (settings.gpt_sovits_python, settings.gpt_sovits_device)
    now = time.time()
    with _EXTERNAL_ENV_STATUS_LOCK:
        cached = _EXTERNAL_ENV_STATUS_CACHE.get(cache_key)
        if cached is not None and now - cached[0] < 30:
            return cached[1]
    try:
        status = _run_gpt_sovits_worker(
            settings.gpt_sovits_python,
            [
                "--status",
                "--runtime-root",
                str(settings.gpt_sovits_root),
                "--device",
                settings.gpt_sovits_device,
            ],
            timeout_seconds=60,
        )
    except RuntimeError as exc:
        status = {
            "success": False,
            "python_executable": settings.gpt_sovits_python,
            "missing_dependencies": [],
            "cuda_error": None,
            "error": str(exc),
        }
    with _EXTERNAL_ENV_STATUS_LOCK:
        _EXTERNAL_ENV_STATUS_CACHE[cache_key] = (now, status)
    return status


class _Inflight:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.path: Path | None = None
        self.error: BaseException | None = None


class _PersistentGptSovitsWorker:
    _MAX_IGNORED_PROTOCOL_LINES = 10000

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._python_executable: str | None = None
        self._stderr_handle: Any | None = None
        self._lock = threading.RLock()

    def _stop_locked(self) -> None:
        process = self._process
        stderr_handle = self._stderr_handle
        self._process = None
        self._python_executable = None
        self._stderr_handle = None
        if process is None:
            try:
                if stderr_handle is not None:
                    stderr_handle.close()
            except Exception:
                pass
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        finally:
            try:
                if stderr_handle is not None:
                    stderr_handle.close()
            except Exception:
                pass

    def _ensure_started_locked(self, python_executable: str) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None and self._python_executable == python_executable:
            return self._process
        self._stop_locked()
        if not GPT_SOVITS_WORKER_SCRIPT.is_file():
            raise RuntimeError(f"GPT-SoVITS worker script is missing: {GPT_SOVITS_WORKER_SCRIPT}")
        worker_log_dir = DEFAULT_TTS_AUDIO_DIR / "worker-logs"
        worker_log_dir.mkdir(parents=True, exist_ok=True)
        worker_log_path = worker_log_dir / "gpt-sovits-persistent-worker.log"
        stderr_handle = worker_log_path.open("a", encoding="utf-8")
        try:
            self._process = subprocess.Popen(
                [python_executable, str(GPT_SOVITS_WORKER_SCRIPT), "--serve"],
                cwd=str(ROOT_DIR),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_handle,
                bufsize=1,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except OSError as exc:
            stderr_handle.close()
            raise RuntimeError(f"Failed to start GPT-SoVITS persistent worker Python {python_executable}: {exc}") from exc
        self._python_executable = python_executable
        self._stderr_handle = stderr_handle
        return self._process

    def _read_response_locked(self, process: subprocess.Popen[str], request_id: str) -> dict[str, Any]:
        if process.stdout is None:
            self._stop_locked()
            raise RuntimeError("GPT-SoVITS persistent worker stdout is not available.")

        ignored_count = 0
        ignored_tail: list[str] = []
        while True:
            try:
                response_line = process.stdout.readline()
            except OSError as exc:
                self._stop_locked()
                raise RuntimeError(f"GPT-SoVITS persistent worker pipe failed: {exc}") from exc

            if not response_line:
                self._stop_locked()
                detail = "GPT-SoVITS persistent worker stopped unexpectedly."
                if ignored_tail:
                    detail += " Ignored protocol output tail: " + " | ".join(ignored_tail[-5:])
                detail += " See .runtime/tts/audio/worker-logs/gpt-sovits-persistent-worker.log"
                raise RuntimeError(detail)

            response_text = response_line.strip()
            if not response_text:
                continue

            try:
                response = json.loads(response_text)
            except json.JSONDecodeError:
                ignored_count += 1
                ignored_tail.append(response_text[-300:])
            else:
                if isinstance(response, dict) and response.get("id") == request_id:
                    return response
                ignored_count += 1
                ignored_tail.append(
                    f"id={response.get('id') if isinstance(response, dict) else None!r} "
                    f"success={response.get('success') if isinstance(response, dict) else None!r} "
                    f"line={response_text[-300:]}"
                )

            if len(ignored_tail) > 10:
                ignored_tail = ignored_tail[-10:]
            if ignored_count >= self._MAX_IGNORED_PROTOCOL_LINES:
                self._stop_locked()
                detail = "GPT-SoVITS persistent worker did not return a matching response id."
                if ignored_tail:
                    detail += " Ignored protocol output tail: " + " | ".join(ignored_tail[-5:])
                raise RuntimeError(detail)

    def synthesize(self, python_executable: str, payload: dict[str, Any]) -> None:
        with self._lock:
            process = self._ensure_started_locked(python_executable)
            if process.stdin is None or process.stdout is None:
                self._stop_locked()
                raise RuntimeError("GPT-SoVITS persistent worker pipes are not available.")
            request_id = uuid.uuid4().hex
            request = {"id": request_id, "payload": payload}
            try:
                process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                process.stdin.flush()
            except OSError as exc:
                self._stop_locked()
                raise RuntimeError(f"GPT-SoVITS persistent worker pipe failed: {exc}") from exc

            response = self._read_response_locked(process, request_id)
            if not response.get("success", False):
                message = response.get("error") or "unknown persistent worker error"
                traceback_text = response.get("traceback")
                if traceback_text:
                    message = f"{message}\n{traceback_text[-1800:]}"
                raise RuntimeError(f"GPT-SoVITS persistent worker failed: {message}")


class GptSovitsLocalService:
    def __init__(self, cache: TtsAudioCache) -> None:
        self._cache = cache
        self._model_lock = threading.RLock()
        self._inflight_lock = threading.RLock()
        self._pipeline: Any | None = None
        self._loaded_model_id: str | None = None
        self._last_error: str | None = None
        self._inflight: dict[str, _Inflight] = {}
        self._persistent_worker = _PersistentGptSovitsWorker()

    @property
    def model_loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def active_cache_keys(self) -> set[str]:
        with self._inflight_lock:
            return set(self._inflight)

    def _prepare_import_path(self, settings: TtsSettings) -> None:
        for path in (settings.gpt_sovits_root, settings.gpt_sovits_root / "GPT_SoVITS"):
            path_text = str(path)
            if path_text not in sys.path:
                sys.path.insert(0, path_text)

    def _runtime_config_path(self, settings: TtsSettings) -> Path:
        return settings.gpt_sovits_root / "GPT_SoVITS" / "configs" / "kgts_tts_infer.runtime.yaml"

    def _write_runtime_config(self, settings: TtsSettings) -> Path:
        paths = get_gpt_sovits_paths(settings)
        config_path = self._runtime_config_path(settings)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "version": "v2",
            "custom": {
                "bert_base_path": str(paths["bert_base"]),
                "cnhuhbert_base_path": str(paths["cnhubert_base"]),
                "device": settings.gpt_sovits_device,
                "is_half": settings.gpt_sovits_is_half,
                "t2s_weights_path": str(paths["gpt_weights"]),
                "version": "v2",
                "vits_weights_path": str(paths["sovits_weights"]),
            },
            "default_v2": {
                "bert_base_path": str(paths["bert_base"]),
                "cnhuhbert_base_path": str(paths["cnhubert_base"]),
                "device": settings.gpt_sovits_device,
                "is_half": settings.gpt_sovits_is_half,
                "t2s_weights_path": str(paths["gpt_weights"]),
                "version": "v2",
                "vits_weights_path": str(paths["sovits_weights"]),
            },
        }
        try:
            yaml = importlib.import_module("yaml")
            text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
        except Exception:
            text = json.dumps(config, ensure_ascii=False, indent=2)
        config_path.write_text(text, encoding="utf-8")
        return config_path

    def _ensure_pipeline(self, settings: TtsSettings) -> Any:
        model_id = get_gpt_sovits_model_id(settings)
        if self._pipeline is not None and self._loaded_model_id == model_id:
            return self._pipeline
        with self._model_lock:
            if self._pipeline is not None and self._loaded_model_id == model_id:
                return self._pipeline
            self._validate_runtime(settings, include_dependencies=False)
            self._prepare_import_path(settings)
            config_path = self._write_runtime_config(settings)
            try:
                with _pushd(settings.gpt_sovits_root):
                    module = importlib.import_module("GPT_SoVITS.TTS_infer_pack.TTS")
                    tts_config = module.TTS_Config(str(config_path))
                    self._pipeline = module.TTS(tts_config)
                    self._loaded_model_id = model_id
                    self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
                raise
            return self._pipeline

    def _validate_runtime(self, settings: TtsSettings, *, include_dependencies: bool = True) -> None:
        _raise_if_tts_paths_outside_project(settings)
        paths = get_gpt_sovits_paths(settings)
        missing = [str(path) for path in paths.values() if not path.exists()]
        if missing:
            raise RuntimeError("GPT-SoVITS runtime is incomplete: " + "; ".join(missing))
        if settings.gpt_sovits_python:
            external_status = _external_python_status(settings)
            if not external_status or not external_status.get("success", False):
                error = external_status.get("error") if external_status else "unknown worker status"
                missing_deps = external_status.get("missing_dependencies", []) if external_status else []
                cuda_error = external_status.get("cuda_error") if external_status else None
                details = []
                if missing_deps:
                    details.append("missing dependencies: " + ", ".join(missing_deps))
                if cuda_error:
                    details.append(str(cuda_error))
                if error:
                    details.append(str(error))
                raise RuntimeError("GPT-SoVITS external Python is not ready: " + "; ".join(details))
            return
        if include_dependencies:
            missing_deps = _missing_gpt_sovits_dependencies()
            if missing_deps:
                raise RuntimeError("Missing GPT-SoVITS Python dependencies: " + ", ".join(missing_deps))
        if settings.gpt_sovits_device.startswith("cuda"):
            cuda_error = _cuda_unavailable_reason()
            if cuda_error:
                raise RuntimeError(cuda_error)

    def _build_cache_identity(
        self,
        settings: TtsSettings,
        normalized: NormalizedTtsText,
        *,
        reference_audio_path: Path,
        reference_text: str,
        prompt_lang: str,
        speed_factor: float,
        top_k: int,
        top_p: float,
        temperature: float,
        repetition_penalty: float,
    ) -> tuple[str, str, dict[str, Any]]:
        reference_audio_hash = _hash_file(reference_audio_path)
        model_id = get_gpt_sovits_model_id(settings)
        identity = {
            "normalized_text": normalized.normalized_text,
            "provider": settings.provider,
            "model_id": model_id,
            "reference_audio_hash": reference_audio_hash,
            "reference_text": reference_text,
            "text_lang": normalized.text_lang,
            "prompt_lang": prompt_lang,
            "speed_factor": speed_factor,
            "top_k": top_k,
            "top_p": top_p,
            "temperature": temperature,
            "repetition_penalty": repetition_penalty,
            "formula_policy_version": normalized.formula_policy_version,
        }
        settings_identity = {key: value for key, value in identity.items() if key != "normalized_text"}
        settings_hash = _sha256_text(json.dumps(settings_identity, sort_keys=True, ensure_ascii=False))
        cache_key = _sha256_text(json.dumps(identity, sort_keys=True, ensure_ascii=False))
        return cache_key, settings_hash, identity

    def synthesize(
        self,
        *,
        text: str,
        language: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        reference_language: str | None = None,
        speed_factor: float | None = None,
        top_k: int | None = None,
        top_p: float | None = None,
        temperature: float | None = None,
        repetition_penalty: float | None = None,
        text_split_method: str | None = None,
    ) -> TtsSynthesisResult:
        settings = get_tts_settings()
        normalized = normalize_tts_text(text, settings.language, language)
        if not normalized.normalized_text:
            raise ValueError("Text is empty after cleaning.")
        if len(normalized.normalized_text) > settings.max_chars:
            raise ValueError(
                f"Text is too long for one TTS request. Limit: {settings.max_chars} normalized characters. "
                "Use /api/tts/segments and synthesize each segment."
            )

        ref_audio = (
            resolve_gpt_sovits_path(settings, reference_audio_path)
            if reference_audio_path
            else get_gpt_sovits_paths(settings)["reference_audio"]
        )
        prompt_text = (reference_text if reference_text is not None else settings.reference_text).strip()
        prompt_lang = (reference_language or settings.reference_language or settings.language).lower()
        effective_speed = settings.speed_factor if speed_factor is None else float(speed_factor)
        effective_top_k = settings.top_k if top_k is None else int(top_k)
        effective_top_p = settings.top_p if top_p is None else float(top_p)
        effective_temperature = settings.temperature if temperature is None else float(temperature)
        effective_repetition = settings.repetition_penalty if repetition_penalty is None else float(repetition_penalty)
        effective_split = text_split_method or settings.text_split_method

        cache_key, settings_hash, identity = self._build_cache_identity(
            settings,
            normalized,
            reference_audio_path=ref_audio,
            reference_text=prompt_text,
            prompt_lang=prompt_lang,
            speed_factor=effective_speed,
            top_k=effective_top_k,
            top_p=effective_top_p,
            temperature=effective_temperature,
            repetition_penalty=effective_repetition,
        )

        cached = self._cache.get(settings, cache_key, settings_hash)
        if cached is not None:
            self._cache.cleanup(settings, preserve_keys=self.active_cache_keys() | {cache_key})
            return TtsSynthesisResult(cached, True, cache_key, len(normalized.normalized_text), settings.provider, normalized.text_lang)

        with self._inflight_lock:
            inflight = self._inflight.get(cache_key)
            if inflight is None:
                inflight = _Inflight()
                self._inflight[cache_key] = inflight
                owner = True
            else:
                owner = False

        if not owner:
            inflight.event.wait()
            if inflight.error is not None:
                raise RuntimeError(str(inflight.error))
            cached = self._cache.get(settings, cache_key, settings_hash)
            if cached is None:
                raise RuntimeError("TTS generation finished without a valid cache file.")
            return TtsSynthesisResult(cached, True, cache_key, len(normalized.normalized_text), settings.provider, normalized.text_lang)

        tmp_path: Path | None = None
        try:
            self._validate_runtime(settings)
            self._cache.tmp_dir(settings).mkdir(parents=True, exist_ok=True)
            tmp_path = self._cache.tmp_dir(settings) / f"{cache_key}-{uuid.uuid4().hex}.wav"
            self._synthesize_to_file(
                settings,
                output_path=tmp_path,
                text=normalized.normalized_text,
                text_lang=normalized.text_lang,
                ref_audio=ref_audio,
                prompt_text=prompt_text,
                prompt_lang=prompt_lang,
                speed_factor=effective_speed,
                top_k=effective_top_k,
                top_p=effective_top_p,
                temperature=effective_temperature,
                repetition_penalty=effective_repetition,
                text_split_method=effective_split,
            )
            final_path = self._cache.store(
                settings,
                cache_key=cache_key,
                tmp_path=tmp_path,
                settings_hash=settings_hash,
                metadata={
                    "original_text_summary": text[:160],
                    "normalized_text_summary": normalized.normalized_text[:160],
                    "provider": settings.provider,
                    "model_id": identity["model_id"],
                    "duration_estimate": None,
                },
            )
            inflight.path = final_path
            self._last_error = None
            self._cache.cleanup(settings, preserve_keys=self.active_cache_keys() | {cache_key})
            return TtsSynthesisResult(final_path, False, cache_key, len(normalized.normalized_text), settings.provider, normalized.text_lang)
        except BaseException as exc:
            inflight.error = exc
            self._last_error = str(exc)
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        finally:
            with self._inflight_lock:
                self._inflight.pop(cache_key, None)
                inflight.event.set()

    def _synthesize_to_file(
        self,
        settings: TtsSettings,
        *,
        output_path: Path,
        text: str,
        text_lang: str,
        ref_audio: Path,
        prompt_text: str,
        prompt_lang: str,
        speed_factor: float,
        top_k: int,
        top_p: float,
        temperature: float,
        repetition_penalty: float,
        text_split_method: str,
    ) -> None:
        if settings.gpt_sovits_python:
            self._synthesize_to_file_via_worker(
                settings,
                output_path=output_path,
                text=text,
                text_lang=text_lang,
                ref_audio=ref_audio,
                prompt_text=prompt_text,
                prompt_lang=prompt_lang,
                speed_factor=speed_factor,
                top_k=top_k,
                top_p=top_p,
                temperature=temperature,
                repetition_penalty=repetition_penalty,
                text_split_method=text_split_method,
            )
            return

        pipeline = self._ensure_pipeline(settings)
        with self._model_lock:
            inputs = {
                "text": text,
                "text_lang": text_lang,
                "ref_audio_path": str(ref_audio),
                "prompt_text": prompt_text,
                "prompt_lang": prompt_lang,
                "top_k": top_k,
                "top_p": top_p,
                "temperature": temperature,
                "text_split_method": text_split_method,
                "batch_size": settings.batch_size,
                "batch_threshold": settings.batch_threshold,
                "split_bucket": settings.split_bucket,
                "return_fragment": False,
                "speed_factor": speed_factor,
                "fragment_interval": 0.3,
                "seed": -1,
                "parallel_infer": settings.parallel_infer,
                "repetition_penalty": repetition_penalty,
            }
            chunks: list[Any] = []
            sample_rate: int | None = None
            for sr, audio in pipeline.run(inputs):
                sample_rate = int(sr)
                chunks.append(audio)
            if sample_rate is None or not chunks:
                raise RuntimeError("GPT-SoVITS completed without audio data.")

            np = importlib.import_module("numpy")
            audio_data = np.concatenate([np.asarray(chunk) for chunk in chunks])
            if audio_data.dtype != np.int16:
                if audio_data.max(initial=0) <= 1.0 and audio_data.min(initial=0) >= -1.0:
                    audio_data = (audio_data * 32767).astype(np.int16)
                else:
                    audio_data = audio_data.astype(np.int16)

            with wave.open(str(output_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data.tobytes())
        if not output_path.is_file() or output_path.stat().st_size <= 44:
            raise RuntimeError("GPT-SoVITS produced an empty wav file.")

    def _synthesize_to_file_via_worker(
        self,
        settings: TtsSettings,
        *,
        output_path: Path,
        text: str,
        text_lang: str,
        ref_audio: Path,
        prompt_text: str,
        prompt_lang: str,
        speed_factor: float,
        top_k: int,
        top_p: float,
        temperature: float,
        repetition_penalty: float,
        text_split_method: str,
    ) -> None:
        with self._model_lock:
            config_path = self._write_runtime_config(settings)
            payload_path = self._cache.tmp_dir(settings) / f"gpt-sovits-worker-{uuid.uuid4().hex}.json"
            payload = {
                "runtime_root": str(settings.gpt_sovits_root),
                "config_path": str(config_path),
                "config_key": get_gpt_sovits_model_id(settings),
                "output_path": str(output_path),
                "log_path": str(payload_path.with_suffix(".log")),
                "inputs": {
                    "text": text,
                    "text_lang": text_lang,
                    "ref_audio_path": str(ref_audio),
                    "prompt_text": prompt_text,
                    "prompt_lang": prompt_lang,
                    "top_k": top_k,
                    "top_p": top_p,
                    "temperature": temperature,
                    "text_split_method": text_split_method,
                    "batch_size": settings.batch_size,
                    "batch_threshold": settings.batch_threshold,
                    "split_bucket": settings.split_bucket,
                    "return_fragment": False,
                    "speed_factor": speed_factor,
                    "fragment_interval": 0.3,
                    "seed": -1,
                    "parallel_infer": settings.parallel_infer,
                    "repetition_penalty": repetition_penalty,
                },
            }
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                self._persistent_worker.synthesize(settings.gpt_sovits_python, payload)
            finally:
                try:
                    payload_path.unlink(missing_ok=True)
                except OSError:
                    pass
        if not output_path.is_file() or output_path.stat().st_size <= 44:
            raise RuntimeError("GPT-SoVITS worker produced an empty wav file.")


def _missing_gpt_sovits_dependencies() -> list[str]:
    return [name for name in GPT_SOVITS_DEPENDENCY_MODULES if importlib.util.find_spec(name) is None]


def _cuda_unavailable_reason() -> str | None:
    if importlib.util.find_spec("torch") is None:
        return "CUDA requested, but torch is not installed."
    try:
        torch = importlib.import_module("torch")
        if not torch.cuda.is_available():
            return "CUDA requested by KGTS_TTS_GPT_SOVITS_DEVICE, but torch.cuda.is_available() is false."
    except Exception as exc:
        return f"CUDA availability check failed: {exc}"
    return None


def get_gpt_sovits_runtime_status(settings: TtsSettings) -> dict[str, Any]:
    path_violations = _tts_path_policy_violations(settings)
    paths = get_gpt_sovits_paths(settings)
    missing_paths = [str(path) for path in paths.values() if not path.exists()]
    runtime_mode = "subprocess" if settings.gpt_sovits_python else "in_process"
    external_status = None if path_violations else (_external_python_status(settings) if settings.gpt_sovits_python else None)
    if external_status is not None:
        missing_dependencies = list(external_status.get("missing_dependencies") or [])
        cuda_error = external_status.get("cuda_error")
        external_error = external_status.get("error")
    else:
        missing_dependencies = _missing_gpt_sovits_dependencies()
        cuda_error = _cuda_unavailable_reason() if settings.gpt_sovits_device.startswith("cuda") and not missing_dependencies else None
        external_error = None
    cache_status = tts_audio_cache.status(settings)
    last_error = gpt_sovits_local_service.last_error or cuda_error or external_error
    available = not path_violations and not missing_paths and not missing_dependencies and not cuda_error and not external_error
    runtime_assets_ready = not missing_paths
    if path_violations:
        detail = "GPT-SoVITS path is outside project root while KGTS_PROJECT_LOCAL_ONLY=1."
    elif available:
        if settings.gpt_sovits_python:
            detail = "GPT-SoVITS local runtime assets are ready; synthesis will run through the configured external Python."
        else:
            detail = "GPT-SoVITS local runtime is ready."
    elif missing_paths:
        detail = "GPT-SoVITS local runtime assets are incomplete; run scripts/migrate_shu_gpt_sovits_runtime.ps1."
    elif missing_dependencies and settings.gpt_sovits_python:
        detail = "Configured GPT-SoVITS external Python is missing dependencies: " + ", ".join(missing_dependencies)
    elif missing_dependencies:
        detail = (
            "GPT-SoVITS local runtime assets are present, but the active Python environment is missing "
            "GPT-SoVITS dependencies. Install requirements-gpt-sovits-tts.txt into a Python 3.10-compatible "
            "local environment and run KGTS from that environment."
        )
    elif external_error:
        detail = "Configured GPT-SoVITS external Python is not ready: " + str(external_error)
    elif cuda_error:
        detail = cuda_error
    else:
        detail = "GPT-SoVITS local runtime is not ready."
    return {
        "provider": settings.provider,
        "available": available,
        "model_loaded": gpt_sovits_local_service.model_loaded,
        "runtime_root": str(settings.gpt_sovits_root),
        "model_id": get_gpt_sovits_model_id(settings),
        "cache_enabled": settings.cache_enabled,
        "cache_files": cache_status["cache_files"],
        "cache_size_mb": cache_status["cache_size_mb"],
        "last_error": last_error,
        "path_policy": "project_local" if project_local_only() else "external_paths_allowed",
        "outside_project_paths": path_violations,
        "missing_paths": missing_paths,
        "missing_dependencies": missing_dependencies,
        "runtime_mode": runtime_mode,
        "runtime_assets_ready": runtime_assets_ready,
        "external_python_executable": settings.gpt_sovits_python or None,
        "external_python_version": external_status.get("python_version") if external_status else None,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "reference_audio_path": str(paths["reference_audio"]),
        "reference_language": settings.reference_language,
        "detail": detail,
    }


def get_tts_status() -> dict[str, Any]:
    settings = get_tts_settings()
    path_violations = _tts_path_policy_violations(settings)
    status: dict[str, Any] = {
        "success": True,
        "enabled": settings.enabled,
        "provider": settings.provider,
        "available": False,
        "character_name": settings.predefined_character or settings.character_name,
        "output_dir": str(settings.output_dir),
        "max_chars": settings.max_chars,
        "path_policy": "project_local" if project_local_only() else "external_paths_allowed",
        "outside_project_paths": path_violations,
    }
    if not settings.enabled or settings.provider == "disabled":
        status["detail"] = "TTS is disabled. Set KGTS_TTS_ENABLED=1 and KGTS_TTS_PROVIDER=genie for local Genie-TTS inference."
        return status
    if settings.provider == "gpt_sovits_local":
        status.update(get_gpt_sovits_runtime_status(settings))
        return status
    if settings.provider == "genie_server":
        status["available"] = bool(settings.server_url)
        status["server_url"] = settings.server_url
        status["detail"] = "Using external Genie-TTS server proxy."
        return status
    if settings.provider == "gpt_sovits_server":
        status["available"] = bool(settings.server_url)
        status["server_url"] = settings.server_url
        status["reference_audio_path"] = settings.reference_audio_path
        status["reference_language"] = settings.reference_language
        status["detail"] = "Using external GPT-SoVITS server proxy."
        return status
    if settings.provider != "genie":
        status["detail"] = f"Unsupported TTS provider: {settings.provider}"
        return status

    if path_violations:
        status["detail"] = "TTS path is outside project root while KGTS_PROJECT_LOCAL_ONLY=1."
        status["last_error"] = "; ".join(f"{item['label']}={item['path']}" for item in path_violations)
        return status

    try:
        _prepare_genie_import_path()
        has_genie = importlib.util.find_spec("genie_tts") is not None
    except RuntimeError as exc:
        has_genie = False
        status["last_error"] = str(exc)
    status["genie_data_dir"] = str(settings.genie_data_dir)
    status["model_dir"] = settings.model_dir
    status["reference_audio_path"] = settings.reference_audio_path
    missing_resources = _get_missing_genie_resources(settings.genie_data_dir)
    missing_model_files = _get_missing_genie_model_files(_as_path(settings.model_dir) or Path(settings.model_dir))
    reference_audio = _as_path(settings.reference_audio_path) or Path(settings.reference_audio_path)
    missing_reference_audio = [] if reference_audio.exists() else [str(reference_audio)]
    status["available"] = has_genie and not missing_resources and not missing_model_files and not missing_reference_audio
    if not has_genie:
        status["detail"] = "Genie-TTS is not installed. Install local-only dependencies from requirements-tts.txt."
    elif missing_resources:
        status["missing_resources"] = missing_resources
        status["detail"] = "Genie-TTS package is installed, but required GenieData resources are missing."
    elif missing_model_files:
        status["missing_model_files"] = missing_model_files
        status["detail"] = "Genie-TTS is installed, but the shu ONNX model directory is incomplete."
    elif missing_reference_audio:
        status["missing_reference_audio"] = missing_reference_audio
        status["detail"] = "Genie-TTS is installed, but the shu reference audio is missing."
    else:
        status["detail"] = "Genie-TTS local runtime and shu model are available."
    return status


class GenieTtsService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._genie: Any | None = None
        self._loaded_characters: set[str] = set()
        self._reference_cache_keys: set[tuple[str, str, str]] = set()

    def _import_genie(self, settings: TtsSettings) -> Any:
        if self._genie is not None:
            return self._genie

        _raise_if_tts_paths_outside_project(settings)
        settings.genie_data_dir.mkdir(parents=True, exist_ok=True)
        _prepare_genie_runtime(settings)
        _prepare_genie_import_path()
        self._genie = importlib.import_module("genie_tts")
        return self._genie

    def load_character(
        self,
        *,
        character_name: str | None = None,
        predefined_character: str | None = None,
        model_dir: str | None = None,
        language: str | None = None,
    ) -> str:
        settings = get_tts_settings()
        name = (character_name or settings.character_name or predefined_character or settings.predefined_character).strip()
        predefined = (predefined_character or settings.predefined_character).strip()
        model_path = (model_dir or settings.model_dir).strip()
        lang = (language or settings.language).strip()

        with self._lock:
            genie = self._import_genie(settings)
            if predefined:
                genie.load_predefined_character(predefined)
                loaded_name = predefined
            else:
                if not name:
                    raise RuntimeError("KGTS_TTS_CHARACTER_NAME is required when no predefined character is configured.")
                if not model_path:
                    raise RuntimeError("KGTS_TTS_MODEL_DIR is required when no predefined character is configured.")
                if not lang:
                    raise RuntimeError("KGTS_TTS_LANGUAGE is required when no predefined character is configured.")
                genie.load_character(
                    character_name=name,
                    onnx_model_dir=str(_as_path(model_path) or model_path),
                    language=lang,
                )
                loaded_name = name
            self._loaded_characters.add(loaded_name)
            return loaded_name

    def set_reference_audio(
        self,
        *,
        character_name: str | None = None,
        audio_path: str | None = None,
        audio_text: str | None = None,
        language: str | None = None,
    ) -> None:
        settings = get_tts_settings()
        name = (character_name or settings.character_name or settings.predefined_character).strip()
        ref_path = (audio_path or settings.reference_audio_path).strip()
        ref_text = (audio_text or settings.reference_text).strip()
        ref_language = (language or settings.reference_language).strip()
        if not name:
            raise RuntimeError("character_name is required before setting reference audio.")
        if not ref_path:
            raise RuntimeError("audio_path is required before setting reference audio.")

        resolved_ref = str(_as_path(ref_path) or ref_path)
        cache_key = (name, resolved_ref, ref_text)
        with self._lock:
            if cache_key in self._reference_cache_keys:
                return
            genie = self._import_genie(settings)
            try:
                genie.set_reference_audio(
                    character_name=name,
                    audio_path=resolved_ref,
                    audio_text=ref_text,
                    language=ref_language,
                )
            except TypeError:
                genie.set_reference_audio(
                    character_name=name,
                    audio_path=resolved_ref,
                    audio_text=ref_text,
                )
            self._reference_cache_keys.add(cache_key)

    def _ensure_ready(
        self,
        *,
        character_name: str | None = None,
        model_dir: str | None = None,
        language: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        reference_language: str | None = None,
    ) -> str:
        settings = get_tts_settings()
        name = (character_name or settings.character_name or settings.predefined_character).strip()
        if not name or name not in self._loaded_characters:
            name = self.load_character(
                character_name=character_name,
                model_dir=model_dir,
                language=language,
            )

        if reference_audio_path or settings.reference_audio_path:
            self.set_reference_audio(
                character_name=name,
                audio_path=reference_audio_path,
                audio_text=reference_text or settings.reference_text,
                language=reference_language or settings.reference_language,
            )
        return name

    def synthesize(
        self,
        *,
        text: str,
        character_name: str | None = None,
        split_sentence: bool = True,
        model_dir: str | None = None,
        language: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        reference_language: str | None = None,
    ) -> Path:
        settings = get_tts_settings()
        if len(text) > settings.max_chars:
            raise ValueError(f"Text is too long for one TTS request. Limit: {settings.max_chars} characters.")

        settings.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = settings.output_dir / f"tts-{uuid.uuid4().hex}.wav"
        with self._lock:
            character = self._ensure_ready(
                character_name=character_name,
                model_dir=model_dir,
                language=language,
                reference_audio_path=reference_audio_path,
                reference_text=reference_text,
                reference_language=reference_language,
            )
            genie = self._import_genie(settings)
            kwargs = {
                "character_name": character,
                "text": text,
                "play": False,
                "save_path": str(output_path),
                "split_sentence": split_sentence,
            }
            try:
                result = genie.tts(**kwargs)
            except TypeError:
                kwargs.pop("split_sentence", None)
                result = genie.tts(**kwargs)

            if not output_path.exists():
                if isinstance(result, (str, Path)) and Path(result).exists():
                    output_path = Path(result)
                elif isinstance(result, bytes):
                    output_path.write_bytes(result)
                else:
                    raise RuntimeError("Genie-TTS completed without producing an audio file.")

        self.cleanup_audio_dir(settings.output_dir, settings.max_audio_files)
        return output_path

    def unload_character(self, character_name: str) -> bool:
        settings = get_tts_settings()
        with self._lock:
            genie = self._import_genie(settings)
            unload = getattr(genie, "unload_character", None)
            if not callable(unload):
                return False
            unload(character_name=character_name)
            self._loaded_characters.discard(character_name)
            return True

    def stop(self) -> bool:
        settings = get_tts_settings()
        with self._lock:
            genie = self._import_genie(settings)
            for name in ("stop", "stop_all", "stop_all_tts_tasks", "stop_all_tasks"):
                fn = getattr(genie, name, None)
                if callable(fn):
                    fn()
                    return True
            return False

    def clear_reference_audio_cache(self) -> bool:
        settings = get_tts_settings()
        with self._lock:
            genie = self._import_genie(settings)
            fn = getattr(genie, "clear_reference_audio_cache", None)
            if callable(fn):
                fn()
            self._reference_cache_keys.clear()
            return callable(fn)

    @staticmethod
    def cleanup_audio_dir(output_dir: Path, max_files: int) -> None:
        try:
            files = sorted(
                [path for path in output_dir.glob("*.wav") if path.is_file()],
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for old_file in files[max_files:]:
            try:
                old_file.unlink()
            except OSError:
                pass


def run_tts_startup_cleanup() -> dict[str, Any]:
    settings = get_tts_settings()
    return tts_audio_cache.cleanup(settings, preserve_keys=gpt_sovits_local_service.active_cache_keys())


def is_tts_cache_admin_enabled() -> bool:
    explicit = os.getenv("KGTS_TTS_CACHE_ADMIN_ENABLED")
    if explicit is not None and explicit.strip() != "":
        return _env_flag("KGTS_TTS_CACHE_ADMIN_ENABLED", False)
    cloud_markers = (
        "WEBSITE_SITE_NAME",
        "WEBSITE_INSTANCE_ID",
        "APPSETTING_WEBSITE_SITE_NAME",
        "RENDER",
        "RENDER_SERVICE_ID",
    )
    app_env = _env_text("APP_ENV").lower()
    return app_env not in {"prod", "production"} and not any(os.getenv(name) for name in cloud_markers)


tts_audio_cache = TtsAudioCache()
genie_tts_service = GenieTtsService()
gpt_sovits_local_service = GptSovitsLocalService(tts_audio_cache)
