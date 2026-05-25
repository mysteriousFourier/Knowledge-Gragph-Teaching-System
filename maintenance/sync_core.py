"""Core sync logic for structured sync."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
from pathlib import Path
from unittest.mock import patch

from KGTS.maintenance.sync_builders import _collect_specs
from KGTS.maintenance.sync_utils import (
    SourceSpec,
    PROJECT_ROOT,
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


CANONICAL_CHAPTER_IDS = [f"chapter::chapter{index}" for index in range(1, 31)]


def _cleanup_source_for_key(source_key: str) -> str:
    prefix, separator, source_name = str(source_key or "").partition("::")
    if not separator:
        return ""
    if prefix in {"chunk", "library", "toc"}:
        return source_name.strip()
    if prefix == "chapter":
        return "structured_sync"
    return ""


def scan_structured_sources(
    *,
    force: bool = False,
    dry_run: bool = False,
    skip_semantic: bool = False,
    import_graph: bool = True,
) -> Dict[str, Any]:
    """Scan structured directory, build specs, and optionally persist."""
    specs, chapters = _collect_specs(skip_semantic=skip_semantic)
    new_hashes = {spec.source_key: spec.file_hash for spec in specs}
    manifest = _load_json(MANIFEST_PATH)
    old_hashes = manifest.get("hashes") or {}
    changed = list(new_hashes.keys()) if force else [key for key in new_hashes if old_hashes.get(key) != new_hashes[key]]
    unchanged = [] if force else [key for key in new_hashes if key not in changed]
    removed = [key for key in old_hashes if key not in new_hashes]

    if dry_run:
        return {
            "dry_run": True,
            "changed": changed,
            "unchanged": unchanged,
            "removed": removed,
            "chapters": list(chapters.keys()),
            "import_graph": import_graph,
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

    graph_import: Optional[Dict[str, Any]] = None
    if import_graph:
        from KGTS.core.bridge import call_backend_tool, import_graph_payload

        cleanup_sources = {
            str((node.get("metadata") or {}).get("source") or "")
            for node in all_nodes
        }
        cleanup_sources.update(_cleanup_source_for_key(key) for key in removed)
        cleanup_sources.add("structured_sync")
        cleanup_sources.discard("")
        graph_cleanup = call_backend_tool(
            "delete_by_sources",
            {"sources": sorted(cleanup_sources)},
        )

        graph_import = import_graph_payload(
            {
                "nodes": all_nodes,
                "relations": all_relations,
            }
        )
        graph_import["cleanup"] = graph_cleanup

    result = {
        "success": True,
        "last_sync": _now(),
        "changed": changed,
        "unchanged": unchanged,
        "removed": removed,
        "chapters": list(chapters.keys()),
        "total_nodes": len(all_nodes),
        "total_relations": len(all_relations),
        "package_summary": {
            "node_count": len(all_nodes),
            "edge_count": len(all_relations),
            "chapter_count": len(chapters),
        },
    }
    if graph_import is not None:
        result["graph_import"] = graph_import
    return result


def rebuild_staging_graph(
    *,
    toc_export_dir: str | Path | None = None,
    skip_semantic: bool = False,
    rebuild_vector: bool = True,
) -> Dict[str, Any]:
    """Build a staging graph DB/vector index without replacing production graph data."""
    staging_dir = PROJECT_ROOT / ".runtime" / "staging"
    graph_db_path = staging_dir / "knowledge_graph.db"
    vector_index_dir = staging_dir / "vector_index"
    manifest_path = staging_dir / "structured_sync_manifest.json"
    package_path = staging_dir / "teacher_memory_package.json"
    staging_dir.mkdir(parents=True, exist_ok=True)

    from KGTS.maintenance import sync_builders

    effective_toc_dir = Path(toc_export_dir) if toc_export_dir is not None else Path(os.getenv("KGTS_TOC_EXPORT_DIR", ""))
    source_patches = [
        patch.object(sync_builders, "TOC_EXPORT_DIR", effective_toc_dir),
        patch("KGTS.maintenance.sync_core.MANIFEST_PATH", manifest_path),
        patch("KGTS.maintenance.sync_core.TEACHER_PACKAGE_PATH", package_path),
        patch("KGTS.maintenance.sync_core._ensure_data_dir", lambda: staging_dir.mkdir(parents=True, exist_ok=True)),
    ]
    with source_patches[0], source_patches[1], source_patches[2], source_patches[3]:
        dry_run = scan_structured_sources(
            force=True,
            dry_run=True,
            skip_semantic=skip_semantic,
            import_graph=False,
        )
        persisted = scan_structured_sources(
            force=True,
            dry_run=False,
            skip_semantic=skip_semantic,
            import_graph=False,
        )

    package = _load_json(package_path)
    nodes = list(package.get("nodes") or [])
    relations = list(package.get("relations") or [])

    if graph_db_path.exists():
        graph_db_path.unlink()

    from KGTS.core.graph_service import GraphService

    graph = GraphService(db_path=graph_db_path)
    import_result = graph.batch_import_graph(nodes, relations)
    graph_stats = _sqlite_graph_stats(graph_db_path)

    vector_stats: Dict[str, Any] = {"enabled": False, "skipped": not rebuild_vector}
    if rebuild_vector:
        with patch.dict(
            os.environ,
            {
                "KGTS_RETRIEVAL_MODE": "hybrid",
                "KGTS_VECTOR_INDEX_DIR": str(vector_index_dir),
            },
        ):
            vector_graph = GraphService(db_path=graph_db_path)
            vector_stats = vector_graph.rebuild_vector_index()

    checks = _staging_checks(graph_db_path, package_path, vector_stats)
    return {
        "success": True,
        "staging": True,
        "paths": {
            "staging_dir": str(staging_dir),
            "graph_db": str(graph_db_path),
            "vector_index_dir": str(vector_index_dir),
            "manifest": str(manifest_path),
            "teacher_package": str(package_path),
        },
        "toc_export_dir": str(effective_toc_dir) if str(effective_toc_dir) else "",
        "dry_run": dry_run,
        "sync": persisted,
        "import_graph": import_result,
        "graph_stats": graph_stats,
        "vector_stats": vector_stats,
        "checks": checks,
        "message": "Staging graph rebuilt. Production graph DB and teacher chapter store were not replaced.",
    }


def _sqlite_graph_stats(db_path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        relation_count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        toc_count = conn.execute("SELECT COUNT(*) FROM nodes WHERE id LIKE 'toc::%'").fetchone()[0]
        raw_toc_chapter_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM nodes
            WHERE id LIKE 'toc::%'
              AND json_extract(metadata_json, '$.toc_entry_type') = 'chapter'
            """
        ).fetchone()[0]
        canonical_chapter_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM nodes
            WHERE type = 'chapter'
              AND id LIKE 'chapter::chapter%'
            """
        ).fetchone()[0]
        node_types = {
            str(row[0]): int(row[1])
            for row in conn.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type").fetchall()
        }
        relation_types = {
            str(row[0]): int(row[1])
            for row in conn.execute("SELECT type, COUNT(*) FROM relationships GROUP BY type").fetchall()
        }
        sample_mappings = {
            chapter: conn.execute(
                """
                SELECT source_node
                FROM relationships
                WHERE target_node = ?
                  AND type = 'contains'
                ORDER BY source_node
                LIMIT 1
                """,
                (f"block::{chapter}_001::1",),
            ).fetchone()
            for chapter in ("chapter1", "chapter5", "chapter26")
        }
        return {
            "nodes": node_count,
            "relations": relation_count,
            "toc_nodes": toc_count,
            "toc_raw_entry_type_chapters": raw_toc_chapter_count,
            "canonical_chapter_nodes": canonical_chapter_count,
            "node_types": node_types,
            "relation_types": relation_types,
            "sample_mappings": {
                chapter: (row[0] if row else None)
                for chapter, row in sample_mappings.items()
            },
        }
    finally:
        conn.close()


def _staging_checks(db_path: Path, package_path: Path, vector_stats: Dict[str, Any]) -> Dict[str, Any]:
    package = _load_json(package_path)
    package_chapters = {
        str(chapter or "")
        for chapter in (package.get("chapters") or {}).keys()
        if str(chapter or "").startswith("chapter")
    }
    conn = sqlite3.connect(str(db_path))
    try:
        total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        toc_nodes = conn.execute("SELECT COUNT(*) FROM nodes WHERE id LIKE 'toc::%'").fetchone()[0]
        canonical_rows = conn.execute(
            """
            SELECT id
            FROM nodes
            WHERE type = 'chapter'
              AND id LIKE 'chapter::chapter%'
            """
        ).fetchall()
        canonical_chapter_ids = {str(row[0]) for row in canonical_rows}
        missing_canonical_chapters = [
            chapter_id for chapter_id in CANONICAL_CHAPTER_IDS
            if chapter_id not in canonical_chapter_ids
        ]
        chapter_attachment_counts = {
            chapter_id: int(count)
            for chapter_id, count in conn.execute(
                """
                SELECT source_node, COUNT(*)
                FROM relationships
                WHERE type = 'contains'
                  AND source_node IN ({})
                GROUP BY source_node
                """.format(",".join("?" for _ in CANONICAL_CHAPTER_IDS)),
                CANONICAL_CHAPTER_IDS,
            ).fetchall()
        }
        chapters_without_contains = [
            chapter_id for chapter_id in CANONICAL_CHAPTER_IDS
            if chapter_attachment_counts.get(chapter_id, 0) <= 0
        ]
        raw_toc_chapter_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM nodes
            WHERE id LIKE 'toc::%'
              AND json_extract(metadata_json, '$.toc_entry_type') = 'chapter'
            """
        ).fetchone()[0]
        toc_chapter_store_entries = 0
        chapters_path = PROJECT_ROOT / ".runtime" / "chapters.json"
        if chapters_path.exists():
            try:
                chapter_payload = json.loads(chapters_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                chapter_payload = {}
            chapters = chapter_payload.get("chapters")
            if isinstance(chapters, dict):
                toc_chapter_store_entries = sum(
                    1
                    for key, value in chapters.items()
                    if str(key).startswith("chapter::toc_")
                    or (
                        isinstance(value, dict)
                        and (
                            str(value.get("id") or "").startswith("chapter::toc_")
                            or str(value.get("source") or "").lower().endswith("_toc_tree.json")
                        )
                    )
                )
        vector_size = int(vector_stats.get("index_size") or 0)
        return {
            "structured_regular_chapter_count": len(package_chapters),
            "structured_regular_chapters": sorted(package_chapters, key=lambda item: int(item.replace("chapter", "") or "0")),
            "structured_regular_chapters_complete_1_to_30": package_chapters == {f"chapter{index}" for index in range(1, 31)},
            "canonical_chapter_node_count": len(canonical_chapter_ids),
            "canonical_chapters_complete_1_to_30": not missing_canonical_chapters,
            "missing_canonical_chapters": missing_canonical_chapters,
            "chapters_without_contains": chapters_without_contains,
            "toc_raw_entry_type_chapter_count": raw_toc_chapter_count,
            "toc_nodes_present": toc_nodes > 0,
            "toc_node_count": toc_nodes,
            "teacher_chapter_store_toc_entries": toc_chapter_store_entries,
            "vector_covers_all_nodes": bool(vector_size) and vector_size == total_nodes,
            "vector_index_size": vector_size,
            "graph_node_count": total_nodes,
            "package_exists": package_path.exists(),
        }
    finally:
        conn.close()


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
