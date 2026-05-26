"""Fuse exported book TOC entries with structured knowledge units.

The exported TOC is the source of truth for the book tree shape and page
numbers. The structured JSON files are the source of truth for content
ownership, because their filenames and metadata carry stable chapter IDs such
as ``chapter13`` even when a TOC entry uses local numbering inside a Part.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class StructuredUnit:
    unit_id: str
    chapter: str
    path: Path
    headings: tuple[str, ...]
    is_chapter_intro: bool = False


@dataclass
class TocFusion:
    toc_by_id: Dict[str, Dict[str, Any]]
    root_ids: List[str]
    chapter_to_toc_id: Dict[str, str] = field(default_factory=dict)
    unit_to_toc_id: Dict[str, str] = field(default_factory=dict)
    metadata_by_toc_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def default_heading_path_from_metadata(metadata: Dict[str, Any]) -> List[str]:
    raw_path = metadata.get("heading_path")
    if isinstance(raw_path, list):
        candidates = [str(item or "").strip() for item in raw_path]
    else:
        candidates = []
        for key in ("section_level_1", "section_level_2", "section_level_3", "section"):
            value = str(metadata.get(key) or "").strip()
            if value:
                candidates.append(value)
        subsections = metadata.get("subsections")
        if isinstance(subsections, list):
            candidates.extend(str(item or "").strip() for item in subsections)

    result: List[str] = []
    seen_adjacent = ""
    for item in candidates:
        normalized = re.sub(r"\s+", " ", item).strip()
        if not normalized or normalized == seen_adjacent:
            continue
        result.append(normalized)
        seen_adjacent = normalized
    return result


def build_structured_units(
    source_paths: Iterable[Path],
    *,
    heading_path_from_metadata: Callable[[Dict[str, Any]], List[str]] = default_heading_path_from_metadata,
) -> List[StructuredUnit]:
    units: List[StructuredUnit] = []
    for source_path in source_paths:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        chapter = str(metadata.get("chapter") or source_path.stem.split("_")[0]).strip()
        unit_id = str(payload.get("id") or source_path.stem).strip()
        headings = tuple(heading_path_from_metadata(metadata))
        units.append(
            StructuredUnit(
                unit_id=unit_id,
                chapter=chapter,
                path=source_path,
                headings=headings,
                is_chapter_intro=source_path.stem.lower().endswith("_001"),
            )
        )
    return units


def fuse_toc_with_structured_units(toc_path: Path, units: Iterable[StructuredUnit]) -> TocFusion:
    payload = json.loads(toc_path.read_text(encoding="utf-8"))
    raw_nodes = payload.get("nodes") if isinstance(payload.get("nodes"), dict) else {}
    root_ids = [str(item or "").strip() for item in (payload.get("root_nodes") or []) if str(item or "").strip()]
    toc_by_id = _normalize_toc_nodes(raw_nodes)
    children_by_parent = _children_by_parent(toc_by_id)
    ordered_items = sorted(toc_by_id.values(), key=_toc_sort_key)
    for siblings in children_by_parent.values():
        siblings.sort(key=lambda toc_id: _toc_sort_key(toc_by_id.get(toc_id, {"id": toc_id})))

    structured_units = list(units)
    units_by_chapter: Dict[str, List[StructuredUnit]] = {}
    for unit in structured_units:
        units_by_chapter.setdefault(_chapter_key(unit.chapter), []).append(unit)
    for values in units_by_chapter.values():
        values.sort(key=lambda item: item.path.name.lower())

    metadata_by_toc_id = {
        toc_id: _toc_metadata(toc_id, toc_by_id)
        for toc_id in toc_by_id
    }
    chapter_to_toc_id = _map_chapters_to_toc(
        toc_by_id,
        children_by_parent,
        ordered_items,
        units_by_chapter,
    )
    unit_to_toc_id = _map_units_to_toc(
        toc_by_id,
        children_by_parent,
        units_by_chapter,
        chapter_to_toc_id,
    )
    diagnostics = _build_diagnostics(toc_by_id, root_ids, units_by_chapter, chapter_to_toc_id, unit_to_toc_id)
    return TocFusion(
        toc_by_id=toc_by_id,
        root_ids=root_ids,
        chapter_to_toc_id=chapter_to_toc_id,
        unit_to_toc_id=unit_to_toc_id,
        metadata_by_toc_id=metadata_by_toc_id,
        diagnostics=diagnostics,
    )


def _normalize_toc_nodes(raw_nodes: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_id, item in raw_nodes.items():
        if not isinstance(item, dict):
            continue
        toc_id = str(item.get("id") or raw_id or "").strip()
        title = str(item.get("title") or "").strip()
        if not toc_id or not title:
            continue
        copy = dict(item)
        copy["id"] = toc_id
        copy["title"] = title
        normalized[toc_id] = copy
    return normalized


def _children_by_parent(toc_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    children: Dict[str, List[str]] = {}
    for toc_id, item in toc_by_id.items():
        parent_id = str(item.get("parent_id") or "").strip()
        if parent_id:
            children.setdefault(parent_id, []).append(toc_id)
    return children


def _toc_sort_key(item: Dict[str, Any]) -> tuple[int, int, str]:
    return (_int_value(item.get("page")), _int_value(item.get("level")), str(item.get("id") or ""))


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _entry_type(item: Dict[str, Any]) -> str:
    return str(item.get("entry_type") or "").strip().lower()


def _chapter_key(chapter: str) -> str:
    return str(chapter or "").strip().lower()


def _chapter_number(chapter: str) -> Optional[int]:
    match = re.fullmatch(r"chapter0*([0-9]+)", _chapter_key(chapter), flags=re.I)
    return int(match.group(1)) if match else None


def _appendix_number(chapter: str) -> Optional[int]:
    match = re.fullmatch(r"appendix0*([0-9]+)", _chapter_key(chapter), flags=re.I)
    return int(match.group(1)) if match else None


def _normalize_match_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = re.sub(r"\$[^$]*\$", " ", text)
    text = text.replace("'", "")
    text = text.lower()
    text = re.sub(r"\bchapter\s*[0-9]+\b", " ", text)
    text = re.sub(r"\bappendix\s*[0-9]+\b", " ", text)
    text = re.sub(r"^[a0-9]+[.]\s*", "", text)
    text = re.sub(r"\b[ivx]+[.]\s*", " ", text)
    text = re.sub(r"\bintroduction\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_intro_heading(value: Any) -> bool:
    normalized = _normalize_match_text(value)
    return normalized in {"", "intro"} or normalized.endswith(" introduction")


def _title_score(query: str, title: str) -> float:
    left = _normalize_match_text(query)
    right = _normalize_match_text(title)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_terms = set(left.split())
    right_terms = set(right.split())
    if not left_terms or not right_terms:
        return 0.0
    query_coverage = len(left_terms & right_terms) / len(left_terms)
    target_coverage = len(left_terms & right_terms) / len(right_terms)
    harmonic = (
        (2 * query_coverage * target_coverage) / (query_coverage + target_coverage)
        if query_coverage + target_coverage
        else 0.0
    )
    sequence = SequenceMatcher(None, left, right).ratio()
    contains = 0.96 if (left in right or right in left) and min(len(left_terms), len(right_terms)) >= 3 else 0.0
    return max(harmonic, sequence, contains)


def _best_match(queries: Iterable[str], candidates: Iterable[Dict[str, Any]]) -> tuple[float, Optional[Dict[str, Any]]]:
    deduped_queries = list(dict.fromkeys(str(query or "").strip() for query in queries if str(query or "").strip()))
    best_score = 0.0
    best_node: Optional[Dict[str, Any]] = None
    for item in candidates:
        score = max((_title_score(query, str(item.get("title") or "")) for query in deduped_queries), default=0.0)
        if score > best_score:
            best_score = score
            best_node = item
    return best_score, best_node


def _ancestor_ids(toc_id: str, toc_by_id: Dict[str, Dict[str, Any]]) -> List[str]:
    ancestors: List[str] = []
    visited: set[str] = set()
    current_id = toc_id
    while current_id and current_id in toc_by_id and current_id not in visited:
        visited.add(current_id)
        parent_id = str(toc_by_id[current_id].get("parent_id") or "").strip()
        if not parent_id:
            break
        ancestors.append(parent_id)
        current_id = parent_id
    return ancestors


def _path_for(toc_id: str, toc_by_id: Dict[str, Dict[str, Any]]) -> List[str]:
    items: List[str] = []
    current_ids = [toc_id, *_ancestor_ids(toc_id, toc_by_id)]
    for current_id in reversed(current_ids):
        title = str((toc_by_id.get(current_id) or {}).get("title") or "").strip()
        if title:
            items.append(title)
    return items


def _descendants_of(
    toc_id: str,
    toc_by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
    *,
    include_self: bool = True,
) -> List[Dict[str, Any]]:
    ordered: List[Dict[str, Any]] = []
    visited: set[str] = set()

    def visit(current_id: str) -> None:
        if current_id in visited:
            return
        visited.add(current_id)
        item = toc_by_id.get(current_id)
        if not item:
            return
        ordered.append(item)
        explicit_children = [
            str(child_id or "").strip()
            for child_id in (item.get("children") or [])
            if str(child_id or "").strip()
        ]
        child_ids = explicit_children or children_by_parent.get(current_id, [])
        for child_id in child_ids:
            visit(child_id)

    if include_self:
        visit(toc_id)
    else:
        for child_id in children_by_parent.get(toc_id, []):
            visit(child_id)
    return ordered


def _nearest_chapter_or_appendix(toc_id: str, toc_by_id: Dict[str, Dict[str, Any]]) -> Optional[str]:
    for candidate_id in [toc_id, *_ancestor_ids(toc_id, toc_by_id)]:
        item = toc_by_id.get(candidate_id)
        if _entry_type(item or {}) in {"chapter", "appendix"}:
            return candidate_id
    return None


def _root_part_id(toc_id: str, toc_by_id: Dict[str, Dict[str, Any]]) -> Optional[str]:
    current_id = toc_id
    visited: set[str] = set()
    best: Optional[str] = None
    while current_id and current_id in toc_by_id and current_id not in visited:
        visited.add(current_id)
        if _entry_type(toc_by_id[current_id]) == "part":
            best = current_id
        parent_id = str(toc_by_id[current_id].get("parent_id") or "").strip()
        if not parent_id:
            break
        current_id = parent_id
    return best


def _unit_queries(units: Iterable[StructuredUnit]) -> List[str]:
    queries: List[str] = []
    for unit in units:
        queries.extend(unit.headings)
    return [query for query in queries if not _is_intro_heading(query)]


def _chapter_title_queries(units: Iterable[StructuredUnit]) -> List[str]:
    queries: List[str] = []
    for unit in units:
        for heading in unit.headings:
            if _is_intro_heading(heading):
                continue
            normalized = re.sub(r":\s*introduction\s*$", "", heading, flags=re.I).strip()
            if normalized:
                queries.append(normalized)
                parts = [part.strip() for part in re.split(r"\s*:\s*", normalized) if part.strip()]
                for index in range(1, len(parts)):
                    tail = ": ".join(parts[index:])
                    if tail:
                        queries.append(tail)
                queries.extend(parts)
            queries.append(heading)
            break
    return queries


def _map_chapters_to_toc(
    toc_by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
    ordered_items: List[Dict[str, Any]],
    units_by_chapter: Dict[str, List[StructuredUnit]],
) -> Dict[str, str]:
    chapter_like_items = [
        item
        for item in ordered_items
        if _entry_type(item) in {"chapter", "appendix"}
    ]
    appendix_root_items = [
        item
        for item in ordered_items
        if re.match(r"^\s*A0*[0-9]+(?:[.\s]|$)", str(item.get("title") or ""), flags=re.I)
    ]
    unused_ids = {str(item.get("id") or "") for item in chapter_like_items}
    result: Dict[str, str] = {}

    # Appendices generally have globally stable A1/A2 numbering in the TOC.
    for chapter, units in sorted(units_by_chapter.items()):
        appendix_number = _appendix_number(chapter)
        if appendix_number is None:
            continue
        candidate = next(
            (
                item
                for item in [*chapter_like_items, *appendix_root_items]
                if re.match(
                    rf"^\s*A0*{appendix_number}(?:[.\s]|$)",
                    str(item.get("title") or ""),
                    flags=re.I,
                )
            ),
            None,
        )
        if not candidate:
            score, candidate = _best_match(_chapter_title_queries(units), [*chapter_like_items, *appendix_root_items])
            if score < 0.86:
                candidate = None
        if candidate:
            toc_id = str(candidate.get("id") or "")
            result[chapter] = toc_id
            unused_ids.discard(toc_id)

    # Numeric chapter labels in the exported TOC are often local to a Part, so
    # match by structured chapter title/section text first.
    scored: List[tuple[float, str, str]] = []
    for chapter, units in sorted(units_by_chapter.items()):
        if chapter in result or _chapter_number(chapter) is None:
            continue
        queries = _chapter_title_queries(units)
        if not queries:
            continue
        for item in chapter_like_items:
            toc_id = str(item.get("id") or "")
            if not toc_id or toc_id not in unused_ids:
                continue
            score, _ = _best_match(queries, [item])
            if score >= 0.72:
                scored.append((score, chapter, toc_id))

    for score, chapter, toc_id in sorted(scored, reverse=True):
        if chapter in result or toc_id not in unused_ids:
            continue
        same_chapter_scores = [item for item in scored if item[1] == chapter]
        higher_or_equal = [item for item in same_chapter_scores if item[0] >= score and item[2] != toc_id]
        if score >= 0.86 and (score >= 0.90 or not higher_or_equal):
            result[chapter] = toc_id
            unused_ids.discard(toc_id)

    return result


def _map_units_to_toc(
    toc_by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
    units_by_chapter: Dict[str, List[StructuredUnit]],
    chapter_to_toc_id: Dict[str, str],
) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for chapter, units in sorted(units_by_chapter.items(), key=lambda item: _structured_chapter_sort_key(item[0])):
        chapter_toc_id = chapter_to_toc_id.get(chapter)
        descendant_items = (
            [
                item
                for item in _descendants_of(chapter_toc_id, toc_by_id, children_by_parent)
                if _entry_type(item) not in {"index", "literature_cited"}
            ]
            if chapter_toc_id
            else []
        )
        for unit in sorted(units, key=lambda item: item.path.name.lower()):
            unit_key = unit.unit_id.strip().lower()
            if unit.is_chapter_intro or not chapter_toc_id:
                result[unit_key] = chapter_toc_id or ""
                continue
            queries = [heading for heading in unit.headings if not _is_intro_heading(heading)]
            if not queries:
                result[unit_key] = chapter_toc_id
                continue
            score, best_node = _best_match(queries, descendant_items)
            toc_id = str((best_node or {}).get("id") or "").strip()
            nearest = _nearest_chapter_or_appendix(toc_id, toc_by_id) if toc_id else None
            if toc_id and nearest == chapter_toc_id and score >= 0.88:
                result[unit_key] = toc_id
            else:
                result[unit_key] = chapter_toc_id
    return result


def _toc_metadata(toc_id: str, toc_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    item = toc_by_id.get(toc_id) or {}
    root_part = _root_part_id(toc_id, toc_by_id)
    return {
        "toc_node_id": toc_id,
        "toc_title": item.get("title"),
        "toc_entry_type": item.get("entry_type"),
        "toc_level": item.get("level"),
        "toc_page": item.get("page"),
        "toc_parent_id": item.get("parent_id"),
        "toc_path": _path_for(toc_id, toc_by_id),
        "toc_root_part_id": root_part,
        "toc_root_part_title": (toc_by_id.get(root_part or "") or {}).get("title"),
        "toc_fusion_source": "structured_toc_fusion",
    }


def _structured_chapter_sort_key(chapter: str) -> tuple[int, str]:
    number = _chapter_number(chapter)
    if number is not None:
        return (number, chapter)
    appendix = _appendix_number(chapter)
    if appendix is not None:
        return (1000 + appendix, chapter)
    return (10000, chapter)


def _build_diagnostics(
    toc_by_id: Dict[str, Dict[str, Any]],
    root_ids: List[str],
    units_by_chapter: Dict[str, List[StructuredUnit]],
    chapter_to_toc_id: Dict[str, str],
    unit_to_toc_id: Dict[str, str],
) -> Dict[str, Any]:
    chapter_like_count = sum(
        1
        for item in toc_by_id.values()
        if _entry_type(item) in {"chapter", "appendix"}
        or re.match(r"^\s*A0*[0-9]+(?:[.\s]|$)", str(item.get("title") or ""), flags=re.I)
    )
    return {
        "toc_node_count": len(toc_by_id),
        "toc_root_count": len(root_ids),
        "toc_chapter_like_count": chapter_like_count,
        "structured_chapter_count": len(units_by_chapter),
        "structured_unit_count": sum(len(items) for items in units_by_chapter.values()),
        "mapped_chapter_count": len([item for item in chapter_to_toc_id.values() if item]),
        "mapped_unit_count": len([item for item in unit_to_toc_id.values() if item]),
        "unmapped_chapters": sorted(chapter for chapter in units_by_chapter if not chapter_to_toc_id.get(chapter)),
    }
