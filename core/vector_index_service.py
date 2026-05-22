#!/usr/bin/env python3
"""Optional FAISS vector index for graph nodes.

The graph SQLite database remains the source of truth. This module stores only
derived embeddings and metadata that can be rebuilt from the graph at any time.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


class VectorIndexUnavailable(RuntimeError):
    """Raised when optional vector search dependencies or index files fail."""


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_index_dir() -> Path:
    configured = os.getenv("KGTS_VECTOR_INDEX_DIR")
    if configured:
        return Path(configured)
    return _project_root() / ".runtime" / "vector_index"


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


class GraphVectorIndex:
    """Small FAISS index wrapper for graph node retrieval."""

    def __init__(self, index_dir: str | Path | None = None, model_name: Optional[str] = None):
        self.index_dir = Path(index_dir) if index_dir else _default_index_dir()
        self.model_name = model_name or os.getenv(
            "KGTS_EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
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

    def _ensure_dependencies(self) -> None:
        if self._faiss is not None and self._np is not None and self._model is not None:
            return
        faiss, np, SentenceTransformer = _load_vector_dependencies()
        self._faiss = faiss
        self._np = np
        self._model = SentenceTransformer(self.model_name)

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
            if self._index is not None and not self._is_stale(node_list):
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
        self.last_error = None
        return self.get_stats()

    def reset(self) -> Dict[str, Any]:
        if self.index_dir.exists():
            shutil.rmtree(self.index_dir)
        self._index = None
        self._entries = []
        self._dimension = 0
        self.last_error = None
        return self.get_stats()

    def search(self, query: str, top_k: int = 10, node_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if not query.strip():
            return []
        if self._index is None:
            if not self._load_index():
                return []
        if self._index is None or int(getattr(self._index, "ntotal", 0) or 0) == 0:
            return []

        limit = min(max(top_k, 1), int(getattr(self._index, "ntotal", 0) or 0))
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
        return {
            "enabled": True,
            "mode": "hybrid",
            "index_size": index_size,
            "embedding_dimension": self._dimension,
            "model": self.model_name,
            "index_path": str(self.index_dir),
            "metadata_format": self._metadata_format,
            "metric_type": self._metric_type,
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
