"""Source builders for structured sync."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from KGTS.core.graph_service import normalize_relation_type

from KGTS.maintenance.sync_utils import (
    SourceSpec,
    STRUCTURED_DIR,
    _chapter_label,
    _chapter_node_id,
    _clean_label,
    _expand_formula_references,
    _node_payload,
    _parse_references,
    _relation_payload,
    _sha256_file,
)


def _semantic_relation_for_pair(
    source: Dict[str, Any],
    target: Dict[str, Any],
    source_keywords: set[str],
    target_keywords: set[str],
) -> Optional[tuple[str, float, str]]:
    from KGTS.maintenance.sync_utils import _node_text, _overlap_score

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
    from KGTS.maintenance.sync_utils import _keywords

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
        candidates: list[tuple[float, Dict[str, Any], str, str]] = []
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


def _resolve_relation_types(nodes: List[Dict[str, Any]], relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        from KGTS.maintenance.sync_utils import _truncate
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


def _collect_specs() -> tuple[List[SourceSpec], Dict[str, str]]:
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
