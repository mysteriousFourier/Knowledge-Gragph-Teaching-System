"""Incremental sync from structured JSON sources into the knowledge graph."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
VECTOR_SYSTEM_DIR = BACKEND_DIR / "vector_index_system"
STRUCTURED_DIR = PROJECT_ROOT / "structured"
DATA_DIR = BACKEND_DIR / "data"
MANIFEST_PATH = DATA_DIR / "structured_sync_manifest.json"
TEACHER_PACKAGE_PATH = DATA_DIR / "teacher_memory_package.json"

if str(VECTOR_SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(VECTOR_SYSTEM_DIR))

from graph_service import GraphService, normalize_relation_type  # type: ignore  # noqa: E402


REFERENCE_PATTERN = re.compile(r"\[\[(SEE_)?(FORMULA|TABLE):([^\]]+)\]\]")
FORMULA_REFERENCE_PATTERN = re.compile(r"\[\[(SEE_)?FORMULA:([^\]]+)\]\]", re.I)
_FORMULA_INDEX: Optional[Dict[str, Dict[str, str]]] = None

SEMANTIC_STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "these", "those", "are", "was",
    "were", "will", "can", "may", "not", "but", "into", "than", "then", "such", "under",
    "between", "within", "where", "which", "when", "what", "also", "very", "their",
    "there", "because", "while", "through", "using", "used", "value", "values", "trait",
    "traits", "selection", "response", "equation", "result", "results", "chapter",
}


@dataclass
class SourceSpec:
    source_key: str
    file_hash: str
    nodes: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    chapters: Dict[str, str]


def _now() -> str:
    return datetime.now().isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _load_formula_index() -> Dict[str, Dict[str, str]]:
    global _FORMULA_INDEX
    if _FORMULA_INDEX is not None:
        return _FORMULA_INDEX

    payload = _load_json(STRUCTURED_DIR / "formula_library.json")
    index: Dict[str, Dict[str, str]] = {}
    for item in payload.get("formulas") or []:
        if not isinstance(item, dict):
            continue
        formula_id = str(item.get("id") or "").strip()
        latex = str(item.get("latex") or "").strip()
        if not formula_id or not latex:
            continue
        index[formula_id.lower()] = {
            "id": formula_id,
            "label": str(item.get("label_format") or f"Equation {formula_id}").strip(),
            "latex": latex,
        }
    _FORMULA_INDEX = index
    return index


def _expand_formula_references(text: str, *, display: bool = True) -> str:
    text = str(text or "")
    if "[[" not in text:
        return text
    formula_index = _load_formula_index()

    def replace(match: re.Match[str]) -> str:
        formula_id = match.group(2).strip()
        record = formula_index.get(formula_id.lower())
        if not record:
            return f"Equation {formula_id}"
        label = record.get("label") or f"Equation {formula_id}"
        latex = record.get("latex") or ""
        if display and not match.group(1):
            return f"{label}:\n$$ {latex} $$"
        return f"{label} (${latex}$)"

    expanded = FORMULA_REFERENCE_PATTERN.sub(replace, text)
    expanded = re.sub(r"\b(Equation|Eq\.)\s+Equation\s+", r"\1 ", expanded)
    expanded = re.sub(r"\bEquations\s+Equation\s+", "Equations ", expanded)
    return expanded


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_data_dir()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _truncate(text: str, limit: int = 72) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _clean_label(text: str) -> str:
    text = _expand_formula_references(text or "", display=False)
    text = re.sub(r"\[\[(?:SEE_)?TABLE:[^\]]+\]\]", "", text)
    text = re.sub(r"\$\$[\s\S]*?\$\$", "[formula]", text)
    text = re.sub(r"\$[^$]+\$", "[math]", text)
    return _truncate(text)


def _chapter_node_id(chapter: str) -> str:
    return f"chapter::{chapter}"


def _chapter_label(chapter: str, title: Optional[str]) -> str:
    return title or chapter.replace("_", " ").title()


def _node_payload(
    *,
    node_id: str,
    content: str,
    node_type: str,
    label: str,
    chapter: Optional[str],
    source_file: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = {
        "id": node_id,
        "label": label,
        "chapter": chapter,
        "source": source_file,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "id": node_id,
        "content": content,
        "type": node_type,
        "metadata": metadata,
    }


def _relation_payload(
    relation_id: str,
    source_id: str,
    target_id: str,
    relation_type: str,
    *,
    description: str = "",
    similarity: Optional[float] = None,
    chapter: Optional[str] = None,
    source_file: Optional[str] = None,
) -> Dict[str, Any]:
    metadata = {
        "id": relation_id,
        "description": description,
    }
    if chapter:
        metadata["chapter"] = chapter
    if source_file:
        metadata["source"] = source_file
    return {
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "metadata": metadata,
        "similarity": similarity,
    }


def _resolve_relation_types(nodes: List[Dict[str, Any]], relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Classify relation types; unresolved other relations are folded into related."""
    node_lookup = {str(node.get("id")): node for node in nodes if node.get("id")}
    resolved: List[Dict[str, Any]] = []

    for relation in relations:
        item = dict(relation)
        metadata = dict(item.get("metadata") or {})
        source_id = str(item.get("source_id") or item.get("source") or "")
        target_id = str(item.get("target_id") or item.get("target") or "")
        original_type = str(item.get("relation_type") or item.get("type") or "other")
        relation_type = normalize_relation_type(
            original_type,
            metadata,
            node_lookup.get(source_id),
            node_lookup.get(target_id),
        )
        if relation_type == "other":
            relation_type = "related"
        if relation_type != original_type:
            metadata.setdefault("original_relation_type", original_type)
            metadata.setdefault("relation_inference", "preset_or_other_resolution")
        item["relation_type"] = relation_type
        item["metadata"] = metadata
        resolved.append(item)

    return resolved


