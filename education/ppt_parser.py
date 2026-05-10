"""PPT parsing helpers for extracting slide content used by lecture generation."""
from __future__ import annotations

import base64
import io
from typing import Any, Dict, List

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Pt


MAX_INLINE_IMAGE_BYTES = 800 * 1024


def parse_ppt(file_bytes: bytes) -> Dict[str, Any]:
    """Parse PPT bytes into per-slide structured content."""
    try:
        prs = Presentation(io.BytesIO(file_bytes))
    except Exception as exc:
        return {"success": False, "error": f"PPT 文件解析失败: {exc}"}

    slides: List[Dict[str, Any]] = []
    all_texts: List[str] = []

    for idx, slide in enumerate(prs.slides, 1):
        slide_data = _parse_slide(slide, idx)
        slides.append(slide_data)
        raw_text = str(slide_data.get("raw_text") or "").strip()
        if raw_text:
            all_texts.append(raw_text)

    return {
        "success": True,
        "slide_count": len(slides),
        "slides": slides,
        "full_text": "\n\n---\n\n".join(all_texts),
    }


def _parse_slide(slide: Any, index: int) -> Dict[str, Any]:
    title = ""
    body_texts: List[str] = []
    tables: List[Dict[str, Any]] = []
    notes = ""
    image_count = 0
    images: List[Dict[str, Any]] = []

    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            image_count += 1
            image_data = _extract_image(shape)
            if image_data:
                images.append(image_data)
            continue

        if getattr(shape, "has_text_frame", False):
            text = str(shape.text or "").strip()
            if text:
                if _is_title_shape(shape) and not title:
                    title = text
                else:
                    body_texts.append(text)

        if getattr(shape, "has_table", False):
            tables.append(_parse_table(shape.table))

    if getattr(slide, "has_notes_slide", False):
        notes_frame = slide.notes_slide.notes_text_frame
        if notes_frame:
            notes = str(notes_frame.text or "").strip()

    raw_text = _build_raw_text(title, body_texts, tables, notes)
    return {
        "index": index,
        "title": title,
        "body_texts": body_texts,
        "tables": tables,
        "notes": notes,
        "image_count": image_count,
        "images": images,
        "raw_text": raw_text,
    }


def _extract_image(shape: Any) -> Dict[str, Any]:
    try:
        image = shape.image
        image_bytes = image.blob
        data_uri = None
        oversized = len(image_bytes) > MAX_INLINE_IMAGE_BYTES
        if not oversized:
            encoded = base64.b64encode(image_bytes).decode("utf-8")
            data_uri = f"data:{image.content_type};base64,{encoded}"
        result = {
            "data_uri": data_uri,
            "width_emu": int(shape.width),
            "height_emu": int(shape.height),
            "left_emu": int(shape.left),
            "top_emu": int(shape.top),
        }
        if oversized:
            result["oversized"] = True
        return result
    except Exception:
        return {}


def _is_title_shape(shape: Any) -> bool:
    if not getattr(shape, "has_text_frame", False):
        return False
    try:
        ph_type = shape.placeholder_format.type
        if ph_type in {1, 3, 4}:  # TITLE, CENTER_TITLE, SUBTITLE
            return True
    except Exception:
        pass

    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            if run.font.size and run.font.size >= Pt(24):
                return True
            if run.font.bold:
                return True
    return False


def _parse_table(table: Any) -> Dict[str, Any]:
    rows = []
    for row in table.rows:
        rows.append([str(cell.text or "").strip() for cell in row.cells])
    return {"rows": rows}


def _build_raw_text(title: str, body_texts: List[str], tables: List[Dict[str, Any]], notes: str) -> str:
    parts: List[str] = []
    if title:
        parts.append(f"## {title}")
    parts.extend(text for text in body_texts if text)
    for table_data in tables:
        table_text = _format_table_text(table_data)
        if table_text:
            parts.append(table_text)
    if notes:
        parts.append(f"[备注] {notes}")
    return "\n".join(parts)


def _format_table_text(table_data: Dict[str, Any]) -> str:
    rows = table_data.get("rows", [])
    if not rows:
        return ""
    lines = []
    for index, row in enumerate(rows):
        line = " | ".join(str(cell) for cell in row)
        lines.append(line)
        if index == 0:
            lines.append("-" * max(len(line), 10))
    return "\n".join(lines)


def build_ppt_lecture_prompt_data(parse_result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert parser output into the payload used by lecture generation."""
    if not parse_result.get("success"):
        return {
            "chapter_title": "未命名PPT",
            "chapter_content": "",
            "slide_details": [],
            "total_slides": 0,
        }

    slides = parse_result.get("slides", [])
    first_title = next((slide.get("title") for slide in slides if slide.get("title")), "")

    slide_details = []
    for slide in slides:
        slide_details.append(
            {
                "index": slide["index"],
                "title": slide.get("title", ""),
                "content": "\n".join(slide.get("body_texts", [])),
                "notes": slide.get("notes", ""),
                "has_images": slide.get("image_count", 0) > 0,
                "image_count": slide.get("image_count", 0),
                "images": slide.get("images", []),
                "tables": slide.get("tables", []),
                "body_texts": slide.get("body_texts", []),
                "raw_text": slide.get("raw_text", ""),
            }
        )

    return {
        "chapter_title": first_title or "未命名PPT",
        "chapter_content": parse_result.get("full_text", ""),
        "slide_details": slide_details,
        "total_slides": len(slides),
    }
