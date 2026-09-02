from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from KGTS.core.bridge import chapter_store
from KGTS.education.courseware_editor import list_courseware_projects, load_courseware_project, save_courseware_project
from KGTS.education.router import _render_courseware_pdf_pages


def _save_chapter_with_render(chapter: dict[str, Any], rendered_pages: list[dict[str, Any]], render_error: str) -> None:
    chapter_store.save_chapter(
        title=str(chapter.get("title") or "未命名课件"),
        content=chapter.get("content"),
        graph_data=chapter.get("graph_data"),
        chapter_id=chapter.get("id"),
        source_type=chapter.get("source_type"),
        source_node_ids=chapter.get("source_node_ids"),
        source_scope=chapter.get("source_scope"),
        ppt_slides=chapter.get("ppt_slides"),
        slide_lectures=chapter.get("slide_lectures"),
        tex_content=chapter.get("tex_content"),
        editable_model=chapter.get("editable_model"),
        asset_map=chapter.get("asset_map"),
        rendered_pages=rendered_pages,
        render_source="latex" if rendered_pages else chapter.get("render_source"),
        render_error=render_error,
        ppt_artifact=chapter.get("ppt_artifact"),
        ppt_source_node_ids=chapter.get("ppt_source_node_ids"),
        lecture_source_node_ids=chapter.get("lecture_source_node_ids"),
        lecture_target_duration_minutes=chapter.get("lecture_target_duration_minutes"),
        lecture_speech_rate_cpm=chapter.get("lecture_speech_rate_cpm"),
        lecture_pacing=chapter.get("lecture_pacing"),
    )


def _save_project_with_render(project: dict[str, Any], rendered_pages: list[dict[str, Any]], render_error: str) -> None:
    save_courseware_project(
        {
            "project_id": project.get("id"),
            "title": project.get("title"),
            "editable_model": project.get("editable_model") or {},
            "asset_map": project.get("asset_map") or {},
            "slides": project.get("slides") or [],
            "tex_content": project.get("tex_content") or "",
            "rendered_pages": rendered_pages,
            "render_source": "latex" if rendered_pages else project.get("render_source"),
            "render_error": render_error,
            "ppt_artifact": project.get("ppt_artifact"),
            "source_node_ids": project.get("source_node_ids") or [],
        }
    )


def _backfill_chapters(*, force: bool = False, remaining: int = 0) -> int:
    chapters = chapter_store.list_chapters()
    updated = 0
    for chapter in chapters:
        chapter_id = str(chapter.get("id") or "")
        title = str(chapter.get("title") or chapter_id or "未命名课件")
        tex_content = str(chapter.get("tex_content") or "").strip()
        existing_pages = chapter.get("rendered_pages") or []
        if not tex_content:
            print(f"skip no-tex {chapter_id} {title}")
            continue
        if existing_pages and not force:
            print(f"skip rendered {chapter_id} {title} pages={len(existing_pages)}")
            continue

        print(f"render {chapter_id} {title}")
        rendered_pages, render_error = _render_courseware_pdf_pages(
            tex_content,
            chapter.get("asset_map"),
            namespace=f"chapter-{chapter_id}",
        )
        if rendered_pages:
            print(f"save rendered {chapter_id} pages={len(rendered_pages)}")
        else:
            print(f"save render-error {chapter_id}: {render_error}")
        _save_chapter_with_render(chapter, rendered_pages, render_error)
        updated += 1
        if remaining and updated >= remaining:
            break
    return updated


def _backfill_projects(*, force: bool = False, remaining: int = 0) -> int:
    updated = 0
    for summary in list_courseware_projects():
        project_id = str(summary.get("id") or "")
        project = load_courseware_project(project_id) if project_id else None
        if not isinstance(project, dict):
            continue
        title = str(project.get("title") or project_id or "未命名课件")
        tex_content = str(project.get("tex_content") or "").strip()
        existing_pages = project.get("rendered_pages") or []
        if not tex_content:
            print(f"skip project no-tex {project_id} {title}")
            continue
        if existing_pages and not force:
            print(f"skip project rendered {project_id} {title} pages={len(existing_pages)}")
            continue

        print(f"render project {project_id} {title}")
        rendered_pages, render_error = _render_courseware_pdf_pages(
            tex_content,
            project.get("asset_map"),
            namespace=f"project-{project_id}",
        )
        if rendered_pages:
            print(f"save project rendered {project_id} pages={len(rendered_pages)}")
        else:
            print(f"save project render-error {project_id}: {render_error}")
        _save_project_with_render(project, rendered_pages, render_error)
        updated += 1
        if remaining and updated >= remaining:
            break
    return updated


def backfill(*, force: bool = False, limit: int = 0) -> int:
    chapter_limit = limit if limit else 0
    updated = _backfill_chapters(force=force, remaining=chapter_limit)
    if limit and updated >= limit:
        return updated
    project_limit = max(0, limit - updated) if limit else 0
    updated += _backfill_projects(force=force, remaining=project_limit)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill compiled PDF page renders for saved courseware chapters.")
    parser.add_argument("--force", action="store_true", help="Re-render chapters that already have rendered_pages.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of chapters to update.")
    args = parser.parse_args()
    updated = backfill(force=args.force, limit=max(0, args.limit))
    print(f"updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