def _node_text(node: Dict[str, Any]) -> str:
    metadata = node.get("metadata") or {}
    return " ".join(
        str(part or "")
        for part in (
            metadata.get("label"),
            metadata.get("description"),
            node.get("content"),
            node.get("type"),
        )
    )


def _keywords(text: str) -> Set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_'-]{3,}", text.lower())
    return {word.strip("'") for word in words if word.strip("'") not in SEMANTIC_STOPWORDS}


def _overlap_score(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(min(len(left), len(right)), 1)


def _semantic_relation_for_pair(
    source: Dict[str, Any],
    target: Dict[str, Any],
    source_keywords: Set[str],
    target_keywords: Set[str],
) -> Optional[Tuple[str, float, str]]:
    source_text = _node_text(source).lower()
    target_text = _node_text(target).lower()
    combined = f"{source_text}\n{target_text}"
    overlap = _overlap_score(source_keywords, target_keywords)
    target_type = str(target.get("type") or "").lower()
    source_type = str(source.get("type") or "").lower()

    if any(token in target_text for token in ("in contrast", "however", "whereas", "unlike", "rather than")):
        return "contrasts_with", max(overlap, 0.72), "contrast marker"
    if "example" in target_text or target_text.strip().startswith("example"):
        return "example_of", max(overlap, 0.7), "example marker"
    if any(token in combined for token in ("define", "denote", "called", "means that", "let ")):
        return "defines", max(overlap, 0.64), "definition marker"
    if source_type == "derivation" or target_type == "derivation" or any(token in combined for token in ("derive", "proof", "theorem", "identity", "equation")):
        return "derives", max(overlap, 0.62), "derivation marker"
    if any(token in combined for token in ("depends on", "requires", "based on", "recall", "assume")):
        return "depends_on", max(overlap, 0.6), "dependency marker"
    if any(token in combined for token in ("support", "evidence", "consistent with", "suggest")):
        return "supports", max(overlap, 0.58), "support marker"
    if any(token in combined for token in ("apply", "application", "used to", "use of")):
        return "applies_to", max(overlap, 0.58), "application marker"
    if any(token in combined for token in ("cause", "lead to", "effect of", "resulting in")):
        return "causes", max(overlap, 0.58), "causal marker"
    if overlap >= 0.42:
        return "explains", overlap, "high keyword overlap"
    if overlap >= 0.28:
        return "related", overlap, "moderate keyword overlap"
    return None


def _add_semantic_candidate_relations(spec: SourceSpec) -> None:
    block_nodes = [
        node for node in spec.nodes
        if str(node.get("id") or "").startswith("block::")
    ]
    if len(block_nodes) < 2:
        return

    existing = {
        (
            str(relation.get("source_id") or relation.get("source") or ""),
            str(relation.get("target_id") or relation.get("target") or ""),
            str(relation.get("relation_type") or relation.get("type") or ""),
        )
        for relation in spec.relations
    }
    keyword_map = {str(node.get("id")): _keywords(_node_text(node)) for node in block_nodes}

    for index, source in enumerate(block_nodes):
        source_id = str(source.get("id"))
        candidates: List[Tuple[float, Dict[str, Any], str, str]] = []
        for target in block_nodes[index + 1:index + 7]:
            target_id = str(target.get("id"))
            inferred = _semantic_relation_for_pair(
                source,
                target,
                keyword_map.get(source_id, set()),
                keyword_map.get(target_id, set()),
            )
            if not inferred:
                continue
            relation_type, score, reason = inferred
            if (source_id, target_id, relation_type) in existing:
                continue
            candidates.append((score, target, relation_type, reason))

        for score, target, relation_type, reason in sorted(candidates, key=lambda item: item[0], reverse=True)[:2]:
            target_id = str(target.get("id"))
            metadata = source.get("metadata") or {}
            relation = _relation_payload(
                f"rel::{source_id}::{relation_type}::{target_id}::semantic",
                source_id,
                target_id,
                relation_type,
                description=f"semantic candidate: {reason}",
                similarity=round(score, 4),
                chapter=metadata.get("chapter"),
                source_file=metadata.get("source"),
            )
            relation["metadata"]["relation_source"] = "semantic_candidate"
            relation["metadata"]["relation_inference"] = reason
            spec.relations.append(relation)
            existing.add((source_id, target_id, relation_type))


def _parse_references(text: str) -> Tuple[Set[str], Set[str]]:
    formula_ids: Set[str] = set()
    table_ids: Set[str] = set()
    for _, ref_type, ref_id in REFERENCE_PATTERN.findall(text or ""):
        normalized = ref_id.strip()
        if ref_type == "FORMULA":
            formula_ids.add(normalized)
        elif ref_type == "TABLE":
            table_ids.add(normalized)
    return formula_ids, table_ids


def _build_chunk_source(path: Path) -> SourceSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata") or {}
    chapter = str(metadata.get("chapter") or path.stem.split("_")[0])
    chapter_title = str(metadata.get("section") or metadata.get("source_title") or chapter)
    file_hash = _sha256_file(path)
    source_file = path.name

    nodes: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    previous_block_id: Optional[str] = None

    for index, block in enumerate(payload.get("blocks") or [], start=1):
        block_type = str(block.get("type") or "concept")
        raw_block_content = str(block.get("content") or "")
        block_content = _expand_formula_references(raw_block_content)
        block_id = f"block::{path.stem}::{index}"
        label = f"{chapter} #{index} {block_type}: {_clean_label(block_content)}"
        nodes.append(
            _node_payload(
                node_id=block_id,
                content=block_content,
                node_type=block_type,
                label=label,
                chapter=chapter,
                source_file=source_file,
                extra_metadata={
                    "block_index": index,
                    "source_unit": payload.get("id") or path.stem,
                    "section": metadata.get("section"),
                    "subsections": metadata.get("subsections"),
                    "source_title": metadata.get("source_title"),
                    "source_file_name": metadata.get("source_file"),
                },
            )
        )
        relations.append(
            _relation_payload(
                f"rel::{_chapter_node_id(chapter)}::contains::{block_id}",
                _chapter_node_id(chapter),
                block_id,
                "contains",
                description="chapter contains structured block",
                chapter=chapter,
                source_file=source_file,
            )
        )
        if previous_block_id:
            relations.append(
                _relation_payload(
                    f"rel::{previous_block_id}::precedes::{block_id}",
                    previous_block_id,
                    block_id,
                    "precedes",
                    description="structured block sequence",
                    chapter=chapter,
                    source_file=source_file,
                )
            )

        formula_ids, table_ids = _parse_references(raw_block_content)
        for formula_id in formula_ids:
            formula_node_id = f"formula::{chapter}::{formula_id}"
            relations.append(
                _relation_payload(
                    f"rel::{block_id}::references_formula::{formula_node_id}",
                    block_id,
                    formula_node_id,
                    "references_formula",
                    description=f"block references formula {formula_id}",
                    chapter=chapter,
                    source_file=source_file,
                )
            )
        for table_id in table_ids:
            table_node_id = f"table::{chapter}::{table_id}"
            relations.append(
                _relation_payload(
                    f"rel::{block_id}::references_table::{table_node_id}",
                    block_id,
                    table_node_id,
                    "references_table",
                    description=f"block references table {table_id}",
                    chapter=chapter,
                    source_file=source_file,
                )
            )

        previous_block_id = block_id

    return SourceSpec(
        source_key=f"chunk::{path.name}",
        file_hash=file_hash,
        nodes=nodes,
        relations=relations,
        chapters={chapter: chapter_title},
    )


def _build_formula_source(path: Path) -> SourceSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    file_hash = _sha256_file(path)
    source_file = path.name
    nodes: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    chapters: Dict[str, str] = {}

    for item in payload.get("formulas") or []:
        source = item.get("source") or {}
        chapter = str(source.get("chapter") or "unknown")
        chapter_title = str(source.get("subsection") or chapter)
        chapters.setdefault(chapter, chapter_title)
        formula_id = str(item.get("id"))
        node_id = f"formula::{chapter}::{formula_id}"
        label = str(item.get("label_format") or f"Formula {formula_id}")
        content = str(item.get("latex") or "")
        nodes.append(
            _node_payload(
                node_id=node_id,
                content=content,
                node_type="formula",
                label=label,
                chapter=chapter,
                source_file=source_file,
                extra_metadata={
                    "formula_id": formula_id,
                    "formula_type": item.get("formula_type"),
                    "context": item.get("context"),
                    "description": item.get("description"),
                    "source_unit": source.get("unit_id"),
                    "subsection": source.get("subsection"),
                },
            )
        )
        relations.append(
            _relation_payload(
                f"rel::{_chapter_node_id(chapter)}::contains::{node_id}",
                _chapter_node_id(chapter),
                node_id,
                "contains",
                description="chapter contains formula",
                chapter=chapter,
                source_file=source_file,
            )
        )

    return SourceSpec(
        source_key=f"library::{path.name}",
        file_hash=file_hash,
        nodes=nodes,
        relations=relations,
        chapters=chapters,
    )


def _build_table_source(path: Path) -> SourceSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    file_hash = _sha256_file(path)
    source_file = path.name
    nodes: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    chapters: Dict[str, str] = {}

    for item in payload.get("tables") or []:
        source = item.get("source") or {}
        chapter = str(source.get("chapter") or "unknown")
        chapter_title = str(source.get("subsection") or chapter)
        chapters.setdefault(chapter, chapter_title)
        table_id = str(item.get("id"))
        node_id = f"table::{chapter}::{table_id}"
        label = str(item.get("label_format") or item.get("title") or f"Table {table_id}")
        content = json.dumps(item.get("rows") or item.get("html") or [], ensure_ascii=False)
        nodes.append(
            _node_payload(
                node_id=node_id,
                content=content,
                node_type="note",
                label=_truncate(label, 96),
                chapter=chapter,
                source_file=source_file,
                extra_metadata={
                    "table_id": table_id,
                    "table_type": item.get("table_type"),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "source_unit": source.get("unit_id"),
                    "subsection": source.get("subsection"),
                },
            )
        )
        relations.append(
            _relation_payload(
                f"rel::{_chapter_node_id(chapter)}::contains::{node_id}",
                _chapter_node_id(chapter),
                node_id,
                "contains",
                description="chapter contains table",
                chapter=chapter,
                source_file=source_file,
            )
        )

    return SourceSpec(
        source_key=f"library::{path.name}",
        file_hash=file_hash,
        nodes=nodes,
        relations=relations,
        chapters=chapters,
    )


def _build_chapter_specs(chapters: Dict[str, str]) -> List[SourceSpec]:
    specs: List[SourceSpec] = []
    for chapter, title in sorted(chapters.items()):
        node_id = _chapter_node_id(chapter)
        payload = {
            "chapter": chapter,
            "title": title,
        }
        file_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        specs.append(
            SourceSpec(
                source_key=f"chapter::{chapter}",
                file_hash=file_hash,
                nodes=[
                    _node_payload(
                        node_id=node_id,
                        content=title,
                        node_type="chapter",
                        label=_chapter_label(chapter, title),
                        chapter=chapter,
                        source_file="structured_sync",
                        extra_metadata={"role": "chapter_root", "title": title},
                    )
                ],
                relations=[],
                chapters={chapter: title},
            )
        )
    return specs


def _load_manifest() -> Dict[str, Any]:
    raw = _load_json(MANIFEST_PATH)
    sources = raw.get("sources")
    return {"sources": sources if isinstance(sources, dict) else {}}


def _delete_relation_ids(graph: GraphService, relation_ids: Iterable[str]) -> int:
    deleted = 0
    for relation_id in relation_ids:
        result = graph.delete_relation(relation_id)
        if result.get("success"):
            deleted += 1
    return deleted


def _delete_node_ids(graph: GraphService, node_ids: Iterable[str]) -> int:
    deleted = 0
    for node_id in node_ids:
        result = graph.delete_node(node_id)
        if result.get("success"):
            deleted += 1
    return deleted


def _current_relation_ids(relations: List[Dict[str, Any]]) -> Set[str]:
    relation_ids: Set[str] = set()
    for relation in relations:
        metadata = relation.get("metadata") or {}
        relation_id = metadata.get("id")
        if relation_id:
            relation_ids.add(str(relation_id))
    return relation_ids


def _source_entry(file_hash: str, nodes: List[Dict[str, Any]], relations: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "hash": file_hash,
        "node_ids": [str(node.get("id")) for node in nodes if node.get("id")],
        "relation_ids": sorted(_current_relation_ids(relations)),
        "updated_at": _now(),
    }


def _collect_specs() -> Tuple[List[SourceSpec], Dict[str, str]]:
    specs: List[SourceSpec] = []
    chapters: Dict[str, str] = {}

    for path in sorted(STRUCTURED_DIR.glob("*.json"), key=lambda item: item.name.lower()):
        if path.name == "formula_library.json":
            spec = _build_formula_source(path)
        elif path.name == "table_library.json":
            spec = _build_table_source(path)
        else:
            spec = _build_chunk_source(path)
        specs.append(spec)
        for chapter, title in spec.chapters.items():
            chapters.setdefault(chapter, title)

    chapter_specs = _build_chapter_specs(chapters)
    for spec in specs:
        _add_semantic_candidate_relations(spec)
        spec.relations = _resolve_relation_types(spec.nodes, spec.relations)
    return chapter_specs + specs, chapters


def _normalize_teacher_graph(raw_graph: Dict[str, Any]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    for node in raw_graph.get("nodes", []):
        metadata = node.get("metadata") or {}
        nodes.append(
            {
                "id": node.get("id"),
                "label": metadata.get("label") or node.get("label") or node.get("content") or node.get("id"),
                "type": node.get("type") or metadata.get("type") or "concept",
                "content": node.get("content") or "",
                "chapter": metadata.get("chapter"),
                "source": metadata.get("source"),
                "metadata": metadata,
            }
        )

    for relation in raw_graph.get("relations", []):
        metadata = relation.get("metadata") or {}
        relation_type = relation.get("relation_type") or "related"
        edges.append(
            {
                "id": relation.get("id"),
                "source": relation.get("source_id"),
                "target": relation.get("target_id"),
                "type": relation_type,
                "label": relation_type,
                "title": metadata.get("description") or relation_type,
                "metadata": metadata,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }


def build_teacher_package(graph: Optional[GraphService] = None) -> Dict[str, Any]:
    graph_service = graph or GraphService()
    raw_graph = graph_service.read_graph()
    normalized = _normalize_teacher_graph(raw_graph)
    allowed_node_ids = {
        node["id"]
        for node in normalized["nodes"]
        if node.get("chapter")
        or (node.get("metadata") or {}).get("role") == "chapter_root"
    }
    graph_payload = {
        "nodes": [node for node in normalized["nodes"] if node["id"] in allowed_node_ids],
        "edges": [
            edge
            for edge in normalized["edges"]
            if edge.get("source") in allowed_node_ids and edge.get("target") in allowed_node_ids
        ],
    }
    graph_payload["stats"] = {
        "node_count": len(graph_payload["nodes"]),
        "edge_count": len(graph_payload["edges"]),
    }
    chapter_summary: Dict[str, Dict[str, Any]] = {}

    for node in graph_payload["nodes"]:
        chapter = node.get("chapter") or "unassigned"
        chapter_summary.setdefault(
            chapter,
            {
                "title": chapter,
                "node_ids": [],
                "edge_ids": [],
            },
        )
        chapter_summary[chapter]["node_ids"].append(node["id"])
        if node.get("type") == "chapter":
            chapter_summary[chapter]["title"] = node.get("label") or chapter

    edge_chapters: Dict[str, Set[str]] = {}
    node_chapter_map = {node["id"]: node.get("chapter") or "unassigned" for node in graph_payload["nodes"]}
    for edge in graph_payload["edges"]:
        source_chapter = node_chapter_map.get(edge["source"], "unassigned")
        target_chapter = node_chapter_map.get(edge["target"], "unassigned")
        edge_chapters.setdefault(edge["id"], set()).update({source_chapter, target_chapter})
        for chapter in edge_chapters[edge["id"]]:
            chapter_summary.setdefault(chapter, {"title": chapter, "node_ids": [], "edge_ids": []})
            chapter_summary[chapter]["edge_ids"].append(edge["id"])

    package = {
        "package_type": "teacher_graph_package",
        "generated_at": _now(),
        "graph": graph_payload,
        "chapters": chapter_summary,
    }
    _save_json(TEACHER_PACKAGE_PATH, package)
    return package


def scan_structured_sources(force: bool = False) -> Dict[str, Any]:
    graph = GraphService()
    manifest = _load_manifest()
    previous_sources = manifest.get("sources", {})
    current_sources: Dict[str, Dict[str, Any]] = {}
    specs, chapters = _collect_specs()

    created_sources = 0
    updated_sources = 0
    skipped_sources = 0
    deleted_nodes = 0
    deleted_relations = 0
    imported_nodes = 0
    imported_relations = 0
    changed_files: List[str] = []

    spec_map = {spec.source_key: spec for spec in specs}

    for removed_key in sorted(set(previous_sources.keys()) - set(spec_map.keys())):
        old_entry = previous_sources.get(removed_key) or {}
        deleted_relations += _delete_relation_ids(graph, old_entry.get("relation_ids") or [])
        deleted_nodes += _delete_node_ids(graph, old_entry.get("node_ids") or [])

    for spec in specs:
        current_sources[spec.source_key] = _source_entry(spec.file_hash, spec.nodes, spec.relations)
        previous_entry = previous_sources.get(spec.source_key) or {}
        previous_hash = previous_entry.get("hash")
        if previous_hash == spec.file_hash and not force:
            skipped_sources += 1
            continue

        previous_node_ids = set(previous_entry.get("node_ids") or [])
        previous_relation_ids = set(previous_entry.get("relation_ids") or [])
        current_node_ids = set(current_sources[spec.source_key]["node_ids"])
        current_relation_ids = set(current_sources[spec.source_key]["relation_ids"])

        deleted_relations += _delete_relation_ids(graph, sorted(previous_relation_ids - current_relation_ids))
        deleted_nodes += _delete_node_ids(graph, sorted(previous_node_ids - current_node_ids))

        result = graph.batch_import_graph(spec.nodes, spec.relations)
        imported_nodes += int(result.get("nodes", {}).get("success", 0))
        imported_relations += int(result.get("relations", {}).get("success", 0))
        changed_files.append(spec.source_key)
        if previous_hash is None:
            created_sources += 1
        else:
            updated_sources += 1

    new_manifest = {
        "generated_at": _now(),
        "sources": current_sources,
        "chapters": chapters,
    }
    _save_json(MANIFEST_PATH, new_manifest)
    package = build_teacher_package(graph)

    return {
        "success": True,
        "force": force,
        "created_sources": created_sources,
        "updated_sources": updated_sources,
        "skipped_sources": skipped_sources,
        "deleted_nodes": deleted_nodes,
        "deleted_relations": deleted_relations,
        "imported_nodes": imported_nodes,
        "imported_relations": imported_relations,
        "changed_files": changed_files,
        "chapter_count": len(chapters),
        "package_path": str(TEACHER_PACKAGE_PATH),
        "manifest_path": str(MANIFEST_PATH),
        "package_summary": package.get("graph", {}).get("stats", {}),
    }


def review_search(query: str, limit: int = 10, chapter: Optional[str] = None) -> Dict[str, Any]:
    graph = GraphService()
    lowered = query.strip().lower()
    if chapter:
        hits = []
        for node in graph.read_graph().get("nodes", []):
            metadata = node.get("metadata") or {}
            if metadata.get("chapter") != chapter:
                continue
            haystack = f"{metadata.get('label', '')}\n{node.get('content', '')}".lower()
            if lowered and lowered in haystack:
                hits.append(node)
        hits = hits[:limit]
    else:
        hits = graph.search_nodes(query, limit=limit * 3)[:limit]

    results: List[Dict[str, Any]] = []
    for hit in hits:
        relations = graph.get_relations(node_id=hit["id"], limit=20)
        related: List[Dict[str, Any]] = []
        for relation in relations:
            other_id = relation["target_id"] if relation["source_id"] == hit["id"] else relation["source_id"]
            other_node = graph.get_node(other_id)
            related.append(
                {
                    "relation": relation,
                    "other_node": other_node,
                }
            )
        results.append({"node": hit, "related": related})

    return {
        "success": True,
        "query": query,
        "chapter": chapter,
        "results": results,
    }
