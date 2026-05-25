"""Utility functions for structured sync."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class SourceSpec:
    source_key: str
    file_hash: str
    nodes: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    chapters: Dict[str, str]


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STRUCTURED_DIR = Path(os.getenv("KGTS_STRUCTURED_DIR", str(PROJECT_ROOT / "structured")))
TOC_EXPORT_DIR = Path(os.getenv("KGTS_TOC_EXPORT_DIR", ""))
DATA_DIR = Path(os.getenv("APP_RUNTIME_DIR", str(PROJECT_ROOT / ".runtime")))
MANIFEST_PATH = DATA_DIR / "structured_sync_manifest.json"
TEACHER_PACKAGE_PATH = DATA_DIR / "teacher_memory_package.json"

REFERENCE_PATTERN = re.compile(r"\[\[(SEE_)?(FORMULA|TABLE|FIGURE|EXAMPLE):([^\]]+)\]\]", re.I)
FORMULA_REFERENCE_PATTERN = re.compile(r"\[\[(SEE_)?FORMULA:([^\]]+)\]\]", re.I)
_FORMULA_INDEX: Optional[Dict[str, Dict[str, str]]] = None

SEMANTIC_STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "these", "those", "are", "was",
    "were", "will", "can", "may", "not", "but", "into", "than", "then", "such", "under",
    "between", "within", "where", "which", "when", "what", "also", "very", "their",
    "there", "because", "while", "through", "using", "used", "value", "values", "trait",
    "traits", "selection", "response", "equation", "result", "results", "chapter",
}


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


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_data_dir()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _truncate(text: str, limit: int = 72) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


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


def _clean_label(text: str) -> str:
    text = _expand_formula_references(text or "", display=False)
    text = re.sub(r"\[\[(?:SEE_)?TABLE:[^\]]+\]\]", "", text)
    text = re.sub(r"\$\$[\s\S]*?\$\$", "[formula]", text)
    text = re.sub(r"\$[^$]+\$", "[math]", text)
    return _truncate(text)


def _chapter_node_id(chapter: str) -> str:
    return f"chapter::{chapter}"


def _chapter_label(chapter: str, title: Optional[str]) -> str:
    if title and title.strip().lower() != chapter.strip().lower():
        return f"{_chapter_display_name(chapter)}: {title}"
    return _chapter_display_name(chapter)


def _chapter_display_name(chapter: str) -> str:
    match = re.fullmatch(r"chapter0*([0-9]+)", chapter.strip(), flags=re.I)
    if match:
        return f"Chapter {int(match.group(1))}"
    match = re.fullmatch(r"appendix0*([0-9]+)", chapter.strip(), flags=re.I)
    if match:
        return f"Appendix {int(match.group(1))}"
    return chapter.replace("_", " ").title()


def _slug_heading(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", text, flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:10]
    return text[:96]


def _section_node_id(chapter: str, heading_path: List[str]) -> str:
    path_slug = "__".join(_slug_heading(item) for item in heading_path if str(item or "").strip())
    if not path_slug:
        path_slug = "untitled"
    return f"section::{chapter}::{path_slug}"


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


def _parse_references(text: str) -> Tuple[Set[str], Set[str]]:
    refs = _parse_all_references(text)
    return refs["formula"], refs["table"]


def _parse_all_references(text: str) -> Dict[str, Set[str]]:
    formula_ids: Set[str] = set()
    table_ids: Set[str] = set()
    figure_ids: Set[str] = set()
    example_ids: Set[str] = set()
    for _, ref_type, ref_id in REFERENCE_PATTERN.findall(text or ""):
        normalized = ref_id.strip()
        ref_type = ref_type.upper()
        if ref_type == "FORMULA":
            formula_ids.add(normalized)
        elif ref_type == "TABLE":
            table_ids.add(normalized)
        elif ref_type == "FIGURE":
            figure_ids.add(normalized)
        elif ref_type == "EXAMPLE":
            example_ids.add(normalized)
    return {
        "formula": formula_ids,
        "table": table_ids,
        "figure": figure_ids,
        "example": example_ids,
    }
