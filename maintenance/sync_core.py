"""Core sync logic for structured sync."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from KGTS.maintenance.sync_builders import _collect_specs
from KGTS.maintenance.sync_utils import (
    SourceSpec,
    MANIFEST_PATH,
    TEACHER_PACKAGE_PATH,
    _chapter_node_id,
    _ensure_data_dir,
    _load_json,
    _now,
    _relation_payload,
    _save_json,
    _sha256_file,
)


def scan_structured_sources(
    *,
    force: bool = False,
    dry_run: bool = False,
    skip_semantic: bool = False,
) -> Dict[str, Any]:
    """Scan structured directory, build specs, and optionally persist."""
    specs, chapters = _collect_specs()
    new_hashes = {spec.source_key: spec.file_hash for spec in specs}
    manifest = _load_json(MANIFEST_PATH)
    old_hashes = manifest.get("hashes") or {}
    changed = list(new_hashes) if force else [
        key for key in new_hashes if old_hashes.get(key) != new_hashes[key]
    ]
    unchanged = [key for key in new_hashes if key not in changed]
    removed = [key for key in old_hashes if key not in new_hashes]

    if dry_run:
        return {
            "dry_run": True,
            "changed": changed,
            "unchanged": unchanged,
            "removed": removed,
            "chapters": list(chapters.keys()),
        }

    _ensure_data_dir()
    _save_json(
        MANIFEST_PATH,
        {
            "last_sync": _now(),
            "hashes": new_hashes,
            "chapters": chapters,
        },
    )

    all_nodes: List[Dict[str, Any]] = []
    all_relations: List[Dict[str, Any]] = []
    for spec in specs:
        all_nodes.extend(spec.nodes)
        all_relations.extend(spec.relations)

    _save_json(
        TEACHER_PACKAGE_PATH,
        {
            "last_sync": _now(),
            "chapters": chapters,
            "nodes": all_nodes,
            "relations": all_relations,
        },
    )

    return {
        "success": True,
        "last_sync": _now(),
        "changed": changed,
        "unchanged": unchanged,
        "removed": removed,
        "chapters": list(chapters.keys()),
        "total_nodes": len(all_nodes),
        "total_relations": len(all_relations),
    }


def build_teacher_package(
    *,
    filter_chapters: Optional[List[str]] = None,
    filter_node_types: Optional[List[str]] = None,
    include_formulas: bool = True,
    include_tables: bool = True,
    include_semantic: bool = True,
    min_similarity: Optional[float] = None,
    max_nodes: Optional[int] = None,
    max_relations: Optional[int] = None,
    include_chapter_relations: bool = True,
    include_block_relations: bool = True,
) -> Dict[str, Any]:
    """Build teacher package with optional filtering."""
    manifest = _load_json(MANIFEST_PATH)
    if not manifest:
        return {
            "success": False,
            "error": "Manifest not found. Run scan_structured_sources first.",
        }

    package = _load_json(TEACHER_PACKAGE_PATH)
    if not package:
        return {
            "success": False,
            "error": "Teacher package not found. Run scan_structured_sources first.",
        }

    nodes = list(package.get("nodes") or [])
    relations = list(package.get("relations") or [])
    chapters = dict(package.get("chapters") or {})

    if filter_chapters:
        allowed = set(filter_chapters)
        nodes = [
            node for node in nodes
            if str((node.get("metadata") or {}).get("chapter") or "") in allowed
        ]
        relations = [
            relation for relation in relations
            if str((relation.get("metadata") or {}).get("chapter") or "") in allowed
        ]

    if filter_node_types:
        allowed = set(filter_node_types)
        nodes = [node for node in nodes if str(node.get("type") or "") in allowed]

    if not include_formulas:
        nodes = [node for node in nodes if str(node.get("type") or "") != "formula"]
        relations = [
            relation for relation in relations
            if str(relation.get("relation_type") or "") != "references_formula"
        ]

    if not include_tables:
        nodes = [node for node in nodes if str(node.get("type") or "") != "note"]
        relations = [
            relation for relation in relations
            if str(relation.get("relation_type") or "") != "references_table"
        ]

    if not include_semantic:
        relations = [
            relation for relation in relations
            if str((relation.get("metadata") or {}).get("relation_source") or "") != "semantic_candidate"
        ]

    if min_similarity is not None:
        relations = [
            relation for relation in relations
            if (relation.get("similarity") or 1.0) >= min_similarity
        ]

    if not include_chapter_relations:
        relations = [
            relation for relation in relations
            if str(relation.get("relation_type") or "") != "contains"
        ]

    if not include_block_relations:
        relations = [
            relation for relation in relations
            if str(relation.get("relation_type") or "") != "precedes"
        ]

    if max_nodes is not None and len(nodes) > max_nodes:
        nodes = nodes[:max_nodes]
    if max_relations is not None and len(relations) > max_relations:
        relations = relations[:max_relations]

    return {
        "success": True,
        "last_sync": package.get("last_sync"),
        "chapters": chapters,
        "total_nodes": len(nodes),
        "total_relations": len(relations),
        "nodes": nodes,
        "relations": relations,
    }


def review_search(
    query: str,
    *,
    top_k: int = 5,
    include_formulas: bool = True,
    include_tables: bool = True,
    include_blocks: bool = True,
    min_similarity: float = 0.0,
) -> Dict[str, Any]:
    """Search within the teacher package."""
    package = _load_json(TEACHER_PACKAGE_PATH)
    if not package:
        return {
            "success": False,
            "error": "Teacher package not found. Run scan_structured_sources first.",
        }

    from KGTS.maintenance.sync_utils import _keywords, _overlap_score

    query_keywords = _keywords(query)
    nodes = list(package.get("nodes") or [])
    relations = list(package.get("relations") or [])

    if not include_formulas:
        nodes = [node for node in nodes if str(node.get("type") or "") != "formula"]
    if not include_tables:
        nodes = [node for node in nodes if str(node.get("type") or "") != "note"]
    if not include_blocks:
        nodes = [node for node in nodes if not str(node.get("id") or "").startswith("block::")]

    scored_nodes: List[tuple[float, Dict[str, Any]]] = []
    for node in nodes:
        node_keywords = _keywords(_node_text(node))
        score = _overlap_score(query_keywords, node_keywords)
        if score >= min_similarity:
            scored_nodes.append((score, node))

    scored_nodes.sort(key=lambda item: item[0], reverse=True)
    top_nodes = scored_nodes[:top_k]
    node_ids = {str(node.get("id")) for _, node in top_nodes}

    related_relations = [
        relation for relation in relations
        if str(relation.get("source_id") or relation.get("source") or "") in node_ids
        or str(relation.get("target_id") or relation.get("target") or "") in node_ids
    ]

    return {
        "success": True,
        "query": query,
        "total_matches": len(top_nodes),
        "nodes": [node for _, node in top_nodes],
        "relations": related_relations,
    }


def _node_text(node: Dict[str, Any]) -> str:
    from KGTS.maintenance.sync_utils import _node_text as _orig
    return _orig(node)
