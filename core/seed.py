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


def _graph_node_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT count(*) FROM nodes").fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0] if row else 0)


def ensure_seed_graph() -> None:
    if not _env_flag("APP_BOOTSTRAP_SEED_DATA", True) or not SEED_GRAPH_DB_FILE.exists():
        return

    from KGTS.core.graph_service import _default_db_path
    graph_db = str(_default_db_path())
    if not graph_db:
        return

    target_path = Path(graph_db)
    seed_nodes = _graph_node_count(SEED_GRAPH_DB_FILE)
    target_nodes = _graph_node_count(target_path)
    if seed_nodes <= 0 or target_nodes >= seed_nodes:
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SEED_GRAPH_DB_FILE, target_path)
    print(f"[seed] graph installed: nodes={seed_nodes}, previous_nodes={target_nodes}")


def ensure_seed_runtime() -> None:
    ensure_seed_chapters()
    ensure_seed_graph()
