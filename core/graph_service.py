#!/usr/bin/env python3
"""Compatibility graph service backed by vector_index_system knowledge graph DB."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import uuid
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from time import time
from typing import Any, Dict, Iterable, List, Optional, Set

from KGTS.core.vector_index_service import GraphVectorIndex, VectorIndexUnavailable, vector_path_policy_violations
from KGTS.core.path_policy import project_local_only

_LAST_VECTOR_ERROR: Optional[str] = None


def _default_db_path() -> Path:
    explicit = os.getenv("GRAPH_DB_PATH") or os.getenv("KNOWLEDGE_GRAPH_DB_PATH")
    if explicit:
        return Path(explicit)

    data_dir = os.getenv("APP_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "knowledge_graph.db"

    # Try to find the project root by looking for data/seed directory
    current = Path(__file__).resolve().parent
    for _ in range(5):
        seed_dir = current / "data" / "seed"
        if seed_dir.exists():
            return current / "backend" / "vector_index_system" / "knowledge_graph" / "knowledge_graph.db"
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback to legacy path for backward compatibility
    return Path(__file__).resolve().parent.parent.parent / "backend" / "vector_index_system" / "knowledge_graph" / "knowledge_graph.db"


DEFAULT_DB_PATH = _default_db_path()

PRESET_RELATION_TYPES = {
    "contains",
    "precedes",
    "references_formula",
    "references_table",
    "references_figure",
    "references_example",
    "references",
    "defines",
    "explains",
    "derives",
    "depends_on",
    "supports",
    "contrasts_with",
    "example_of",
    "applies_to",
    "equivalent_to",
    "causes",
    "related",
}

RELATION_TYPE_ALIASES = {
    "belongsto": "contains",
    "belongs_to": "contains",
    "part_of": "contains",
    "has_part": "contains",
    "before": "precedes",
    "after": "precedes",
    "next": "precedes",
    "reference": "references",
    "references": "references",
    "explains": "explains",
    "explained_by": "explains",
    "supports": "supports",
    "applies": "applies_to",
    "applied_to": "applies_to",
    "equivalent": "equivalent_to",
    "same_as": "equivalent_to",
    "semantic_weak": "related",
    "based_on": "depends_on",
    "requires": "depends_on",
    "prerequisite": "depends_on",
    "uses": "depends_on",
    "is_example_of": "example_of",
}


def _normalize_type(node_type: Optional[str]) -> str:
    return (node_type or "concept").strip() or "concept"


def _slug_relation_type(value: Optional[str]) -> str:
    text = re.sub(r"[^0-9a-zA-Z]+", "_", str(value or "").strip().lower())
    return re.sub(r"_+", "_", text).strip("_")


def normalize_relation_type(
    relation_type: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
    source_node: Optional[Dict[str, Any]] = None,
    target_node: Optional[Dict[str, Any]] = None,
) -> str:
    metadata = metadata or {}
    raw = _slug_relation_type(relation_type)
    if raw in RELATION_TYPE_ALIASES:
        raw = RELATION_TYPE_ALIASES[raw]

    description = " ".join(
        str(part or "").lower()
        for part in (
            raw,
            metadata.get("description"),
            metadata.get("label"),
            metadata.get("title"),
            (source_node or {}).get("type"),
            (target_node or {}).get("type"),
        )
    )
    source_type = str((source_node or {}).get("type") or "").lower()
    target_type = str((target_node or {}).get("type") or "").lower()

    if raw in {"references", "reference"} and "formula" in target_type:
        return "references_formula"
    if raw in {"references", "reference"} and "table" in target_type:
        return "references_table"
    if raw in PRESET_RELATION_TYPES:
        return raw

    if "formula" in target_type or "formula" in description:
        return "references_formula"
    if "table" in target_type or "table" in description:
        return "references_table"
    if any(token in description for token in ("contain", "include", "section", "chapter", "part")):
        return "contains"
    if any(token in description for token in ("preced", "follow", "next", "sequence", "before", "after")):
        return "precedes"
    if any(token in description for token in ("define", "definition", "means", "term")):
        return "defines"
    if any(token in description for token in ("explain", "clarify", "describe", "account for")):
        return "explains"
    if any(token in description for token in ("derive", "proof", "theorem", "equation", "result")):
        return "derives"
    if any(token in description for token in ("depend", "require", "base", "prereq", "use")):
        return "depends_on"
    if any(token in description for token in ("support", "evidence", "justify")):
        return "supports"
    if any(token in description for token in ("contrast", "differ", "oppos", "however", "whereas")):
        return "contrasts_with"
    if any(token in description for token in ("example", "case", "illustrat")):
        return "example_of"
    if any(token in description for token in ("apply", "application")):
        return "applies_to"
    if any(token in description for token in ("equivalent", "same", "identity")):
        return "equivalent_to"
    if any(token in description for token in ("cause", "lead", "effect", "result")):
        return "causes"

    if raw and raw not in {"other", "unknown", "none", "related"}:
        return raw
    return "related"


def _safe_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _merge_metadata(row: sqlite3.Row | Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    if hasattr(row, "keys") and "metadata_json" in row.keys():
        metadata = _safe_json(row["metadata_json"])
    metadata.update(base)
    return metadata


def _score_text(query: str, text: str) -> float:
    query = (query or "").strip().lower()
    text = (text or "").strip().lower()
    if not query or not text:
        return 0.0
    if query in text:
        return 1.0

    query_tokens = set(re.findall(r"\w+", query, flags=re.UNICODE))
    text_tokens = set(re.findall(r"\w+", text, flags=re.UNICODE))
    if query_tokens and text_tokens:
        overlap = len(query_tokens & text_tokens)
        union = len(query_tokens | text_tokens)
        if union:
            return overlap / union

    return len(set(query) & set(text)) / max(len(set(query)), 1)


def _sparse_terms(value: str) -> Dict[str, float]:
    text = (value or "").lower()
    terms: Dict[str, float] = {}

    for token in re.findall(r"[\w]+", text, flags=re.UNICODE):
        if len(token) <= 1:
            continue
        terms[f"tok:{token}"] = terms.get(f"tok:{token}", 0.0) + 1.0

    compact = re.sub(r"\s+", "", text)
    for size, weight in ((2, 0.6), (3, 0.9)):
        if len(compact) < size:
            continue
        for index in range(0, len(compact) - size + 1):
            gram = compact[index : index + size]
            if not gram.strip():
                continue
            terms[f"ng{size}:{gram}"] = terms.get(f"ng{size}:{gram}", 0.0) + weight

    return terms


def _cosine_sparse(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    if dot <= 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


class GraphService:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retrieval_mode = os.getenv("KGTS_RETRIEVAL_MODE", "hybrid").strip().lower()
        self._vector_last_error: Optional[str] = None
        self.vector_index = None
        if self.retrieval_mode == "hybrid":
            try:
                self.vector_index = GraphVectorIndex()
            except VectorIndexUnavailable as exc:
                self._vector_last_error = str(exc)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT,
                    metadata_json TEXT,
                    source TEXT,
                    confidence REAL DEFAULT 1.0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    reviewed INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS relationships (
                    id TEXT PRIMARY KEY,
                    source_node TEXT NOT NULL,
                    target_node TEXT NOT NULL,
                    type TEXT NOT NULL,
                    strength REAL DEFAULT 1.0,
                    description TEXT,
                    metadata_json TEXT,
                    source TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    reviewed INTEGER DEFAULT 0,
                    FOREIGN KEY (source_node) REFERENCES nodes(id),
                    FOREIGN KEY (target_node) REFERENCES nodes(id)
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
                CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(type);
                CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_node);
                CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_node);
                """
            )
            try:
                conn.execute("ALTER TABLE nodes ADD COLUMN metadata_json TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE relationships ADD COLUMN metadata_json TEXT")
            except sqlite3.OperationalError:
                pass

    def _node_row_to_api(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        label = row["label"]
        content = row["content"] or label
        metadata = _merge_metadata(
            row,
            {
                "label": label,
                "description": content,
                "source": row["source"],
                "confidence": row["confidence"],
                "reviewed": bool(row["reviewed"]),
            },
        )
        return {
            "id": row["id"],
            "content": content,
            "type": row["type"],
            "metadata": metadata,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "label": label,
        }

    def _relation_row_to_api(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        metadata = _merge_metadata(
            row,
            {
                "description": row["description"] or "",
                "source": row["source"],
                "reviewed": bool(row["reviewed"]),
            },
        )
        return {
            "id": row["id"],
            "source_id": row["source_node"],
            "target_id": row["target_node"],
            "relation_type": row["type"],
            "metadata": metadata,
            "similarity": row["strength"],
            "source_node": row["source_node"],
            "target_node": row["target_node"],
        }

    def _fetch_node_rows(self, node_type: Optional[str] = None, limit: Optional[int] = 1000) -> List[sqlite3.Row]:
        with self._connection() as conn:
            if node_type:
                if limit is None:
                    rows = conn.execute(
                        """
                        SELECT id, label, type, content, metadata_json, source, confidence, created_at, updated_at, reviewed
                        FROM nodes
                        WHERE type = ?
                        ORDER BY updated_at DESC, created_at DESC
                        """,
                        (node_type,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, label, type, content, metadata_json, source, confidence, created_at, updated_at, reviewed
                        FROM nodes
                        WHERE type = ?
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT ?
                        """,
                        (node_type, limit),
                    ).fetchall()
            else:
                if limit is None:
                    rows = conn.execute(
                        """
                        SELECT id, label, type, content, metadata_json, source, confidence, created_at, updated_at, reviewed
                        FROM nodes
                        ORDER BY updated_at DESC, created_at DESC
                        """
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, label, type, content, metadata_json, source, confidence, created_at, updated_at, reviewed
                        FROM nodes
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
        return rows

    def _fetch_all_node_rows(self, node_type: Optional[str] = None) -> List[sqlite3.Row]:
        return self._fetch_node_rows(node_type=node_type, limit=None)

    def _fetch_relation_rows(
        self,
        node_id: Optional[str] = None,
        relation_type: Optional[str] = None,
        limit: int = 5000,
    ) -> List[sqlite3.Row]:
        clauses: List[str] = []
        params: List[Any] = []
        if node_id:
            clauses.append("(source_node = ? OR target_node = ?)")
            params.extend([node_id, node_id])
        if relation_type:
            clauses.append("type = ?")
            params.append(relation_type)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT id, source_node, target_node, type, strength, description, metadata_json, source, created_at, updated_at, reviewed
            FROM relationships
            {where_clause}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
        """
        params.append(limit)
        with self._connection() as conn:
            return conn.execute(query, params).fetchall()

    def read_graph(self) -> Dict[str, Any]:
        nodes = [self._node_row_to_api(row) for row in self._fetch_node_rows(limit=20000)]
        relations = [self._relation_row_to_api(row) for row in self._fetch_relation_rows(limit=100000)]
        node_types: Dict[str, int] = {}
        for node in nodes:
            node_types[node["type"]] = node_types.get(node["type"], 0) + 1
        return {
            "nodes": nodes,
            "relations": relations,
            "stats": {
                "node_count": len(nodes),
                "relation_count": len(relations),
                "node_types": node_types,
            },
            "vector_stats": self._vector_stats(),
        }

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, label, type, content, metadata_json, source, confidence, created_at, updated_at, reviewed
                FROM nodes WHERE id = ?
                """,
                (node_id,),
            ).fetchone()
        return self._node_row_to_api(row) if row else None

    def search_nodes(self, keyword: str, node_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        clauses = ["(label LIKE ? OR content LIKE ?)"]
        params: List[Any] = [f"%{keyword}%", f"%{keyword}%"]
        if node_type:
            clauses.append("type = ?")
            params.append(node_type)
        params.append(limit)
        query = f"""
            SELECT id, label, type, content, metadata_json, source, confidence, created_at, updated_at, reviewed
            FROM nodes
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
        """
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._node_row_to_api(row) for row in rows]

    def semantic_search(
        self,
        query: str,
        node_type: Optional[str] = None,
        top_k: int = 10,
        allowed_node_ids: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        global _LAST_VECTOR_ERROR
        allowed_ids = self._normalize_allowed_node_ids(allowed_node_ids)
        if self.retrieval_mode == "hybrid":
            try:
                results = self._hybrid_search(query, node_type=node_type, top_k=top_k, allowed_node_ids=allowed_ids)
                _LAST_VECTOR_ERROR = None
                return results
            except Exception as exc:
                self._vector_last_error = str(exc)
                _LAST_VECTOR_ERROR = str(exc)
                if self.vector_index is not None:
                    self.vector_index.last_error = str(exc)
                return []
        if self.retrieval_mode == "sparse_hybrid":
            return self._sparse_hybrid_search(query, node_type=node_type, top_k=top_k, allowed_node_ids=allowed_ids)
        return self._text_semantic_search(query, node_type=node_type, top_k=top_k, allowed_node_ids=allowed_ids)

    def _normalize_allowed_node_ids(self, values: Optional[Iterable[str]]) -> Optional[Set[str]]:
        if not values:
            return None
        allowed = {str(value or "").strip() for value in values}
        allowed.discard("")
        return allowed or None

    def _text_semantic_search(
        self,
        query: str,
        node_type: Optional[str] = None,
        top_k: int = 10,
        allowed_node_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        candidates = [self._node_row_to_api(row) for row in self._fetch_node_rows(node_type=node_type, limit=5000)]
        if allowed_node_ids is not None:
            candidates = [candidate for candidate in candidates if str(candidate.get("id") or "") in allowed_node_ids]
        scored: List[Dict[str, Any]] = []
        for candidate in candidates:
            haystack = f"{candidate['metadata'].get('label', '')}\n{candidate['content']}"
            score = _score_text(query, haystack)
            if score <= 0:
                continue
            scored.append(
                {
                    "node_id": candidate["id"],
                    "similarity": round(score, 4),
                    "metadata": {
                        "label": candidate["metadata"].get("label"),
                        "type": candidate["type"],
                        "content": candidate["content"],
                    },
                }
            )
        scored.sort(key=lambda item: item["similarity"], reverse=True)
        return scored[:top_k]

    def _hybrid_search(
        self,
        query: str,
        node_type: Optional[str] = None,
        top_k: int = 10,
        allowed_node_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        vector = self._ensure_vector_index()
        candidates = [self._node_row_to_api(row) for row in self._fetch_node_rows(node_type=node_type, limit=5000)]
        if allowed_node_ids is not None:
            candidates = [candidate for candidate in candidates if str(candidate.get("id") or "") in allowed_node_ids]
        candidates_by_id = {candidate["id"]: candidate for candidate in candidates}
        if not candidates_by_id:
            return []
        multiplier = max(1, int(os.getenv("KGTS_VECTOR_TOP_K_MULTIPLIER", "3") or "3"))
        candidate_limit = max(top_k * multiplier, top_k)
        try:
            vector_hits = vector.search(
                query,
                top_k=candidate_limit,
                node_type=node_type,
                allowed_node_ids=allowed_node_ids,
            )
        except TypeError:
            vector_hits = vector.search(query, top_k=candidate_limit, node_type=node_type)
        text_hits = self._text_semantic_search(
            query,
            node_type=node_type,
            top_k=candidate_limit,
            allowed_node_ids=allowed_node_ids,
        )

        combined: Dict[str, Dict[str, Any]] = {}
        for hit in vector_hits:
            node_id = str(hit.get("node_id") or "")
            if not node_id or node_id not in candidates_by_id:
                continue
            combined.setdefault(node_id, {"vector_score": 0.0, "text_score": 0.0})
            combined[node_id]["vector_score"] = max(combined[node_id]["vector_score"], float(hit.get("vector_score", hit.get("similarity", 0.0)) or 0.0))

        for hit in text_hits:
            node_id = str(hit.get("node_id") or "")
            if not node_id or node_id not in candidates_by_id:
                continue
            combined.setdefault(node_id, {"vector_score": 0.0, "text_score": 0.0})
            combined[node_id]["text_score"] = max(combined[node_id]["text_score"], float(hit.get("similarity", 0.0) or 0.0))

        if not combined and vector_hits:
            return []
        if not combined:
            return text_hits[:top_k]

        results: List[Dict[str, Any]] = []
        for node_id, scores in combined.items():
            candidate = candidates_by_id[node_id]
            relations = self.get_relations(node_id=node_id, limit=200)
            graph_score = min(len(relations) / 10.0, 1.0)
            vector_score = max(0.0, min(float(scores.get("vector_score", 0.0)), 1.0))
            text_score = max(0.0, min(float(scores.get("text_score", 0.0)), 1.0))
            hybrid_score = (0.65 * vector_score) + (0.25 * text_score) + (0.10 * graph_score)
            metadata = {
                "label": candidate["metadata"].get("label"),
                "type": candidate["type"],
                "content": candidate["content"],
            }
            results.append(
                {
                    "node_id": node_id,
                    "similarity": round(hybrid_score, 4),
                    "metadata": metadata,
                    "retrieval_source": "hybrid",
                    "vector_score": round(vector_score, 4),
                    "text_score": round(text_score, 4),
                    "graph_score": round(graph_score, 4),
                    "hybrid_score": round(hybrid_score, 4),
                }
            )

        results.sort(key=lambda item: item["hybrid_score"], reverse=True)
        return results[:top_k]

    def _sparse_hybrid_search(
        self,
        query: str,
        node_type: Optional[str] = None,
        top_k: int = 10,
        allowed_node_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        query_terms = _sparse_terms(query)
        if not query_terms:
            return []

        candidates = [self._node_row_to_api(row) for row in self._fetch_node_rows(node_type=node_type, limit=5000)]
        if allowed_node_ids is not None:
            candidates = [candidate for candidate in candidates if str(candidate.get("id") or "") in allowed_node_ids]
        results: List[Dict[str, Any]] = []
        for candidate in candidates:
            haystack = f"{candidate['metadata'].get('label', '')}\n{candidate['type']}\n{candidate['content']}"
            sparse_score = _cosine_sparse(query_terms, _sparse_terms(haystack))
            text_score = _score_text(query, haystack)
            if sparse_score <= 0 and text_score <= 0:
                continue
            relations = self.get_relations(node_id=candidate["id"], limit=200)
            graph_score = min(len(relations) / 10.0, 1.0)
            hybrid_score = (0.65 * sparse_score) + (0.25 * text_score) + (0.10 * graph_score)
            results.append(
                {
                    "node_id": candidate["id"],
                    "similarity": round(hybrid_score, 4),
                    "metadata": {
                        "label": candidate["metadata"].get("label"),
                        "type": candidate["type"],
                        "content": candidate["content"],
                    },
                    "retrieval_source": "sparse_hybrid",
                    "sparse_score": round(sparse_score, 4),
                    "text_score": round(text_score, 4),
                    "graph_score": round(graph_score, 4),
                    "hybrid_score": round(hybrid_score, 4),
                }
            )

        results.sort(key=lambda item: item["hybrid_score"], reverse=True)
        return results[:top_k]

    def _ensure_vector_index(self) -> GraphVectorIndex:
        global _LAST_VECTOR_ERROR
        if self.vector_index is None:
            raise VectorIndexUnavailable("hybrid retrieval is not enabled")
        candidates = [self._node_row_to_api(row) for row in self._fetch_all_node_rows()]
        self.vector_index.ensure_index(candidates)
        self._vector_last_error = None
        _LAST_VECTOR_ERROR = None
        return self.vector_index

    def rebuild_vector_index(self) -> Dict[str, Any]:
        global _LAST_VECTOR_ERROR
        if self.vector_index is None:
            try:
                self.vector_index = GraphVectorIndex()
                self.retrieval_mode = "hybrid"
            except Exception as exc:
                self._vector_last_error = str(exc)
                _LAST_VECTOR_ERROR = str(exc)
                return self._vector_stats()
        candidates = [self._node_row_to_api(row) for row in self._fetch_all_node_rows()]
        try:
            return self.vector_index.rebuild(candidates)
        except Exception as exc:
            self._vector_last_error = str(exc)
            _LAST_VECTOR_ERROR = str(exc)
            self.vector_index.last_error = str(exc)
            return self._vector_stats()

    def reset_vector_index(self) -> Dict[str, Any]:
        if self.vector_index is None:
            try:
                self.vector_index = GraphVectorIndex()
            except Exception as exc:
                self._vector_last_error = str(exc)
                return self._vector_stats()
        return self.vector_index.reset()

    def _vector_stats(self) -> Dict[str, Any]:
        if self.retrieval_mode == "sparse_hybrid":
            return {
                "enabled": True,
                "mode": "sparse_hybrid",
                "provider": "standard-library-sparse",
                "model": "token-char-ngram",
                "db_path": str(self.db_path),
                "path_policy": "project_local" if project_local_only() else "external_paths_allowed",
                "outside_project_paths": [],
                "last_error": None,
            }
        if self.retrieval_mode != "hybrid":
            return {
                "enabled": False,
                "mode": "graph-db",
                "db_path": str(self.db_path),
                "path_policy": "project_local" if project_local_only() else "external_paths_allowed",
                "outside_project_paths": [],
            }
        if self.vector_index is None:
            outside_paths = vector_path_policy_violations()
            return {
                "enabled": False,
                "mode": "hybrid",
                "db_path": str(self.db_path),
                "path_policy": "project_local" if project_local_only() else "external_paths_allowed",
                "outside_project_paths": outside_paths,
                "last_error": self._vector_last_error or "vector index not initialized",
            }
        stats = self.vector_index.get_stats()
        stats["db_path"] = str(self.db_path)
        if self._vector_last_error and not stats.get("last_error"):
            stats["last_error"] = self._vector_last_error
        if _LAST_VECTOR_ERROR and not stats.get("last_error"):
            stats["last_error"] = _LAST_VECTOR_ERROR
        return stats

    def add_node(self, content: str, node_type: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        node_id = str(metadata.get("id") or uuid.uuid4())
        label = str(metadata.get("label") or content[:80] or node_id)
        source = str(metadata.get("source") or "interactive_ui")
        confidence = float(metadata.get("confidence", 1.0))
        timestamp = int(time())
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (id, label, type, content, metadata_json, source, confidence, created_at, updated_at, reviewed)
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    COALESCE((SELECT created_at FROM nodes WHERE id = ?), ?),
                    ?,
                    COALESCE((SELECT reviewed FROM nodes WHERE id = ?), 0)
                )
                """,
                (
                    node_id,
                    label,
                    _normalize_type(node_type),
                    content,
                    json.dumps(metadata, ensure_ascii=False),
                    source,
                    confidence,
                    node_id,
                    timestamp,
                    timestamp,
                    node_id,
                ),
            )
        self._invalidate_vector_index()
        return self.get_node(node_id) or {"id": node_id, "content": content, "type": node_type, "metadata": metadata}

    def update_node(
        self,
        node_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = self.get_node(node_id)
        if current is None:
            return {"success": False, "error": f"Node {node_id} not found"}

        merged_metadata = dict(current.get("metadata") or {})
        merged_metadata.update(metadata or {})
        new_content = content if content is not None else current["content"]
        new_label = str(merged_metadata.get("label") or current.get("label") or new_content[:80] or node_id)
        source = str(merged_metadata.get("source") or current["metadata"].get("source") or "interactive_ui")
        confidence = float(merged_metadata.get("confidence", current["metadata"].get("confidence", 1.0)))
        timestamp = int(time())
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE nodes
                SET label = ?, content = ?, metadata_json = ?, source = ?, confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_label, new_content, json.dumps(merged_metadata, ensure_ascii=False), source, confidence, timestamp, node_id),
            )
        self._invalidate_vector_index()
        return {"success": True, "node": self.get_node(node_id)}

    def delete_node(self, node_id: str) -> Dict[str, Any]:
        with self._connection() as conn:
            conn.execute("DELETE FROM relationships WHERE source_node = ? OR target_node = ?", (node_id, node_id))
            cursor = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        self._invalidate_vector_index()
        return {"success": cursor.rowcount > 0}

    def _invalidate_vector_index(self) -> None:
        global _LAST_VECTOR_ERROR
        if self.vector_index is not None:
            mark_stale = getattr(self.vector_index, "mark_stale", None)
            if callable(mark_stale):
                mark_stale()
            self.vector_index.last_error = None
        self._vector_last_error = None
        _LAST_VECTOR_ERROR = None

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        similarity: Optional[float] = None,
    ) -> Dict[str, Any]:
        metadata = metadata or {}
        requested_type = relation_type
        relation_type = normalize_relation_type(
            requested_type,
            metadata,
            self.get_node(source_id),
            self.get_node(target_id),
        )
        if relation_type != requested_type:
            metadata.setdefault("original_relation_type", requested_type)
            metadata.setdefault("relation_inference", "preset_or_other_resolution")
        rel_id = str(metadata.get("id") or f"[{source_id}]_{relation_type}_{target_id}")
        timestamp = int(time())
        description = str(metadata.get("description") or "")
        source = str(metadata.get("source") or "interactive_ui")
        strength = float(similarity if similarity is not None else metadata.get("strength", 1.0))
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO relationships (
                    id, source_node, target_node, type, strength, description, metadata_json, source, created_at, updated_at, reviewed
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM relationships WHERE id = ?), ?),
                    ?,
                    COALESCE((SELECT reviewed FROM relationships WHERE id = ?), 0)
                )
                """,
                (
                    rel_id,
                    source_id,
                    target_id,
                    relation_type,
                    strength,
                    description,
                    json.dumps(metadata, ensure_ascii=False),
                    source,
                    rel_id,
                    timestamp,
                    timestamp,
                    rel_id,
                ),
            )
        relation = self.get_relations(node_id=source_id)
        for item in relation:
            if item["id"] == rel_id:
                return item
        return {
            "id": rel_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "metadata": metadata,
            "similarity": strength,
        }

    def get_relations(
        self,
        node_id: Optional[str] = None,
        relation_type: Optional[str] = None,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        return [self._relation_row_to_api(row) for row in self._fetch_relation_rows(node_id, relation_type, limit)]

    def get_relation(self, relation_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, source_node, target_node, type, strength, description, metadata_json, source, created_at, updated_at, reviewed
                FROM relationships
                WHERE id = ?
                """,
                (relation_id,),
            ).fetchone()
        return self._relation_row_to_api(row) if row else None

    def update_relation(
        self,
        relation_id: str,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        similarity: Optional[float] = None,
    ) -> Dict[str, Any]:
        current = self.get_relation(relation_id)
        if current is None:
            return {"success": False, "error": f"Relation {relation_id} not found"}

        merged_metadata = dict(current.get("metadata") or {})
        merged_metadata.update(metadata or {})
        new_source = source_id or current["source_id"]
        new_target = target_id or current["target_id"]
        requested_type = relation_type or current["relation_type"]
        new_type = normalize_relation_type(
            requested_type,
            merged_metadata,
            self.get_node(new_source),
            self.get_node(new_target),
        )
        if new_type != requested_type:
            merged_metadata.setdefault("original_relation_type", requested_type)
            merged_metadata.setdefault("relation_inference", "preset_or_other_resolution")
        description = str(merged_metadata.get("description") or "")
        source = str(merged_metadata.get("source") or current["metadata"].get("source") or "interactive_ui")
        strength = float(similarity if similarity is not None else current.get("similarity") or 1.0)
        timestamp = int(time())

        with self._connection() as conn:
            conn.execute(
                """
                UPDATE relationships
                SET source_node = ?, target_node = ?, type = ?, strength = ?, description = ?, metadata_json = ?, source = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_source,
                    new_target,
                    new_type,
                    strength,
                    description,
                    json.dumps(merged_metadata, ensure_ascii=False),
                    source,
                    timestamp,
                    relation_id,
                ),
            )
        return {"success": True, "relation": self.get_relation(relation_id)}

    def delete_relation(self, relation_id: str) -> Dict[str, Any]:
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM relationships WHERE id = ?", (relation_id,))
        return {"success": cursor.rowcount > 0}

    def delete_by_sources(self, sources: Iterable[str]) -> Dict[str, Any]:
        source_values = [str(source or "").strip() for source in sources if str(source or "").strip()]
        if not source_values:
            return {"nodes_deleted": 0, "relations_deleted": 0}
        placeholders = ",".join("?" for _ in source_values)
        with self._connection() as conn:
            relation_cursor = conn.execute(
                f"DELETE FROM relationships WHERE source IN ({placeholders})",
                source_values,
            )
            node_cursor = conn.execute(
                f"DELETE FROM nodes WHERE source IN ({placeholders})",
                source_values,
            )
            orphan_cursor = conn.execute(
                """
                DELETE FROM relationships
                WHERE source_node NOT IN (SELECT id FROM nodes)
                   OR target_node NOT IN (SELECT id FROM nodes)
                """
            )
        self._invalidate_vector_index()
        return {
            "nodes_deleted": node_cursor.rowcount,
            "relations_deleted": relation_cursor.rowcount + orphan_cursor.rowcount,
        }

    def batch_import_graph(self, nodes: List[Dict[str, Any]], relations: List[Dict[str, Any]]) -> Dict[str, Any]:
        node_map: Dict[str, str] = {}
        imported_nodes = 0
        imported_relations = 0
        errors: List[str] = []

        for node in nodes:
            try:
                metadata = _safe_json(node.get("metadata"))
                if node.get("label") and "label" not in metadata:
                    metadata["label"] = node["label"]
                if node.get("source") and "source" not in metadata:
                    metadata["source"] = node["source"]
                if node.get("id"):
                    metadata["id"] = node["id"]

                created = self.add_node(
                    content=str(node.get("content") or node.get("label") or ""),
                    node_type=str(node.get("type") or "concept"),
                    metadata=metadata,
                )
                source_id = str(node.get("id") or created["id"])
                node_map[source_id] = created["id"]
                imported_nodes += 1
            except Exception as exc:
                errors.append(f"node:{node.get('id', 'unknown')}:{exc}")

        for relation in relations:
            try:
                source_id = relation.get("source_id") or relation.get("source")
                target_id = relation.get("target_id") or relation.get("target")
                relation_type = relation.get("relation_type") or relation.get("type") or "related"
                metadata = _safe_json(relation.get("metadata"))
                if relation.get("description") and "description" not in metadata:
                    metadata["description"] = relation["description"]
                self.add_relation(
                    source_id=node_map.get(str(source_id), str(source_id)),
                    target_id=node_map.get(str(target_id), str(target_id)),
                    relation_type=str(relation_type),
                    metadata=metadata,
                    similarity=relation.get("similarity") or relation.get("strength"),
                )
                imported_relations += 1
            except Exception as exc:
                errors.append(
                    f"relation:{relation.get('source_id') or relation.get('source')}->{relation.get('target_id') or relation.get('target')}:{exc}"
                )

        return {
            "nodes": {"total": len(nodes), "success": imported_nodes, "failed": len(nodes) - imported_nodes},
            "relations": {
                "total": len(relations),
                "success": imported_relations,
                "failed": len(relations) - imported_relations,
            },
            "errors": errors,
        }

    def get_graph_statistics(self) -> Dict[str, Any]:
        with self._connection() as conn:
            total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            total_relations = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            node_types = {
                row["type"]: row["count"]
                for row in conn.execute("SELECT type, COUNT(*) AS count FROM nodes GROUP BY type").fetchall()
            }
            relation_types = {
                row["type"]: row["count"]
                for row in conn.execute("SELECT type, COUNT(*) AS count FROM relationships GROUP BY type").fetchall()
            }

        density = 0.0
        if total_nodes > 1:
            density = total_relations / (total_nodes * (total_nodes - 1) / 2)

        return {
            "nodes": {"total": total_nodes, "by_type": node_types},
            "relations": {"total": total_relations, "by_type": relation_types},
            "connectivity": {
                "unique_connections": total_relations,
                "average_degree": round((total_relations * 2) / total_nodes, 2) if total_nodes else 0,
                "density": round(density, 4),
            },
            "vector_stats": self._vector_stats(),
        }

    def get_subgraph_by_type(self, node_type: str) -> Dict[str, Any]:
        nodes = self.search_nodes("", node_type=node_type, limit=5000) if node_type else []
        if not nodes:
            nodes = [self._node_row_to_api(row) for row in self._fetch_node_rows(node_type=node_type, limit=5000)]
        node_ids = {node["id"] for node in nodes}
        relations = [
            relation
            for relation in self.get_relations(limit=10000)
            if relation["source_id"] in node_ids and relation["target_id"] in node_ids
        ]
        return {
            "type": node_type,
            "nodes": nodes,
            "relations": relations,
            "stats": {"node_count": len(nodes), "relation_count": len(relations)},
        }

    def get_k_hop_neighbors(self, node_id: str, k: int = 2) -> Dict[str, Any]:
        layers: Dict[int, List[Dict[str, Any]]] = {}
        visited = {node_id}
        queue = deque([(node_id, 0)])
        while queue:
            current_id, depth = queue.popleft()
            if depth > k:
                continue
            node = self.get_node(current_id)
            if node:
                layers.setdefault(depth, []).append(node)
            if depth == k:
                continue
            for relation in self.get_relations(node_id=current_id):
                neighbor_id = relation["target_id"] if relation["source_id"] == current_id else relation["source_id"]
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                queue.append((neighbor_id, depth + 1))
        return {str(depth): nodes for depth, nodes in layers.items()}

    def get_neighbors(self, node_id: str, direction: str = "both") -> Dict[str, List[Dict[str, Any]]]:
        results = {"in": [], "out": []}
        for relation in self.get_relations(node_id=node_id):
            if direction in {"in", "both"} and relation["target_id"] == node_id:
                source_node = self.get_node(relation["source_id"])
                if source_node:
                    results["in"].append(source_node)
            if direction in {"out", "both"} and relation["source_id"] == node_id:
                target_node = self.get_node(relation["target_id"])
                if target_node:
                    results["out"].append(target_node)
        return results

    def _walk_paths(self, start_node_id: str, max_depth: int, direction: str) -> List[Dict[str, Any]]:
        paths: List[Dict[str, Any]] = []
        queue = deque([(start_node_id, 0, [start_node_id])])
        visited = {start_node_id}

        while queue:
            current_id, depth, path = queue.popleft()
            if depth >= max_depth:
                continue

            for relation in self.get_relations(node_id=current_id):
                if direction == "out" and relation["source_id"] != current_id:
                    continue
                if direction == "in" and relation["target_id"] != current_id:
                    continue

                next_id = relation["target_id"] if relation["source_id"] == current_id else relation["source_id"]
                if next_id in visited:
                    continue
                visited.add(next_id)
                next_path = path + [next_id]
                node = self.get_node(next_id)
                paths.append(
                    {
                        "node_id": next_id,
                        "depth": depth + 1,
                        "path": next_path,
                        "node": node or {"id": next_id},
                    }
                )
                queue.append((next_id, depth + 1, next_path))
        return paths

    def get_prerequisites(self, node_id: str, max_depth: int = 3) -> List[Dict[str, Any]]:
        return self._walk_paths(node_id, max_depth=max_depth, direction="in")

    def get_follow_up(self, node_id: str, max_depth: int = 3) -> List[Dict[str, Any]]:
        return self._walk_paths(node_id, max_depth=max_depth, direction="out")

    def get_note(self, node_id: Optional[str] = None) -> Any:
        if node_id:
            node = self.get_node(node_id)
            return node if node and node.get("type") == "observation" else None
        return [self._node_row_to_api(row) for row in self._fetch_node_rows(node_type="observation", limit=5000)]
