#!/usr/bin/env python3
"""Optional FAISS vector index for graph nodes.

The graph SQLite database remains the source of truth. This module stores only
derived embeddings and metadata that can be rebuilt from the graph at any time.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .path_policy import PROJECT_ROOT, env_flag, outside_project_paths, project_local_only, project_path_error, resolve_project_path


class VectorIndexUnavailable(RuntimeError):
    """Raised when optional vector search dependencies or index files fail."""


def _project_root() -> Path:
    return PROJECT_ROOT


def _default_index_dir() -> Path:
    configured = os.getenv("KGTS_VECTOR_INDEX_DIR")
    if configured:
        path = resolve_project_path(configured)
        if path is None:
            raise VectorIndexUnavailable("KGTS_VECTOR_INDEX_DIR is empty")
        error = project_path_error(path, label="KGTS_VECTOR_INDEX_DIR")
        if error:
            raise VectorIndexUnavailable(error)
        return path
    return _project_root() / ".runtime" / "vector_index"


def _resolve_index_dir(index_dir: str | Path | None = None) -> Path:
    if index_dir is not None:
        path = resolve_project_path(index_dir)
        if path is None:
            raise VectorIndexUnavailable("KGTS_VECTOR_INDEX_DIR is empty")
        error = project_path_error(path, label="KGTS_VECTOR_INDEX_DIR")
        if error:
            raise VectorIndexUnavailable(error)
        return path
    return _default_index_dir()


def _default_embedding_cache_dir() -> Path:
    configured = os.getenv("KGTS_EMBEDDING_CACHE_DIR")
    path = resolve_project_path(configured, default=_project_root() / ".runtime" / "huggingface")
    if path is None:
        raise VectorIndexUnavailable("KGTS_EMBEDDING_CACHE_DIR is empty")
    error = project_path_error(path, label="KGTS_EMBEDDING_CACHE_DIR")
    if error:
        raise VectorIndexUnavailable(error)
    return path


def _looks_like_local_model_path(model_name: str) -> bool:
    value = model_name.strip()
    if not value:
        return False
    path = Path(value)
    if path.is_absolute():
        return True
    return value.startswith((".", "models/", "models\\", ".runtime/", ".runtime\\", "backend/", "backend\\"))


def _model_path_policy_error(model_name: str) -> str | None:
    if not _looks_like_local_model_path(model_name):
        return None
    resolved = resolve_project_path(model_name)
    if resolved is None:
        return "KGTS_EMBEDDING_MODEL is empty"
    return project_path_error(resolved, label="KGTS_EMBEDDING_MODEL")


def vector_path_policy_violations(
    *,
    index_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    effective_model = model_name or os.getenv(
        "KGTS_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    effective_index_dir = (
        index_dir
        if index_dir is not None
        else os.getenv("KGTS_VECTOR_INDEX_DIR") or (_project_root() / ".runtime" / "vector_index")
    )
    effective_cache_dir = (
        cache_dir
        if cache_dir is not None
        else os.getenv("KGTS_EMBEDDING_CACHE_DIR") or (_project_root() / ".runtime" / "huggingface")
    )
    return outside_project_paths(
        [
            ("KGTS_VECTOR_INDEX_DIR", effective_index_dir),
            ("KGTS_EMBEDDING_CACHE_DIR", effective_cache_dir),
            ("KGTS_EMBEDDING_MODEL", effective_model if _looks_like_local_model_path(effective_model) else None),
        ]
    )


def _node_text(node: Dict[str, Any]) -> str:
    metadata = node.get("metadata") or {}
    label = str(node.get("label") or metadata.get("label") or "")
    content = str(node.get("content") or metadata.get("description") or "")
    node_type = str(node.get("type") or metadata.get("type") or "")
    return "\n".join(part for part in (label, node_type, content) if part).strip()


def _legacy_node_text(node: Dict[str, Any]) -> str:
    metadata = node.get("metadata") or {}
    label = str(node.get("label") or metadata.get("label") or "")
    content = str(node.get("content") or metadata.get("description") or "")
    return f"{label}: {content}" if content else label


def _content_hash(text: str, updated_at: Any) -> str:
    payload = f"{updated_at}\n{text}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def _load_vector_dependencies() -> Tuple[Any, Any, Any]:
    try:
        import faiss  # type: ignore
        import numpy as np  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:  # pragma: no cover - exact dependency varies by env
        raise VectorIndexUnavailable(f"vector dependencies unavailable: {exc}") from exc
    return faiss, np, SentenceTransformer


def _load_faiss() -> Any:
    try:
        import faiss  # type: ignore
    except Exception as exc:  # pragma: no cover - exact dependency varies by env
        raise VectorIndexUnavailable(f"faiss unavailable: {exc}") from exc
    return faiss


class _HashingEmbeddingModel:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def encode(self, texts: List[str], convert_to_numpy: bool = True, show_progress_bar: bool = False) -> Any:
        import numpy as np  # type: ignore

        vectors = np.zeros((len(texts), self.dimension), dtype="float32")
        for row, text in enumerate(texts):
            tokens = re.findall(r"[\w]+", str(text or "").lower(), flags=re.UNICODE)
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8", errors="replace")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vectors[row, index] += sign
            if not tokens and text:
                digest = hashlib.sha256(str(text).encode("utf-8", errors="replace")).digest()
                vectors[row, int.from_bytes(digest[:4], "big") % self.dimension] = 1.0
        return vectors


class GraphVectorIndex:
    """Small FAISS index wrapper for graph node retrieval."""

    def __init__(self, index_dir: str | Path | None = None, model_name: Optional[str] = None):
        self.index_dir = _resolve_index_dir(index_dir)
        self.model_name = model_name or os.getenv(
            "KGTS_EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        self.cache_dir = _default_embedding_cache_dir()
        self.index_file = self.index_dir / "vector_index.faiss"
        self.metadata_file = self.index_dir / "metadata.json"
        self.last_error: Optional[str] = None

        self._faiss: Any = None
        self._np: Any = None
        self._model: Any = None
        self._index: Any = None
        self._dimension: int = 0
        self._entries: List[Dict[str, Any]] = []
        self._metadata_format = "kgts-vector-v1"
        self._metric_type: Optional[int] = None
        self._force_rebuild = False
        self._provider = "sentence-transformers"

    def _ensure_dependencies(self) -> None:
        if self._faiss is not None and self._np is not None and self._model is not None:
            return
        faiss, np, SentenceTransformer = _load_vector_dependencies()
        self._faiss = faiss
        self._np = np
        model_error = _model_path_policy_error(self.model_name)
        if model_error:
            raise VectorIndexUnavailable(model_error)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for env_name in ("HF_HOME", "HF_HUB_CACHE", "SENTENCE_TRANSFORMERS_HOME", "TRANSFORMERS_CACHE"):
            os.environ.setdefault(env_name, str(self.cache_dir))
        kwargs = {}
        if os.getenv("KGTS_EMBEDDING_LOCAL_FILES_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}:
            kwargs["local_files_only"] = True
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        try:
            self._model = SentenceTransformer(self.model_name, **kwargs)
        except TypeError:
            try:
                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:
                self._use_hashing_fallback(exc)
        except Exception as exc:
            self._use_hashing_fallback(exc)

    def _use_hashing_fallback(self, exc: Exception) -> None:
        if not env_flag("KGTS_VECTOR_HASH_FALLBACK", True):
            raise exc
        self._model = _HashingEmbeddingModel()
        self._provider = "hashing-fallback"
        self.last_error = f"using hashing fallback after embedding model load failed: {exc}"

    def _encode(self, texts: List[str]) -> Any:
        self._ensure_dependencies()
        if not texts:
            return self._np.empty((0, self._dimension or 1), dtype="float32")
        embeddings = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        embeddings = self._np.asarray(embeddings, dtype="float32")
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)
        norms = self._np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return embeddings / norms

    def _load_metadata(self) -> List[Dict[str, Any]]:
        if not self.metadata_file.exists():
            return []
        with self.metadata_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload.get("id_to_text"), dict):
            self._metadata_format = "legacy-vector-retrieval"
            entries: List[Dict[str, Any]] = []
            for raw_index, item in sorted(payload["id_to_text"].items(), key=lambda pair: int(pair[0])):
                item = item if isinstance(item, dict) else {}
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                entries.append(
                    {
                        "node_id": str(metadata.get("node_id") or metadata.get("id") or ""),
                        "label": metadata.get("label"),
                        "type": metadata.get("type") or "concept",
                        "content": item.get("text") or metadata.get("content") or "",
                        "legacy_text": item.get("text") or "",
                        "content_hash": "",
                        "updated_at": metadata.get("updated_at"),
                        "legacy_index": int(raw_index),
                    }
                )
            return entries
        if str(payload.get("model_name") or "") != self.model_name:
            raise VectorIndexUnavailable("vector index model mismatch")
        self._metadata_format = str(payload.get("format") or "kgts-vector-v1")
        self._metric_type = payload.get("metric_type")
        entries = payload.get("entries")
        return entries if isinstance(entries, list) else []

    def _save_metadata(self) -> None:
        payload = {
            "model_name": self.model_name,
            "dimension": self._dimension,
            "format": "kgts-vector-v1",
            "metric_type": self._metric_type,
            "updated_at": time.time(),
            "entries": self._entries,
        }
        with self.metadata_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _load_index(self) -> bool:
        self._ensure_dependencies()
        if not self.index_file.exists() or not self.metadata_file.exists():
            return False
        self._entries = self._load_metadata()
        self._index = self._faiss.read_index(str(self.index_file))
        self._dimension = int(getattr(self._index, "d", 0) or 0)
        self._metric_type = int(getattr(self._index, "metric_type", self._metric_type or 0) or 0)
        if int(getattr(self._index, "ntotal", 0) or 0) != len(self._entries):
            raise VectorIndexUnavailable("vector index metadata count mismatch")
        return True

    def ensure_index(self, nodes: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """Load an existing index or rebuild when it is missing/stale."""
        node_list = list(nodes)
        try:
            if self._index is None:
                try:
                    self._load_index()
                except VectorIndexUnavailable:
                    self._index = None
                    self._entries = []
            if self._index is not None and not self._force_rebuild and not self._is_stale(node_list):
                self.last_error = None
                return self.get_stats()
            return self.rebuild(node_list)
        except Exception as exc:
            self.last_error = str(exc)
            raise VectorIndexUnavailable(str(exc)) from exc

    def _is_stale(self, nodes: List[Dict[str, Any]]) -> bool:
        if self._index is None:
            return True
        valid_nodes = [node for node in nodes if str(node.get("id") or "")]
        if len(valid_nodes) != len(self._entries):
            return True
        hashes_by_id = {
            str(entry.get("node_id")): str(entry.get("content_hash") or "")
            for entry in self._entries
        }
        entries_by_id = {
            str(entry.get("node_id")): entry
            for entry in self._entries
        }
        if set(entries_by_id) != {str(node.get("id") or "") for node in valid_nodes}:
            return True
        if self._metadata_format == "legacy-vector-retrieval":
            return False
        for node in valid_nodes:
            node_id = str(node.get("id") or "")
            text = _node_text(node)
            expected = _content_hash(text, node.get("updated_at"))
            entry = entries_by_id.get(node_id) or {}
            if not entry.get("content_hash"):
                if str(entry.get("legacy_text") or "") != _legacy_node_text(node):
                    return True
                if str(entry.get("type") or "") != str(node.get("type") or "concept"):
                    return True
                continue
            if hashes_by_id.get(node_id) != expected:
                return True
        return False

    def rebuild(self, nodes: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        self._ensure_dependencies()
        self.index_dir.mkdir(parents=True, exist_ok=True)
        node_list = [node for node in nodes if str(node.get("id") or "")]
        texts = [_node_text(node) for node in node_list]
        embeddings = self._encode(texts)
        self._dimension = int(embeddings.shape[1]) if len(texts) else 0
        if self._dimension:
            index = self._faiss.IndexFlatIP(self._dimension)
            index.add(embeddings)
            self._metric_type = int(getattr(index, "metric_type", 0) or 0)
        else:
            index = None
            self._metric_type = None

        self._entries = []
        for node, text in zip(node_list, texts):
            metadata = node.get("metadata") or {}
            self._entries.append(
                {
                    "node_id": str(node.get("id") or ""),
                    "label": node.get("label") or metadata.get("label"),
                    "type": node.get("type") or metadata.get("type") or "concept",
                    "content": node.get("content") or metadata.get("description") or "",
                    "content_hash": _content_hash(text, node.get("updated_at")),
                    "updated_at": node.get("updated_at"),
                }
            )

        if index is not None:
            self._faiss.write_index(index, str(self.index_file))
        elif self.index_file.exists():
            self.index_file.unlink()
        self._index = index
        self._save_metadata()
        self._force_rebuild = False
        self.last_error = None
        return self.get_stats()

    def mark_stale(self) -> None:
        self._force_rebuild = True

    def reset(self) -> Dict[str, Any]:
        if self.index_dir.exists():
            shutil.rmtree(self.index_dir)
        self._index = None
        self._entries = []
        self._dimension = 0
        self._force_rebuild = False
        self.last_error = None
        return self.get_stats()

    def search(
        self,
        query: str,
        top_k: int = 10,
        node_type: Optional[str] = None,
        allowed_node_ids: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        if self._index is None:
            if not self._load_index():
                return []
        if self._index is None or int(getattr(self._index, "ntotal", 0) or 0) == 0:
            return []

        allowed_ids = {str(value or "").strip() for value in (allowed_node_ids or [])}
        allowed_ids.discard("")
        ntotal = int(getattr(self._index, "ntotal", 0) or 0)
        limit = ntotal if allowed_ids else min(max(top_k, 1), ntotal)
        query_embedding = self._encode([query])
        similarities, indices = self._index.search(query_embedding, limit)
        results: List[Dict[str, Any]] = []
        for raw_idx, raw_score in zip(indices[0], similarities[0]):
            idx = int(raw_idx)
            if idx < 0 or idx >= len(self._entries):
                continue
            entry = self._entries[idx]
            if node_type and entry.get("type") != node_type:
                continue
            if allowed_ids and str(entry.get("node_id") or "") not in allowed_ids:
                continue
            score = self._score(raw_score)
            results.append(
                {
                    "node_id": entry.get("node_id"),
                    "vector_score": score,
                    "similarity": score,
                    "metadata": {
                        "label": entry.get("label"),
                        "type": entry.get("type"),
                        "content": entry.get("content"),
                    },
                }
            )
            if len(results) >= top_k:
                break
        return results

    def _score(self, raw_score: Any) -> float:
        value = float(raw_score)
        if self._faiss is not None and self._metric_type == getattr(self._faiss, "METRIC_L2", 1):
            return 1.0 / (1.0 + max(value, 0.0))
        return value

    def get_stats(self) -> Dict[str, Any]:
        if self._index is None and self.index_file.exists() and self.metadata_file.exists():
            self._probe_existing_index()
        index_size = int(getattr(self._index, "ntotal", 0) or 0) if self._index is not None else len(self._entries)
        outside_paths = vector_path_policy_violations(
            index_dir=self.index_dir,
            cache_dir=self.cache_dir,
            model_name=self.model_name,
        )
        local_model_path = resolve_project_path(self.model_name) if _looks_like_local_model_path(self.model_name) else None
        return {
            "enabled": True,
            "mode": "hybrid",
            "index_size": index_size,
            "embedding_dimension": self._dimension,
            "model": self.model_name,
            "provider": self._provider,
            "index_path": str(self.index_dir),
            "embedding_cache_path": str(self.cache_dir),
            "local_model_path": str(local_model_path) if local_model_path else None,
            "local_model_exists": bool(local_model_path and local_model_path.exists()),
            "path_policy": "project_local" if project_local_only() else "external_paths_allowed",
            "outside_project_paths": outside_paths,
            "metadata_format": self._metadata_format,
            "metric_type": self._metric_type,
            "stale": self._force_rebuild,
            "last_error": self.last_error,
        }

    def _probe_existing_index(self) -> None:
        try:
            original_faiss = self._faiss
            self._faiss = self._faiss or _load_faiss()
            self._entries = self._load_metadata()
            index = self._faiss.read_index(str(self.index_file))
            self._dimension = int(getattr(index, "d", 0) or 0)
            self._metric_type = int(getattr(index, "metric_type", self._metric_type or 0) or 0)
            self._index = index
            self.last_error = None
            if original_faiss is None:
                self._faiss = original_faiss
        except Exception as exc:
            self.last_error = str(exc)
