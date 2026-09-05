"""File-backed course catalog for course-scoped education records."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from KGTS.core.bridge import RUNTIME_DIR

COURSES_FILE = RUNTIME_DIR / "courses.json"


def _now() -> str:
    return datetime.now().isoformat()


def _safe_course_id(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff_-]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-_")[:72]


class CourseStore:
    def __init__(self, path: Path = COURSES_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        courses = payload.get("courses") if isinstance(payload, dict) else None
        return courses if isinstance(courses, dict) else {}

    def _save(self, courses: Dict[str, Dict[str, Any]]) -> None:
        payload = json.dumps({"courses": courses}, ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Replace the catalog atomically so a restart cannot observe a partial JSON file.
        fd, temp_name = tempfile.mkstemp(prefix=f"{self.path.stem}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def create(self, *, title: str, description: str = "", course_id: Optional[str] = None) -> Dict[str, Any]:
        clean_title = str(title or "").strip()
        if not clean_title:
            raise ValueError("课程名称不能为空")
        courses = self._load()
        base = _safe_course_id(course_id) or _safe_course_id(clean_title) or f"course-{uuid.uuid4().hex[:8]}"
        candidate = f"course_{base}" if not base.startswith("course_") else base
        if candidate in courses:
            candidate = f"{candidate}_{uuid.uuid4().hex[:6]}"
        now = _now()
        record = {"id": candidate, "title": clean_title, "description": str(description or "").strip(), "created_at": now, "updated_at": now}
        courses[candidate] = record
        self._save(courses)
        return record

    def list(self) -> List[Dict[str, Any]]:
        records = [dict(item) for item in self._load().values() if isinstance(item, dict)]
        return sorted(records, key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    def get(self, course_id: str) -> Optional[Dict[str, Any]]:
        value = self._load().get(str(course_id or "").strip())
        return dict(value) if isinstance(value, dict) else None

    def update(self, course_id: str, *, title: Optional[str] = None, description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        courses = self._load()
        record = courses.get(str(course_id or "").strip())
        if not isinstance(record, dict):
            return None
        if title is not None:
            clean_title = str(title).strip()
            if not clean_title:
                raise ValueError("课程名称不能为空")
            record["title"] = clean_title
        if description is not None:
            record["description"] = str(description).strip()
        record["updated_at"] = _now()
        self._save(courses)
        return dict(record)

    def delete(self, course_id: str) -> bool:
        courses = self._load()
        key = str(course_id or "").strip()
        if key not in courses:
            return False
        courses.pop(key)
        self._save(courses)
        return True


course_store = CourseStore()
