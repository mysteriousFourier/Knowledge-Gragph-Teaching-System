"""Seed data initialization for fresh deployments."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT_DIR / "data" / "seed"
SEED_CHAPTERS_FILE = SEED_DIR / "chapters.json"
SEED_GRAPH_DB_FILE = SEED_DIR / "knowledge_graph.db"


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _runtime_chapters_file() -> Path:
    return Path(os.getenv("APP_RUNTIME_DIR", str(ROOT_DIR / ".runtime"))) / "chapters.json"


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _exercise_count(chapter: dict[str, Any], key: str) -> int:
    value = chapter.get(key)
    return len(value) if isinstance(value, list) else 0


def _chapter_seed_score(chapter: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        _exercise_count(chapter, "approved_exercise_bank"),
        _exercise_count(chapter, "exercise_bank"),
        len(str(chapter.get("lecture_content") or "")),
        len(str(chapter.get("content") or "")),
    )


def ensure_seed_chapters() -> None:
    if not _env_flag("APP_BOOTSTRAP_SEED_DATA", True) or not SEED_CHAPTERS_FILE.exists():
        return

    seed_payload = _read_json_object(SEED_CHAPTERS_FILE)
    seed_chapters = seed_payload.get("chapters")
    if not isinstance(seed_chapters, dict) or not seed_chapters:
        return

    target_path = _runtime_chapters_file()
    target_payload = _read_json_object(target_path)
    target_chapters = target_payload.get("chapters")
    if not isinstance(target_chapters, dict):
        target_chapters = {}

    changed = False
    for chapter_id, seed_chapter in seed_chapters.items():
        if not isinstance(seed_chapter, dict):
            continue
        current_chapter = target_chapters.get(chapter_id)
        if not isinstance(current_chapter, dict):
            target_chapters[chapter_id] = seed_chapter
            changed = True

    if not changed:
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps({"chapters": target_chapters}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[seed] chapters installed: {len(seed_chapters)} chapter(s)")


def _graph_chapter_tree_health(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        return {
            "nodes": 0,
            "chapter_roots": 0,
            "contains": 0,
            "toc_root": 0,
            "heading_sections": 0,
            "chapter_heading_edges": 0,
            "legacy_toc_block_edges": 0,
            "legacy_chapter_toc_section_edges": 0,
        }
    try:
        with sqlite3.connect(str(db_path)) as conn:
            nodes = int(conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])
            chapter_roots = int(
                conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE type = 'chapter' AND id LIKE 'chapter::chapter%'"
                ).fetchone()[0]
            )
            contains = int(
                conn.execute(
                    "SELECT COUNT(*) FROM relationships WHERE type = 'contains'"
                ).fetchone()[0]
            )
            toc_root = int(
                conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE id = 'toc::root'"
                ).fetchone()[0]
            )
            heading_sections = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM nodes
                    WHERE type = 'section'
                      AND json_extract(metadata_json, '$.role') = 'heading'
                    """
                ).fetchone()[0]
            )
            chapter_heading_edges = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM relationships AS rel
                    JOIN nodes AS node ON node.id = rel.target_node
                    WHERE rel.type = 'contains'
                      AND rel.source_node LIKE 'chapter::chapter%'
                      AND node.type = 'section'
                      AND json_extract(node.metadata_json, '$.role') = 'heading'
                    """
                ).fetchone()[0]
            )
            legacy_toc_block_edges = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM relationships
                    WHERE type = 'contains'
                      AND source_node LIKE 'toc::%'
                      AND target_node LIKE 'block::%'
                    """
                ).fetchone()[0]
            )
            legacy_chapter_toc_section_edges = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM relationships AS rel
                    JOIN nodes AS node ON node.id = rel.target_node
                    WHERE rel.type = 'contains'
                      AND rel.source_node LIKE 'chapter::chapter%'
                      AND rel.target_node LIKE 'toc::%'
                      AND node.type = 'section'
                      AND json_extract(node.metadata_json, '$.toc_entry_type') IN ('section', 'subsection')
                    """
                ).fetchone()[0]
            )
    except sqlite3.Error:
        return {
            "nodes": 0,
            "chapter_roots": 0,
            "contains": 0,
            "toc_root": 0,
            "heading_sections": 0,
            "chapter_heading_edges": 0,
            "legacy_toc_block_edges": 0,
            "legacy_chapter_toc_section_edges": 0,
        }
    return {
        "nodes": nodes,
        "chapter_roots": chapter_roots,
        "contains": contains,
        "toc_root": toc_root,
        "heading_sections": heading_sections,
        "chapter_heading_edges": chapter_heading_edges,
        "legacy_toc_block_edges": legacy_toc_block_edges,
        "legacy_chapter_toc_section_edges": legacy_chapter_toc_section_edges,
    }


def _target_graph_needs_seed(seed_path: Path, target_path: Path) -> tuple[bool, dict[str, int], dict[str, int]]:
    seed = _graph_chapter_tree_health(seed_path)
    target = _graph_chapter_tree_health(target_path)
    if seed["nodes"] <= 0:
        return False, seed, target
    if target["nodes"] <= 0:
        return True, seed, target
    if seed["toc_root"] and not target["toc_root"]:
        return True, seed, target
    if target["chapter_roots"] < min(seed["chapter_roots"], 30):
        return True, seed, target
    if seed.get("heading_sections", 0) and target.get("heading_sections", 0) < max(1, int(seed["heading_sections"] * 0.9)):
        return True, seed, target
    if seed.get("chapter_heading_edges", 0) and target.get("chapter_heading_edges", 0) < max(1, int(seed["chapter_heading_edges"] * 0.9)):
        return True, seed, target
    if target["contains"] < max(1, int(seed["contains"] * 0.8)):
        return True, seed, target
    if not seed["toc_root"] and target["nodes"] < seed["nodes"]:
        return True, seed, target
    return False, seed, target


def _merge_seed_graph(seed_path: Path, target_path: Path) -> None:
    with sqlite3.connect(str(seed_path)) as seed_conn, sqlite3.connect(str(target_path)) as target_conn:
        for table in ("nodes", "relationships"):
            columns = [row[1] for row in seed_conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if not columns:
                continue
            column_sql = ", ".join(columns)
            placeholders = ", ".join("?" for _ in columns)
            rows = seed_conn.execute(f"SELECT {column_sql} FROM {table}").fetchall()
            target_conn.executemany(
                f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
                rows,
            )
        target_conn.commit()


def _cleanup_legacy_toc_content_edges(target_path: Path) -> dict[str, int]:
    if not target_path.exists():
        return {"toc_block_edges_deleted": 0, "chapter_toc_section_edges_deleted": 0}
    with sqlite3.connect(str(target_path)) as conn:
        toc_block_cursor = conn.execute(
            """
            DELETE FROM relationships
            WHERE type = 'contains'
              AND source_node LIKE 'toc::%'
              AND target_node LIKE 'block::%'
              AND EXISTS (
                  SELECT 1
                  FROM relationships AS heading_rel
                  JOIN nodes AS heading_node ON heading_node.id = heading_rel.source_node
                  WHERE heading_rel.type = 'contains'
                    AND heading_rel.target_node = relationships.target_node
                    AND heading_node.type = 'section'
                    AND json_extract(heading_node.metadata_json, '$.role') = 'heading'
              )
            """
        )
        chapter_toc_cursor = conn.execute(
            """
            DELETE FROM relationships
            WHERE type = 'contains'
              AND source_node LIKE 'chapter::chapter%'
              AND target_node LIKE 'toc::%'
              AND EXISTS (
                  SELECT 1
                  FROM nodes AS toc_node
                  WHERE toc_node.id = relationships.target_node
                    AND toc_node.type = 'section'
                    AND json_extract(toc_node.metadata_json, '$.toc_entry_type') IN ('section', 'subsection')
              )
              AND EXISTS (
                  SELECT 1
                  FROM relationships AS heading_rel
                  JOIN nodes AS heading_node ON heading_node.id = heading_rel.target_node
                  WHERE heading_rel.type = 'contains'
                    AND heading_rel.source_node = relationships.source_node
                    AND heading_node.type = 'section'
                    AND json_extract(heading_node.metadata_json, '$.role') = 'heading'
              )
            """
        )
        conn.commit()
    return {
        "toc_block_edges_deleted": max(int(toc_block_cursor.rowcount or 0), 0),
        "chapter_toc_section_edges_deleted": max(int(chapter_toc_cursor.rowcount or 0), 0),
    }


def ensure_seed_graph() -> None:
    if not _env_flag("APP_BOOTSTRAP_SEED_DATA", True) or not SEED_GRAPH_DB_FILE.exists():
        return

    from KGTS.core.graph_service import _default_db_path
    graph_db = str(_default_db_path())
    if not graph_db:
        return

    target_path = Path(graph_db)
    needs_seed, seed_health, target_health = _target_graph_needs_seed(SEED_GRAPH_DB_FILE, target_path)
    if not needs_seed:
        cleanup = _cleanup_legacy_toc_content_edges(target_path)
        if cleanup["toc_block_edges_deleted"] or cleanup["chapter_toc_section_edges_deleted"]:
            print(f"[seed] cleaned legacy graph edges: {cleanup}")
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists() or target_health["nodes"] <= 0:
        shutil.copy2(SEED_GRAPH_DB_FILE, target_path)
        action = "installed"
    else:
        _merge_seed_graph(SEED_GRAPH_DB_FILE, target_path)
        action = "merged"
    cleanup = _cleanup_legacy_toc_content_edges(target_path)
    print(
        "[seed] graph "
        f"{action}: nodes={seed_health['nodes']}, chapter_roots={seed_health['chapter_roots']}, "
        f"contains={seed_health['contains']}, heading_sections={seed_health.get('heading_sections')}, "
        f"cleanup={cleanup}, previous={target_health}"
    )


def ensure_seed_runtime() -> None:
    ensure_seed_chapters()
    ensure_seed_graph()
