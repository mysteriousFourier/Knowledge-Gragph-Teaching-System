"""Bridge layer between the frontend APIs and vector_index_system."""

from __future__ import annotations

import json
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
VECTOR_SYSTEM_DIR = BACKEND_DIR / "vector_index_system"
MCP_SERVER_DIR = BACKEND_DIR / "mcp-server"
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
LEGACY_CHAPTERS_FILE = BACKEND_DIR / "data" / "chapters.json"
LEGACY_PROGRESS_FILE = BACKEND_DIR / "data" / "chapter_progress.json"
CHAPTERS_FILE = RUNTIME_DIR / "chapters.json"
PROGRESS_FILE = RUNTIME_DIR / "chapter_progress.json"

for path in (VECTOR_SYSTEM_DIR, MCP_SERVER_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from cli import dispatch_tool  # type: ignore  # noqa: E402
from memory_runtime import MemoryService  # type: ignore  # noqa: E402
from graphml_importer import convert_to_mcp_format, parse_graphml_file  # type: ignore  # noqa: E402


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0

    text = str(value).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _chapter_sort_value(chapter: Dict[str, Any]) -> float:
    return _timestamp_value(chapter.get("updated_at") or chapter.get("created_at"))


def _chapter_identity(chapter: Dict[str, Any]) -> str:
    raw_id = str(chapter.get("id") or "").strip()
    lowered_id = raw_id.lower()
    for prefix in ("chapter::", "chapter_"):
        if lowered_id.startswith(prefix):
            return lowered_id[len(prefix) :]
    return lowered_id or str(chapter.get("title") or "").strip().lower()


def _text_len(value: Any) -> int:
    return len(value) if isinstance(value, str) else 0


def _chapter_detail_score(chapter: Dict[str, Any]) -> tuple[int, int, int, float]:
    content_len = _text_len(chapter.get("content"))
    lecture_len = _text_len(chapter.get("lecture_content"))
    has_graph = 1 if chapter.get("graph_data") else 0
    preferred_id = 1 if str(chapter.get("id") or "").startswith("chapter::") else 0
    return (lecture_len * 2 + content_len, has_graph, preferred_id, _chapter_sort_value(chapter))


def _dedupe_chapters(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_identity: Dict[str, Dict[str, Any]] = {}
    for chapter in chapters:
        identity = _chapter_identity(chapter)
        current = best_by_identity.get(identity)
        if current is None or _chapter_detail_score(chapter) > _chapter_detail_score(current):
            best_by_identity[identity] = chapter
    return list(best_by_identity.values())


def call_backend_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
    return dispatch_tool(name, arguments or {})


def _node_label(node: Dict[str, Any]) -> str:
    metadata = node.get("metadata") or {}
    return (
        node.get("label")
        or metadata.get("label")
        or node.get("content")
        or node.get("id")
        or "untitled"
    )


def _node_size(node_type: str) -> str:
    if node_type == "chapter":
        return "large"
    if node_type in {"note", "observation"}:
        return "small"
    return "medium"


def _normalize_node(node: Dict[str, Any]) -> Dict[str, Any]:
    label = _node_label(node)
    metadata = dict(node.get("metadata") or {})
    content = node.get("content") or metadata.get("description") or label
    return {
        **node,
        "id": node.get("id"),
        "label": label,
        "content": content,
        "type": node.get("type") or metadata.get("type") or "concept",
        "size": node.get("size") or _node_size(node.get("type") or "concept"),
        "metadata": metadata,
    }


def _normalize_relation(relation: Dict[str, Any]) -> Dict[str, Any]:
    source_id = relation.get("source_id") or relation.get("source") or relation.get("from")
    target_id = relation.get("target_id") or relation.get("target") or relation.get("to")
    relation_type = relation.get("relation_type") or relation.get("type") or relation.get("label") or "related"
    metadata = dict(relation.get("metadata") or relation.get("properties") or {})
    return {
        **relation,
        "source_id": source_id,
        "target_id": target_id,
        "source": source_id,
        "target": target_id,
        "relation_type": relation_type,
        "type": relation_type,
        "metadata": metadata,
    }


def build_frontend_graph(raw_graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    graph = raw_graph or call_backend_tool("read_graph")
    nodes = [_normalize_node(node) for node in graph.get("nodes", [])]
    relations = [_normalize_relation(relation) for relation in graph.get("relations", [])]
    return {
        **graph,
        "nodes": nodes,
        "relations": relations,
        "edges": relations,
    }


def get_graph_schema() -> Dict[str, Any]:
    schema = call_backend_tool("get_graph_schema")
    if isinstance(schema, dict):
        return schema
    graph = build_frontend_graph()
    return {
        "stats": graph.get("stats", {}),
        "vector_stats": graph.get("vector_stats", {}),
        "node_types": sorted({node.get("type") for node in graph.get("nodes", []) if node.get("type")}),
        "relation_types": sorted(
            {edge.get("relation_type") or edge.get("type") for edge in graph.get("relations", []) if edge.get("relation_type") or edge.get("type")}
        ),
    }


def search_nodes(keyword: str, node_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    results = call_backend_tool(
        "search_nodes",
        {"keyword": keyword, "node_type": node_type, "limit": limit},
    )
    if isinstance(results, list):
        return [_normalize_node(result) for result in results]
    if isinstance(results, dict) and isinstance(results.get("results"), list):
        return [_normalize_node(result) for result in results["results"]]
    return []


def semantic_search(query: str, node_type: Optional[str] = None, top_k: int = 10) -> List[Dict[str, Any]]:
    results = call_backend_tool(
        "semantic_search",
        {"query": query, "node_type": node_type, "top_k": top_k},
    )
    if isinstance(results, list):
        return results
    if isinstance(results, dict) and isinstance(results.get("results"), list):
        return results["results"]
    return []


def search_memory(query: str, k: int = 5) -> Dict[str, Any]:
    return MemoryService().search_memory(query, k=k)


def build_rag_context(question: str, limit: int = 6) -> Dict[str, Any]:
    try:
        keyword_hits = search_nodes(question, limit=limit)
    except Exception:
        keyword_hits = []

    try:
        semantic_hits = semantic_search(question, top_k=limit)
    except Exception:
        semantic_hits = []

    try:
        memory_payload = search_memory(question, k=limit)
        memory_hits = memory_payload.get("results", []) if isinstance(memory_payload, dict) else []
    except Exception:
        memory_hits = []

    llm_context: List[Dict[str, Any]] = []
    context_lines: List[str] = []
    seen: set[str] = set()

    def add_context(source_id: str, label: str, node_type: str, content: str, source: str) -> None:
        clean_label = (label or source_id or "untitled").strip()
        clean_content = (content or clean_label).strip()
        key = f"{source}:{source_id or clean_label}:{clean_content[:80]}"
        if not clean_content or key in seen:
            return
        seen.add(key)
        clipped = clean_content[:700]
        llm_context.append(
            {
                "content": clipped,
                "metadata": {
                    "id": source_id,
                    "label": clean_label,
                    "type": node_type or "context",
                    "source": source,
                },
            }
        )
        context_lines.append(f"- [{source}] {clean_label} ({node_type or 'context'}): {clipped[:220]}")

    for hit in keyword_hits:
        metadata = hit.get("metadata") or {}
        add_context(
            str(hit.get("id") or metadata.get("id") or ""),
            _node_label(hit),
            str(hit.get("type") or metadata.get("type") or ""),
            str(hit.get("content") or metadata.get("description") or _node_label(hit)),
            "keyword",
        )

    for hit in semantic_hits:
        metadata = hit.get("metadata") or {}
        add_context(
            str(hit.get("node_id") or metadata.get("id") or ""),
            str(metadata.get("label") or hit.get("node_id") or "semantic_hit"),
            str(metadata.get("type") or ""),
            str(metadata.get("content") or metadata.get("description") or metadata.get("label") or ""),
            "vector",
        )

    for hit in memory_hits:
        metadata = hit.get("metadata") or {}
        add_context(
            str(metadata.get("id") or hit.get("id") or ""),
            str(metadata.get("label") or metadata.get("provider") or "memory"),
            str(metadata.get("type") or "memory"),
            str(hit.get("content") or ""),
            "memory",
        )

    return {
        "context": "\n".join(context_lines[:limit]),
        "llm_context": llm_context[:limit],
        "keyword_hits": keyword_hits,
        "semantic_hits": semantic_hits,
        "memory_hits": memory_hits,
    }


def _build_local_answer_legacy(question: str, limit: int = 5) -> Dict[str, Any]:
    rag_context = build_rag_context(question, limit=limit)
    keyword_hits = rag_context["keyword_hits"]
    semantic_hits = rag_context["semantic_hits"]
    memory_hits = rag_context["memory_hits"]

    lines: List[str] = []
    seen: set[str] = set()

    for hit in keyword_hits:
        label = _node_label(hit)
        text = (hit.get("content") or label).strip()
        if label in seen:
            continue
        seen.add(label)
        lines.append(f"- {label}: {text[:140]}")

    for hit in semantic_hits:
        metadata = hit.get("metadata") or {}
        label = metadata.get("label") or hit.get("node_id") or "semantic_hit"
        text = (metadata.get("content") or label).strip()
        if label in seen:
            continue
        seen.add(label)
        lines.append(f"- {label}: {text[:140]}")

    for hit in memory_hits:
        label = hit.get("metadata", {}).get("provider") or "memory"
        text = str(hit.get("content") or "").strip()
        key = f"{label}:{text[:40]}"
        if not text or key in seen:
            continue
        seen.add(key)
        lines.append(f"- [{label}] {text[:140]}")

    if lines:
        answer = '基于当前图谱和记忆检索，相关内容如下：\\n' + "\n".join(lines[:limit])
    else:
        answer = '当前图谱和记忆库中没有检索到与该问题直接相关的内容。'

    return {
        "answer": answer,
        "keyword_hits": keyword_hits,
        "semantic_hits": semantic_hits,
        "memory_hits": memory_hits,
    }


def build_local_answer(question: str, limit: int = 5) -> Dict[str, Any]:
    rag_context = build_rag_context(question, limit=limit)
    lines: List[str] = []
    seen: set[str] = set()

    for item in rag_context["llm_context"]:
        metadata = item.get("metadata") or {}
        label = metadata.get("label") or metadata.get("id") or "context"
        source = metadata.get("source") or "graph"
        text = str(item.get("content") or "").strip()
        key = f"{source}:{label}:{text[:40]}"
        if not text or key in seen:
            continue
        seen.add(key)
        lines.append(f"- [{source}] {label}: {text[:180]}")

    if lines:
        answer = '基于当前图谱和记忆检索，相关内容如下：\\n' + "\n".join(lines[:limit])
    else:
        answer = '当前图谱和记忆库中没有检索到与该问题直接相关的内容。'

    return {
        "answer": answer,
        "context": rag_context["context"],
        "llm_context": rag_context["llm_context"],
        "keyword_hits": rag_context["keyword_hits"],
        "semantic_hits": rag_context["semantic_hits"],
        "memory_hits": rag_context["memory_hits"],
    }

def import_graph_payload(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    raw_nodes = graph_data.get("nodes", [])
    raw_relations = graph_data.get("relations") or graph_data.get("edges") or []

    nodes: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []

    for node in raw_nodes:
        metadata = dict(node.get("metadata") or node.get("properties") or {})
        if node.get("label") and "label" not in metadata:
            metadata["label"] = node["label"]
        if node.get("id"):
            metadata["id"] = str(node["id"])
        if node.get("source") and "source" not in metadata:
            metadata["source"] = node["source"]
        nodes.append(
            {
                "id": node.get("id"),
                "content": node.get("content") or node.get("description") or node.get("definition") or node.get("label") or "",
                "type": node.get("type") or "concept",
                "metadata": metadata,
            }
        )

    for relation in raw_relations:
        metadata = dict(relation.get("metadata") or relation.get("properties") or {})
        relations.append(
            {
                "source_id": relation.get("source_id") or relation.get("source") or relation.get("from"),
                "target_id": relation.get("target_id") or relation.get("target") or relation.get("to"),
                "relation_type": relation.get("relation_type") or relation.get("type") or relation.get("label") or "related",
                "metadata": metadata,
                "similarity": relation.get("similarity") or relation.get("strength"),
            }
        )

    return call_backend_tool("batch_import_graph", {"nodes": nodes, "relations": relations})


def import_graphml_payload(
    *,
    file_path: Optional[str] = None,
    file_content: Optional[str] = None,
) -> Dict[str, Any]:
    temp_path: Optional[Path] = None
    try:
        source_path = file_path
        if file_content is not None:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".graphml", delete=False, encoding="utf-8") as handle:
                handle.write(file_content)
                temp_path = Path(handle.name)
            source_path = str(temp_path)

        if not source_path:
            raise ValueError("file_path or file_content is required")

        nodes, edges = parse_graphml_file(source_path)
        converted = convert_to_mcp_format(nodes, edges)
        result = call_backend_tool(
            "batch_import_graph",
            {"nodes": converted.get("nodes", []), "relations": converted.get("edges", [])},
        )
        result["graphml_stats"] = {
            "nodes_parsed": len(nodes),
            "edges_parsed": len(edges),
        }
        result["source_file"] = file_path or "inline_content"
        return result
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


class ChapterStore:
    def __init__(self, chapters_file: Path, progress_file: Path):
        self.chapters_file = chapters_file
        self.progress_file = progress_file
        self.chapters_file.parent.mkdir(parents=True, exist_ok=True)
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_chapters(self) -> Dict[str, Dict[str, Any]]:
        legacy_raw = self._load_json(LEGACY_CHAPTERS_FILE)
        legacy_chapters = legacy_raw.get("chapters")
        raw = self._load_json(self.chapters_file)
        chapters = raw.get("chapters")
        merged: Dict[str, Dict[str, Any]] = {}
        if isinstance(legacy_chapters, dict):
            merged.update(legacy_chapters)
        if isinstance(chapters, dict):
            merged.update(chapters)
        return merged

    def _save_chapters(self, chapters: Dict[str, Dict[str, Any]]) -> None:
        self._save_json(self.chapters_file, {"chapters": chapters})

    def _load_progress(self) -> Dict[str, Any]:
        progress = self._load_json(LEGACY_PROGRESS_FILE)
        progress.update(self._load_json(self.progress_file))
        return progress

    def _save_progress(self, progress: Dict[str, Any]) -> None:
        self._save_json(self.progress_file, progress)

    def _ensure_backend_chapter_node(self, chapter: Dict[str, Any]) -> None:
        call_backend_tool(
            "add_memory",
            {
                "content": chapter.get("content") or chapter.get("lecture_content") or chapter["title"],
                "type": "chapter",
                "metadata": {
                    "id": chapter["id"],
                    "label": chapter["title"],
                    "source": "frontend_test",
                    "chapter_id": chapter["id"],
                },
            },
        )

    def _ensure_backend_lecture_node(self, chapter: Dict[str, Any]) -> None:
        lecture_content = chapter.get("lecture_content")
        if not lecture_content:
            return
        lecture_id = f"{chapter['id']}__lecture"
        call_backend_tool(
            "add_memory",
            {
                "content": lecture_content,
                "type": "observation",
                "metadata": {
                    "id": lecture_id,
                    "label": f"{chapter['title']} 授课文案",
                    "source": "frontend_test",
                    "chapter_id": chapter["id"],
                },
            },
        )
        call_backend_tool(
            "add_relation",
            {
                "source_id": chapter["id"],
                "target_id": lecture_id,
                "relation_type": "contains",
                "metadata": {"description": "chapter lecture"},
            },
        )

    def save_chapter(
        self,
        *,
        title: str,
        content: Optional[str] = None,
        graph_data: Optional[Dict[str, Any]] = None,
        chapter_id: Optional[str] = None,
        sync_backend: bool = True,
    ) -> Dict[str, Any]:
        chapters = self._load_chapters()
        existing_id = None
        if chapter_id and chapter_id in chapters:
            existing_id = chapter_id
        elif chapter_id:
            existing_id = chapter_id
        else:
            for current_id, chapter in chapters.items():
                if chapter.get("title") == title:
                    existing_id = current_id
                    break

        resolved_id = existing_id or f"chapter_{uuid.uuid4().hex[:8]}"
        record = dict(chapters.get(resolved_id) or {})
        record.update(
            {
                "id": resolved_id,
                "title": title,
                "content": content if content is not None else record.get("content", ""),
                "graph_data": graph_data if graph_data is not None else record.get("graph_data"),
                "lecture_content": record.get("lecture_content"),
                "exercises": record.get("exercises"),
                "exercise_bank": record.get("exercise_bank", []),
                "created_at": record.get("created_at") or _now(),
                "updated_at": _now(),
            }
        )
        chapters[resolved_id] = record
        self._save_chapters(chapters)
        if sync_backend:
            self._ensure_backend_chapter_node(record)
        if sync_backend and graph_data:
            import_graph_payload(graph_data)
        return record

    def save_lecture(
        self,
        *,
        chapter_id: str,
        lecture_content: str,
        graph_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        chapter = self.get_chapter(chapter_id) or {
            "id": chapter_id,
            "title": chapter_id,
            "content": "",
            "created_at": _now(),
        }
        chapter["lecture_content"] = lecture_content
        chapter["updated_at"] = _now()
        if graph_data is not None:
            chapter["graph_data"] = graph_data
        saved = self.save_chapter(
            title=chapter["title"],
            content=chapter.get("content", ""),
            graph_data=chapter.get("graph_data"),
            chapter_id=chapter_id,
            sync_backend=False,
        )
        saved["lecture_content"] = lecture_content
        saved["exercises"] = chapter.get("exercises")
        saved["exercise_bank"] = chapter.get("exercise_bank", [])
        chapters = self._load_chapters()
        chapters[chapter_id] = saved
        self._save_chapters(chapters)
        self._ensure_backend_lecture_node(saved)
        return saved

    def save_exercise_bank(
        self,
        *,
        chapter_id: str,
        exercises: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        chapter = self.get_chapter(chapter_id) or {
            "id": chapter_id,
            "title": chapter_id,
            "content": "",
            "created_at": _now(),
        }
        clean_bank = [item for item in exercises if isinstance(item, dict)]
        chapter["exercise_bank"] = clean_bank
        chapter["exercises"] = clean_bank[0] if clean_bank else None
        chapter["updated_at"] = _now()

        saved = self.save_chapter(
            title=chapter["title"],
            content=chapter.get("content", ""),
            graph_data=chapter.get("graph_data"),
            chapter_id=chapter_id,
            sync_backend=False,
        )
        saved["exercise_bank"] = clean_bank
        saved["exercises"] = chapter["exercises"]
        chapters = self._load_chapters()
        chapters[chapter_id] = saved
        self._save_chapters(chapters)
        return saved

    def list_chapters(self) -> List[Dict[str, Any]]:
        chapters = self._load_chapters()
        merged_chapters = dict(chapters)
        changed = False
        try:
            graph = build_frontend_graph()
        except Exception:
            graph = {"nodes": []}
        for node in graph.get("nodes", []):
            if node.get("type") != "chapter":
                continue
            chapter_id = str(node.get("id"))
            if chapter_id in merged_chapters:
                continue
            merged_chapters[chapter_id] = {
                "id": chapter_id,
                "title": _node_label(node),
                "content": node.get("content") or "",
                "graph_data": None,
                "lecture_content": None,
                "exercises": None,
                "exercise_bank": [],
                "created_at": node.get("created_at") or _now(),
                "updated_at": node.get("updated_at") or _now(),
            }
            changed = True
        if changed:
            try:
                self._save_chapters(merged_chapters)
            except OSError:
                pass
        records = _dedupe_chapters(list(merged_chapters.values()))
        records.sort(key=_chapter_sort_value, reverse=True)
        return records

    def get_chapter(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        chapters = self._load_chapters()
        chapter = chapters.get(chapter_id)
        if chapter:
            identity = _chapter_identity(chapter)
            aliases = [
                candidate
                for candidate in chapters.values()
                if _chapter_identity(candidate) == identity
            ]
            if aliases:
                return max(aliases, key=_chapter_detail_score)
            return chapter

        node = call_backend_tool("get_node", {"node_id": chapter_id})
        if isinstance(node, dict) and node.get("id"):
            return {
                "id": chapter_id,
                "title": _node_label(node),
                "content": node.get("content") or "",
                "graph_data": None,
                "lecture_content": None,
                "exercises": None,
                "exercise_bank": [],
                "created_at": node.get("created_at") or _now(),
                "updated_at": node.get("updated_at") or _now(),
            }
        return None

    def mark_learned(self, chapter_id: str, student_id: str = "student_001") -> Dict[str, Any]:
        progress = self._load_progress()
        student_progress = progress.setdefault(student_id, {})
        learned = student_progress.setdefault("learned_chapters", {})
        learned[chapter_id] = _now()
        student_progress["updated_at"] = _now()
        progress[student_id] = student_progress
        self._save_progress(progress)
        return {"student_id": student_id, "chapter_id": chapter_id, "learned_at": learned[chapter_id]}

    def review(self, student_id: str = "student_001") -> Dict[str, Any]:
        chapters = self.list_chapters()
        progress = self._load_progress().get(student_id, {})
        learned = progress.get("learned_chapters", {})
        learned_ids = set(learned.keys()) if isinstance(learned, dict) else set()
        total = len(chapters)
        learned_count = len([chapter for chapter in chapters if chapter["id"] in learned_ids])
        progress_percentage = round((learned_count / total) * 100, 2) if total else 0.0

        recommendations: List[Dict[str, Any]] = []
        for chapter in chapters:
            if chapter["id"] not in learned_ids:
                recommendations.append(
                    {
                        "type": "推荐学习",
                        "content": f"建议继续学习《{chapter['title']}》",
                    }
                )
            if len(recommendations) >= 3:
                break

        if not recommendations and chapters:
            recommendations.append(
                {
                    "type": "复习建议",
                    "content": f"建议回顾《{chapters[0]['title']}》中的关键知识点",
                }
            )

        return {
            "progress": {
                "total_chapters": total,
                "learned_chapters": learned_count,
                "progress_percentage": progress_percentage,
            },
            "recommendations": recommendations,
        }


chapter_store = ChapterStore(CHAPTERS_FILE, PROGRESS_FILE)
