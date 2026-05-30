from __future__ import annotations

import json
import logging
import os
import re
import base64
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .beamer_generator_full import config
from .beamer_generator_full.deepseek_client import DeepSeekClient
from .beamer_generator_full.latex_parser import parse_latex_to_slides
from .beamer_generator_full.pptx_generator import generate_pptx
from .beamer_generator_full.prompt_engine import PromptEngine


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent / "beamer_generator_full"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SAVED_PROJECT_DIR = BASE_DIR / "saved_projects"
SAVED_PROJECT_DIR.mkdir(parents=True, exist_ok=True)
EQUATION_INDEX_PATH = BASE_DIR / "equation_index.json"

prompt_engine = PromptEngine(config.SYSTEM_PROMPT_PATH)
router = APIRouter(prefix="/beamer-generator", tags=["beamer-generator"])


class GenerateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    api_key: str = Field(default="")
    style: str = Field(default="academic")
    custom_requirements: str = Field(default="", max_length=5000)
    slide_count: int = Field(default=7, ge=1, le=80)
    language: str = Field(default="title_terms_en_content_zh")
    base_url: str = Field(default="")
    model: str = Field(default="")
    figure_assets: dict[str, str] = Field(default_factory=dict)


class ParseRequest(BaseModel):
    latex: str = Field(..., min_length=1)
    filename: str = Field(default="presentation.tex")


class RenderLatexRequest(ParseRequest):
    pass


class SlideImage(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str = ""
    x: float = 1.0
    y: float = 3.0
    width: float = 4.0


class SlideTextbox(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str = ""
    x: float = 0
    y: float = 0
    width: float = 260
    height: float = 96
    color: str = "#333333"
    bg: str = ""
    fontSize: float = 14
    align: str = "left"
    bold: bool = False
    italic: bool = False


class SlideCallout(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str = ""
    x: float = 130
    y: float = 180
    width: float = 250
    height: float = 92
    fontSize: float = 12
    align: str = "center"


class SlidePlaceholder(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "image"
    label: str = "图片占位"
    position: str = ""
    figure: str = ""
    asset: str = ""
    url: str = ""
    path: str = ""
    page: int = 0
    x: float = 570
    y: float = 150
    width: float = 245
    height: float = 230


class SlideData(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int = 0
    type: str = "content"
    title: str = ""
    subtitle: str = ""
    titleCredit: str = ""
    reviewBackground: bool = False
    backgroundMode: str = ""
    renderedBackground: str = ""
    renderedBackgroundWidth: int = 0
    renderedBackgroundHeight: int = 0
    latexRenderedPage: bool = False
    hideParsedContent: bool = False
    items: List[str] = []
    equations: List[str] = []
    missing_equations: List[dict] = Field(default_factory=list)
    table: Optional[dict] = None
    notes: str = ""
    images: List[SlideImage] = []
    placeholders: List[SlidePlaceholder] = []
    textboxes: List[SlideTextbox] = []
    callouts: List[SlideCallout] = []


class RenderedSlide(BaseModel):
    page_index: int = 0
    image: str = ""
    width: int = 0
    height: int = 0


class ExportRequest(BaseModel):
    title: str = "Presentation"
    subtitle: str = ""
    author: str = ""
    date: str = ""
    slides: List[SlideData] = []
    figure_assets: dict[str, str] = Field(default_factory=dict)
    rendered_slides: List[RenderedSlide] = Field(default_factory=list)
    missing_equations: List[dict] = Field(default_factory=list)


class SaveProjectRequest(ExportRequest):
    latex: str = ""
    chapter_id: str = ""
    chapter_title: str = ""


class OverleafPackageRequest(SaveProjectRequest):
    pass


def _safe_saved_project_id(value: str, fallback: str = "presentation") -> str:
    raw = (value or "").strip() or fallback
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-")
    return safe[:80] or fallback


def _saved_project_path(project_id: str) -> Path:
    return SAVED_PROJECT_DIR / f"{_safe_saved_project_id(project_id)}.json"


def _saved_project_summary(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    slides = data.get("slides") if isinstance(data.get("slides"), list) else []
    return {
        "chapter_id": data.get("chapter_id") or path.stem,
        "chapter_title": data.get("chapter_title") or data.get("title") or path.stem,
        "title": data.get("title") or "",
        "updated_at": data.get("updated_at") or "",
        "slide_count": len(slides),
        "missing_equation_count": len(data.get("missing_equations") or []),
        "slides": [
            {
                "page_index": idx,
                "title": (slide or {}).get("title") or f"Slide {idx + 1}",
                "type": (slide or {}).get("type") or "content",
            }
            for idx, slide in enumerate(slides)
        ],
    }


def _read_root_env_values() -> dict[str, str]:
    env_path = BASE_DIR.parents[1] / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _deepseek_setting(name: str, fallback: str = "") -> str:
    file_values = _read_root_env_values()
    for key, value in file_values.items():
        if key.startswith("DEEPSEEK_") and value and not os.getenv(key):
            os.environ[key] = value
    return os.getenv(name) or file_values.get(name, fallback)


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
@router.get("/index.html", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(
        str(STATIC_DIR / "index.html"),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "beamer-generator"}


def _stream_error(message: str) -> StreamingResponse:
    async def event_stream():
        error_data = json.dumps({"type": "error", "content": message}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _payload_text(payload: dict, key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return str(value if value is not None else default)


def _payload_int(payload: dict, key: str, default: int = 0) -> int:
    try:
        return int(payload.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _payload_map(payload: dict, key: str) -> dict[str, str]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for k, v in value.items():
        k_text = str(k or "").strip()
        v_text = str(v or "").strip()
        if k_text and v_text:
            result[k_text] = v_text
    return result


def _payload_selected_sections(payload: dict) -> list[dict[str, str]]:
    value = payload.get("selected_sections", [])
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for entry in value[:40]:
        if not isinstance(entry, dict):
            continue
        file_text = str(entry.get("file") or "").strip()
        title_text = str(entry.get("title") or "").strip()
        id_text = str(entry.get("id") or "").strip()
        if file_text or title_text:
            result.append({"file": file_text, "title": title_text, "id": id_text})
    return result


def _selected_sections_requirement(sections: list[dict[str, str]]) -> str:
    if not sections:
        return ""
    lines = [
        "本次只允许使用前端已引用的 Markdown 小节生成 PPT；不要使用同一 Markdown 文件中未引用的小节内容。",
        "已引用小节：",
    ]
    for section in sections:
        label = " / ".join(part for part in (section.get("file"), section.get("title")) if part)
        if label:
            lines.append(f"- {label}")
    return "\n".join(lines)


def _equation_reference_key(value: str, is_label: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if is_label:
        return "label:" + text
    match = re.search(r"\d+(?:\.\d+)+|\d+", text)
    return "num:" + match.group(0) if match else "label:" + text


def _extract_equation_references(latex: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(key: str, label: str, raw: str) -> None:
        if not key or key in seen:
            return
        seen.add(key)
        refs.append({"key": key, "label": label, "raw": raw})

    for match in re.finditer(r"\\(eqref|ref)\{([^{}]+)\}", latex or ""):
        command, label = match.group(1), match.group(2).strip()
        low = label.lower()
        if command == "ref" and not re.search(r"(^|[:_.-])(eq|equation|formula)([:_.-]|$)", low):
            continue
        if re.search(r"(^|[:_.-])(fig|figure|tab|table|sec|section|chap|chapter)([:_.-]|$)", low):
            continue
        add(_equation_reference_key(label, is_label=True), f"Equation {label}", match.group(0))

    text_ref_pattern = re.compile(
        r"((?:公式|方程|Equation|Eq\.?)\s*[\(（]?\s*(\d+(?:\.\d+)+|\d+)\s*[\)）]?)",
        re.IGNORECASE,
    )
    for match in text_ref_pattern.finditer(latex or ""):
        number = match.group(2)
        add(_equation_reference_key(number), f"Equation {number}", match.group(1))
    return refs


def _extract_equation_definition_keys(latex: str) -> set[str]:
    keys: set[str] = set()
    for label in re.findall(r"\\label\{([^{}]+)\}", latex or ""):
        keys.add(_equation_reference_key(label, is_label=True))
        number = re.search(r"\d+(?:\.\d+)+|\d+", label)
        if number:
            keys.add(_equation_reference_key(number.group(0)))
    for tag in re.findall(r"\\tag\{([^{}]+)\}", latex or ""):
        keys.add(_equation_reference_key(tag))
    return keys


def _missing_equation_macro() -> str:
    return (
        "\\providecommand{\\kgmissingequation}[2]{"
        "\\textcolor{red}{\\textbf{缺失公式：#2。请导入包含该公式的章节后自动补全。}}}\n"
    )


def _safe_image_macros() -> str:
    return (
        "\\providecommand{\\safelogoimage}[1]{\\IfFileExists{#1}{\\includegraphics[height=39pt, keepaspectratio]{#1}}{\\fbox{\\parbox[c][30pt][c]{65pt}{\\centering\\tiny Missing\\\\image}}}}\n"
        "\\providecommand{\\safecontentimage}[1]{\\IfFileExists{#1}{\\includegraphics[width=0.7\\textwidth]{#1}}{\\fbox{\\parbox[c][0.34\\textheight][c]{0.7\\textwidth}{\\centering\\scriptsize Missing image\\\\\\texttt{\\detokenize{#1}}}}}}\n"
        "\\providecommand{\\safeverticalimage}[1]{\\IfFileExists{#1}{\\includegraphics[width=\\textwidth]{#1}}{\\fbox{\\parbox[c][0.34\\textheight][c]{\\textwidth}{\\centering\\scriptsize Missing image\\\\\\texttt{\\detokenize{#1}}}}}}\n"
    )


def _ensure_safe_image_macros(latex: str) -> str:
    if re.search(r"\\(?:providecommand|newcommand|renewcommand)\{\\safecontentimage\}", latex or ""):
        return latex
    begin_doc = r"\begin{document}"
    idx = (latex or "").find(begin_doc)
    if idx >= 0:
        return latex[:idx] + _safe_image_macros() + latex[idx:]
    return _safe_image_macros() + (latex or "")


def _ensure_missing_equation_macro(latex: str) -> str:
    if re.search(r"\\(?:providecommand|newcommand|renewcommand)\{\\kgmissingequation\}", latex or ""):
        return latex
    begin_doc = r"\begin{document}"
    idx = latex.find(begin_doc)
    if idx != -1:
        return latex[:idx] + _missing_equation_macro() + latex[idx:]
    return _missing_equation_macro() + (latex or "")


def _missing_equation_block(ref: dict[str, str]) -> str:
    key = ref.get("key", "")
    label = ref.get("label", key)
    return (
        "\\begin{alertblock}{缺失公式}\n"
        f"\\kgmissingequation{{{key}}}{{{label}}}\n"
        "\\end{alertblock}"
    )


def _mark_missing_equations(latex: str) -> tuple[str, list[dict[str, str]]]:
    text = latex or ""
    refs = _extract_equation_references(text)
    defined = _extract_equation_definition_keys(text)
    missing = [ref for ref in refs if ref["key"] not in defined]
    if not missing:
        return text, []

    text = _ensure_missing_equation_macro(text)
    frames = re.findall(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?[\s\S]*?\\end\{frame\}", text)
    appended: set[str] = set()
    for frame in frames:
        frame_missing = [
            ref for ref in missing
            if ref["key"] not in appended and ref.get("raw") and ref["raw"] in frame
        ]
        if not frame_missing:
            continue
        addition = "\n\n" + "\n\n".join(_missing_equation_block(ref) for ref in frame_missing)
        replacement = frame.replace(r"\end{frame}", addition + "\n\\end{frame}", 1)
        text = text.replace(frame, replacement, 1)
        appended.update(ref["key"] for ref in frame_missing)

    remaining = [ref for ref in missing if ref["key"] not in appended]
    if remaining:
        frame = (
            "\\begin{frame}{Missing Equations}\n"
            + "\n\n".join(_missing_equation_block(ref) for ref in remaining)
            + "\n\\end{frame}"
        )
        text = _insert_frames_before_end_document(text, [frame])
    return text, missing


def _extract_equations_from_source(source: str) -> dict[str, str]:
    equations: dict[str, str] = {}
    patterns = [
        r"\\begin\{(equation|align|alignat|gather|multline)\*?\}[\s\S]*?\\end\{\1\*?\}",
        r"\\\[[\s\S]*?\\\]",
        r"\$\$[\s\S]*?\$\$",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, source or ""):
            block = match.group(0).strip()
            keys = _extract_equation_definition_keys(block)
            before = (source or "")[max(0, match.start() - 120):match.start()]
            after = (source or "")[match.end():match.end() + 120]
            context = before + " " + after
            for ref in _extract_equation_references(context):
                keys.add(ref["key"])
            for key in keys:
                equations.setdefault(key, block)
    return equations


def _resolve_missing_equations_in_latex(latex: str, source: str) -> tuple[str, list[str], list[str]]:
    equations = _extract_equations_from_source(source)
    resolved: list[str] = []
    missing: list[str] = []
    text = latex or ""
    marker_pattern = re.compile(
        r"\\begin\{alertblock\}\{缺失公式\}\s*\\kgmissingequation\{([^{}]+)\}\{([^{}]*)\}\s*\\end\{alertblock\}",
        re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        label = match.group(2) or key
        formula = equations.get(key)
        if formula:
            resolved.append(label)
            return formula
        missing.append(label)
        return match.group(0)

    return marker_pattern.sub(replace, text), resolved, missing


def _normalize_figure_label(value: str) -> str:
    text = str(value or "")
    match = re.search(r"figure\s*\d+(?:\.\d+)?", text, re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(0)).strip().lower()
    match = re.search(r"(?:fig\.?|图)\s*\d+(?:[._]\d+)?", text, re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(0)).strip().lower()
    return re.sub(r"\s+", " ", text).strip().lower()


def _figure_number_filename(value: str) -> str:
    text = str(value or "")
    match = re.search(r"(?:figure|fig\.?|图)\s*(\d+(?:[._]\d+)?)", text, re.IGNORECASE)
    if not match:
        return ""
    number = match.group(1).replace(".", "_")
    return f"图{number}.png"


def _fig_path_for_label(label: str, figure_assets: dict[str, str]) -> str:
    key = _normalize_figure_label(label)
    for asset_label, asset in (figure_assets or {}).items():
        if _normalize_figure_label(asset_label) == key:
            filename = Path(str(asset or "").split("?", 1)[0].split("#", 1)[0].replace("\\", "/")).name
            if filename:
                return f"fig/{filename}"
    filename = _figure_number_filename(label)
    return f"fig/{filename}" if filename else ""


def _normalize_figure_label(value: str) -> str:
    text = str(value or "")
    match = re.search(r"(?:figure|fig\.?|图)\s*(\d+(?:[._]\d+)?)", text, re.IGNORECASE)
    if match:
        return "figure " + match.group(1).replace("_", ".")
    return re.sub(r"\s+", " ", text).strip().lower()


def _figure_number_filename(value: str) -> str:
    text = str(value or "")
    match = re.search(r"(?:figure|fig\.?|图)\s*(\d+(?:[._]\d+)?)", text, re.IGNORECASE)
    if not match:
        return ""
    number = match.group(1).replace(".", "_")
    return f"图{number}.png"


def _strip_missing_equation_markers(latex: str) -> str:
    text = latex or ""
    text = re.sub(
        r"\\begin\{alertblock\}\{(?:缺失公式|Missing Equation|Missing Equations|缂哄け鍏紡)\}"
        r"[\s\S]*?\\end\{alertblock\}",
        "",
        text,
    )
    return re.sub(r"\\kgmissingequation\{[^{}]*\}\{[^{}]*\}", "", text)


def _extract_equation_references(latex: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    source = _strip_missing_equation_markers(latex)

    def add(key: str, label: str, raw: str) -> None:
        if not key or key in seen:
            return
        seen.add(key)
        refs.append({"key": key, "label": label, "raw": raw})

    for match in re.finditer(r"\\(eqref|ref|autoref|cref|Cref)\{([^{}]+)\}", source):
        command, label = match.group(1), match.group(2).strip()
        low = label.lower()
        if command == "ref" and not re.search(r"(^|[:_.-])(eq|equation|formula)([:_.-]|$)", low):
            continue
        if re.search(r"(^|[:_.-])(fig|figure|tab|table|sec|section|chap|chapter)([:_.-]|$)", low):
            continue
        add(_equation_reference_key(label, is_label=True), f"Equation {label}", match.group(0))

    text_ref_pattern = re.compile(
        r"((?:公式|方程|Equation|Equations|Eq\.?|Eqs\.?)\s*[\(（]?\s*(\d+(?:\.\d+)+|\d+)\s*[\)）]?)",
        re.IGNORECASE,
    )
    for match in text_ref_pattern.finditer(source):
        number = match.group(2)
        add(_equation_reference_key(number), f"Equation {number}", match.group(1))
    return refs


def _extract_equation_definition_keys(latex: str) -> set[str]:
    source = latex or ""
    keys: set[str] = set()
    equation_blocks = re.findall(
        r"\\begin\{(?:equation|align|alignat|gather|multline)\*?\}[\s\S]*?\\end\{(?:equation|align|alignat|gather|multline)\*?\}"
        r"|\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$",
        source,
    )
    blocks = equation_blocks or [source]
    for block in blocks:
        for label in re.findall(r"\\label\{([^{}]+)\}", block):
            low = label.lower()
            if re.search(r"(^|[:_.-])(fig|figure|tab|table|sec|section|chap|chapter)([:_.-]|$)", low):
                continue
            keys.add(_equation_reference_key(label, is_label=True))
            number = re.search(r"\d+(?:\.\d+)+|\d+", label)
            if number:
                keys.add(_equation_reference_key(number.group(0)))
        for tag in re.findall(r"\\tag\{([^{}]+)\}", block):
            keys.add(_equation_reference_key(tag))
    return keys


def _missing_equation_macro() -> str:
    return (
        "\\providecommand{\\kgmissingequation}[2]{\n"
        "  \\textcolor{red}{\\textbf{缺失公式：#2。请导入包含该公式的章节后自动补全。}}\n"
        "}\n"
    )


def _missing_equation_block(ref: dict[str, str]) -> str:
    key = ref.get("key", "")
    label = ref.get("label", key)
    return (
        "\\begin{alertblock}{缺失公式}\n"
        f"\\kgmissingequation{{{key}}}{{{label}}}\n"
        "\\end{alertblock}"
    )


def _missing_equation_marker_pattern() -> re.Pattern[str]:
    return re.compile(
        r"\\begin\{alertblock\}\{(?:缺失公式|Missing Equation|Missing Equations|缂哄け鍏紡)\}\s*"
        r"\\kgmissingequation\{([^{}]+)\}\{([^{}]*)\}\s*"
        r"\\end\{alertblock\}",
        re.DOTALL,
    )


def _mark_missing_equations(latex: str) -> tuple[str, list[dict[str, str]]]:
    text = latex or ""
    refs = _extract_equation_references(text)
    defined = _extract_equation_definition_keys(text)
    already_marked = {match.group(1) for match in _missing_equation_marker_pattern().finditer(text)}
    missing = [ref for ref in refs if ref["key"] not in defined and ref["key"] not in already_marked]
    if not missing:
        return text, []

    text = _ensure_missing_equation_macro(text)
    frames = re.findall(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?[\s\S]*?\\end\{frame\}", text)
    appended: set[str] = set()
    for frame in frames:
        frame_missing = [
            ref for ref in missing
            if ref["key"] not in appended and ref.get("raw") and ref["raw"] in frame
        ]
        if not frame_missing:
            continue
        addition = "\n\n" + "\n\n".join(_missing_equation_block(ref) for ref in frame_missing)
        replacement = frame.replace(r"\end{frame}", addition + "\n\\end{frame}", 1)
        text = text.replace(frame, replacement, 1)
        appended.update(ref["key"] for ref in frame_missing)

    remaining = [ref for ref in missing if ref["key"] not in appended]
    if remaining:
        frame = (
            "\\begin{frame}{Missing Equations}\n"
            + "\n\n".join(_missing_equation_block(ref) for ref in remaining)
            + "\n\\end{frame}"
        )
        text = _insert_frames_before_end_document(text, [frame])
    return text, missing


def _extract_equations_from_source(source: str) -> dict[str, str]:
    equations: dict[str, str] = {}
    patterns = [
        r"\\begin\{(equation|align|alignat|gather|multline)\*?\}[\s\S]*?\\end\{\1\*?\}",
        r"\\\[[\s\S]*?\\\]",
        r"\$\$[\s\S]*?\$\$",
    ]
    text = source or ""
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            block = match.group(0).strip()
            keys = _extract_equation_definition_keys(block)
            before = text[max(0, match.start() - 180):match.start()]
            after = text[match.end():match.end() + 180]
            context = before + " " + after
            for ref in _extract_equation_references(context):
                keys.add(ref["key"])
            for key in keys:
                equations.setdefault(key, block)
    return equations


def _load_equation_index() -> dict[str, list[dict[str, str]]]:
    try:
        data = json.loads(EQUATION_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    normalized: dict[str, list[dict[str, str]]] = {}
    for key, entries in data.items():
        if not isinstance(entries, list):
            continue
        cleaned = []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("latex"):
                cleaned.append({
                    "latex": str(entry.get("latex") or ""),
                    "source_id": str(entry.get("source_id") or ""),
                    "source_title": str(entry.get("source_title") or ""),
                })
        if cleaned:
            normalized[str(key)] = cleaned
    return normalized


def _write_equation_index(index: dict[str, list[dict[str, str]]]) -> None:
    EQUATION_INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_equation_index_from_source(source: str, source_id: str = "", source_title: str = "") -> dict[str, str]:
    equations = _extract_equations_from_source(source)
    if not equations:
        return {}
    index = _load_equation_index()
    for key, latex in equations.items():
        entries = index.setdefault(key, [])
        signature = re.sub(r"\s+", "", latex)
        if not any(re.sub(r"\s+", "", item.get("latex", "")) == signature for item in entries):
            entries.append({
                "latex": latex,
                "source_id": source_id,
                "source_title": source_title,
            })
    _write_equation_index(index)
    return equations


def _known_equation_map(extra_source: str = "", source_id: str = "", source_title: str = "") -> dict[str, str]:
    known: dict[str, str] = {}
    for key, entries in _load_equation_index().items():
        if entries:
            known[key] = entries[0].get("latex", "")
    for path in SAVED_PROJECT_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        latex = str(data.get("latex") or "")
        if latex:
            for key, formula in _extract_equations_from_source(latex).items():
                known.setdefault(key, formula)
    if extra_source:
        known.update(_update_equation_index_from_source(extra_source, source_id, source_title))
    return known


def _attach_equation_number_to_formula(formula: str, key: str) -> str:
    text = (formula or "").strip()
    match = re.match(r"num:(\d+(?:\.\d+)*|\d+)$", key or "")
    if not text or not match or r"\tag{" in text or r"\label{" in text:
        return text
    number = match.group(1)
    display_match = re.fullmatch(r"\\\[\s*([\s\S]*?)\s*\\\]", text)
    if display_match:
        body = display_match.group(1).strip()
        return "\\begin{equation}\n" + body + f"\n\\tag{{{number}}}\n\\end{{equation}}"
    dollar_match = re.fullmatch(r"\$\$\s*([\s\S]*?)\s*\$\$", text)
    if dollar_match:
        body = dollar_match.group(1).strip()
        return "\\begin{equation}\n" + body + f"\n\\tag{{{number}}}\n\\end{{equation}}"
    return text


def _resolve_missing_equations_in_latex(
    latex: str,
    source: str = "",
    known_equations: dict[str, str] | None = None,
    source_id: str = "",
    source_title: str = "",
) -> tuple[str, list[str], list[str]]:
    equations = dict(known_equations or {})
    if source:
        equations.update(_update_equation_index_from_source(source, source_id, source_title))
    resolved: list[str] = []
    missing: list[str] = []
    text = latex or ""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        label = match.group(2) or key
        formula = equations.get(key)
        if formula:
            resolved.append(label)
            return _attach_equation_number_to_formula(formula, key)
        missing.append(label)
        return match.group(0)

    return _missing_equation_marker_pattern().sub(replace, text), resolved, missing


def _apply_equation_reference_policy(
    latex: str,
    source: str = "",
    source_id: str = "",
    source_title: str = "",
) -> tuple[str, list[dict[str, str]], list[str]]:
    known = _known_equation_map(source, source_id, source_title)
    marked, _ = _mark_missing_equations(latex or "")
    resolved_latex, resolved, _ = _resolve_missing_equations_in_latex(marked, known_equations=known)
    final_latex, new_missing = _mark_missing_equations(resolved_latex)
    still_missing = [
        {"key": match.group(1), "label": match.group(2) or match.group(1), "raw": match.group(0)}
        for match in _missing_equation_marker_pattern().finditer(final_latex)
    ]
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for ref in still_missing + new_missing:
        key = ref.get("key", "")
        if key and key not in seen:
            seen.add(key)
            deduped.append(ref)
    return final_latex, deduped, resolved


def _prepare_generated_image_paths(latex: str, figure_assets: dict[str, str]) -> str:
    text = latex or ""
    placeholder_pattern = re.compile(
        r"\\(?:kgimageplaceholder|imageplaceholder|pptimageplaceholder)\s*(?:\[([^\]]*)\])?\s*\{([^{}]*)\}",
        re.DOTALL,
    )

    def replace_placeholder(match: re.Match[str]) -> str:
        options = match.group(1) or ""
        label = match.group(2) or ""
        figure_key = _figure_key_from_placeholder(options, label)
        fig_path = _fig_path_for_label(figure_key or label or options, figure_assets)
        if not fig_path:
            return match.group(0)
        return "\\begin{center}\n  \\includegraphics[width=0.7\\textwidth]{" + fig_path + "}\n\\end{center}"

    text = placeholder_pattern.sub(replace_placeholder, text)

    include_pattern = re.compile(r"(\\includegraphics\s*(?:\[[^\]]*\])?\s*)\{([^{}]+)\}", re.DOTALL)

    def replace_include(match: re.Match[str]) -> str:
        prefix = match.group(1)
        target = match.group(2).strip()
        if target.startswith("fig/"):
            return match.group(0)
        fig_path = _fig_path_for_label(target, figure_assets)
        if not fig_path:
            return match.group(0)
        return f"{prefix}{{{fig_path}}}"

    return include_pattern.sub(replace_include, text)


def _caption_text_from_image_frame_body(body: str, image_command: str) -> str:
    text = (body or "").replace(image_command, " ")
    text = re.sub(r"\\begin\{(?:center|figure|itemize|enumerate|columns)\}(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"\\end\{(?:center|figure|itemize|enumerate|columns)\}", " ", text)
    text = re.sub(r"\\begin\{column\}\{[^{}]*\}", " ", text)
    text = re.sub(r"\\end\{column\}", " ", text)
    text = re.sub(r"\\(?:centering|caption)\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"\\item\b", " ", text)
    text = re.sub(r"\\vspace\{[^{}]*\}", " ", text)
    text = re.sub(r"%.*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "图片说明待补充。"


def _image_dimensions_from_bytes(data: bytes) -> tuple[int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(data):
                break
            size = int.from_bytes(data[index:index + 2], "big")
            if size < 2 or index + size > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(data[index + 3:index + 5], "big")
                width = int.from_bytes(data[index + 5:index + 7], "big")
                return width, height
            index += size
    return None


def _asset_dimensions(value: str) -> tuple[int, int] | None:
    raw = str(value or "").strip()
    if raw.startswith("data:image/") and "," in raw:
        try:
            return _image_dimensions_from_bytes(base64.b64decode(raw.split(",", 1)[1], validate=False))
        except Exception:
            return None
    path = _resolve_uploaded_asset_path(raw)
    if not path:
        return None
    try:
        return _image_dimensions_from_bytes(path.read_bytes())
    except Exception:
        return None


def _image_orientation_for_path(image_path: str, figure_assets: dict[str, str] | None = None) -> str:
    candidates: list[str] = []
    normalized_path = str(image_path or "").replace("\\", "/")
    filename = Path(normalized_path).name.lower()
    figure_key = _normalize_figure_label(normalized_path)
    for label, asset in (figure_assets or {}).items():
        asset_name = Path(str(asset or "").split("?", 1)[0].split("#", 1)[0].replace("\\", "/")).name.lower()
        if (
            _normalize_figure_label(label) == figure_key
            or asset_name == filename
            or _normalize_figure_label(asset_name) == figure_key
        ):
            candidates.append(str(asset or ""))
    candidates.append(normalized_path)
    for candidate in candidates:
        dims = _asset_dimensions(candidate)
        if not dims:
            continue
        width, height = dims
        return "vertical" if height > width else "horizontal"
    return "horizontal"


def _figure_frame_title_for_path(image_path: str, figure_assets: dict[str, str] | None = None) -> str:
    normalized_path = str(image_path or "").replace("\\", "/")
    filename = Path(normalized_path).name
    for label, asset in (figure_assets or {}).items():
        label_text = str(label or "").strip()
        asset_name = Path(str(asset or "").split("?", 1)[0].split("#", 1)[0].replace("\\", "/")).name
        if label_text and (
            asset_name.lower() == filename.lower()
            or _normalize_figure_label(asset_name) == _normalize_figure_label(filename)
            or _normalize_figure_label(label_text) == _normalize_figure_label(filename)
        ):
            normalized = _normalize_figure_label(label_text)
            if normalized.startswith("figure "):
                return "Figure " + normalized.split(" ", 1)[1]
            return label_text

    match = re.search(r"(?:figure|fig\.?|图)?\s*(\d+(?:[._]\d+)?)", filename, re.IGNORECASE)
    if match:
        return "Figure " + match.group(1).replace("_", ".")
    return "Figure"


def _enforce_top_image_bottom_text_layout(latex: str, figure_assets: dict[str, str] | None = None) -> str:
    frame_pattern = re.compile(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?[\s\S]*?\\end\{frame\}")
    image_pattern = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}")

    def replace_frame(match: re.Match[str]) -> str:
        frame = match.group(0)
        if "\\includegraphics" not in frame:
            return frame
        image_match = image_pattern.search(frame)
        if not image_match:
            return frame
        image_path = image_match.group(1).strip()
        body = re.sub(r"^\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?", "", frame)
        body = re.sub(r"\\end\{frame\}\s*$", "", body)
        caption = _caption_text_from_image_frame_body(body, image_match.group(0))
        orientation = _image_orientation_for_path(image_path, figure_assets or {})
        frame_title = _figure_frame_title_for_path(image_path, figure_assets or {})
        if orientation == "vertical":
            return (
                f"\\begin{{frame}}{{{frame_title}}}\n"
                "  \\begin{columns}[T]\n"
                "    \\begin{column}{0.45\\textwidth}\n"
                "      \\centering\n"
                f"      \\safeverticalimage{{{image_path}}}\n"
                "    \\end{column}\n"
                "    \\begin{column}{0.45\\textwidth}\n"
                f"      \\scriptsize {caption}\n"
                "    \\end{column}\n"
                "  \\end{columns}\n"
                "\\end{frame}"
            )
        return (
            f"\\begin{{frame}}{{{frame_title}}}\n"
            "  \\centering\n"
            f"  \\safecontentimage{{{image_path}}}\n"
            "  \\vspace{0.3cm}\n"
            "  \\begin{center}\n"
            f"    \\parbox{{0.95\\textwidth}}{{\\scriptsize {caption}}}\n"
            "  \\end{center}\n"
            "\\end{frame}"
        )

    return frame_pattern.sub(replace_frame, latex or "")


def _image_path_from_frame(frame: str) -> str:
    patterns = [
        r"\\safecontentimage\{([^{}]+)\}",
        r"\\safeverticalimage\{([^{}]+)\}",
        r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, frame or "")
        if match:
            return match.group(1).strip()
    return ""


def _image_merge_key(image_path: str) -> str:
    normalized = str(image_path or "").replace("\\", "/").strip()
    figure = _normalize_figure_label(normalized)
    if figure.startswith("figure "):
        return figure
    return normalized.lower()


def _extract_image_frame_caption(frame: str) -> str:
    parbox = re.search(
        r"\\parbox\{0\.95\\textwidth\}\{\\scriptsize\s*([\s\S]*?)\}\s*\\end\{center\}",
        frame or "",
    )
    if parbox:
        return re.sub(r"\s+", " ", parbox.group(1)).strip()
    column = re.search(r"\\scriptsize\s+([\s\S]*?)\s*\\end\{column\}", frame or "")
    if column:
        return re.sub(r"\s+", " ", column.group(1)).strip()
    return ""


def _append_image_frame_caption(frame: str, caption: str) -> str:
    addition = re.sub(r"\s+", " ", caption or "").strip()
    if not addition or addition in frame:
        return frame

    def replace_parbox(match: re.Match[str]) -> str:
        existing = match.group(1).strip()
        merged = existing + "；" + addition if existing else addition
        return f"\\parbox{{0.95\\textwidth}}{{\\scriptsize {merged}}}\n  \\end{{center}}"

    updated = re.sub(
        r"\\parbox\{0\.95\\textwidth\}\{\\scriptsize\s*([\s\S]*?)\}\s*\\end\{center\}",
        replace_parbox,
        frame,
        count=1,
    )
    if updated != frame:
        return updated

    def replace_column(match: re.Match[str]) -> str:
        existing = match.group(1).strip()
        merged = existing + "；" + addition if existing else addition
        return f"\\scriptsize {merged}\n    \\end{{column}}"

    return re.sub(
        r"\\scriptsize\s+([\s\S]*?)\s*\\end\{column\}",
        replace_column,
        frame,
        count=1,
    )


def _merge_duplicate_image_frames(latex: str) -> str:
    source = latex or ""
    frame_pattern = re.compile(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?[\s\S]*?\\end\{frame\}")
    parts: list[str] = []
    first_frame_part_by_image: dict[str, int] = {}
    last = 0
    for match in frame_pattern.finditer(source):
        parts.append(source[last:match.start()])
        frame = match.group(0)
        image_path = _image_path_from_frame(frame)
        key = _image_merge_key(image_path)
        if image_path and key:
            caption = _extract_image_frame_caption(frame)
            if key in first_frame_part_by_image:
                first_idx = first_frame_part_by_image[key]
                parts[first_idx] = _append_image_frame_caption(parts[first_idx], caption)
            else:
                first_frame_part_by_image[key] = len(parts)
                parts.append(frame)
        else:
            parts.append(frame)
        last = match.end()
    parts.append(source[last:])
    return "".join(parts)


def _resolve_uploaded_asset_path(value: str) -> Optional[Path]:
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw or raw.startswith("data:"):
        return None

    normalized = raw.replace("\\", "/")
    marker = "/beamer-generator/uploads/"
    if normalized.startswith(("http://", "https://")):
        idx = normalized.find(marker)
        if idx == -1:
            return None
        normalized = normalized[idx + len(marker):]
    elif normalized.startswith(marker):
        normalized = normalized.split(marker, 1)[1]
    elif normalized.startswith("/uploads/"):
        normalized = normalized.split("/uploads/", 1)[1]
    elif os.path.isabs(raw):
        candidate = Path(raw).resolve()
        try:
            candidate.relative_to(UPLOAD_DIR.resolve())
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    normalized = normalized.lstrip("./")
    if not normalized or normalized.startswith(".."):
        return None
    candidate = (UPLOAD_DIR / normalized).resolve()
    try:
        candidate.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


def _safe_overleaf_filename(value: str, fallback: str, used: set[str]) -> str:
    raw_name = Path(str(value or "")).name
    stem = Path(raw_name).stem or fallback
    suffix = Path(raw_name).suffix.lower() or ".png"
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", stem).strip(" ._") or fallback
    candidate = f"{stem}{suffix}"
    index = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    used.add(candidate.lower())
    return candidate


def _figure_key_from_placeholder(options: str, label: str) -> str:
    for piece in re.split(r"[,;]", options or ""):
        if "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        if key.strip().lower() in {"figure", "fig", "image"}:
            normalized = _normalize_figure_label(value)
            if normalized:
                return normalized
    return _normalize_figure_label(options) or _normalize_figure_label(label)


def _prepare_overleaf_latex(
    latex: str,
    figure_assets: dict[str, str],
    asset_paths: dict[str, tuple[Path, str]],
) -> str:
    text = _strip_markdown_code_fence(latex or "")

    for label, asset in figure_assets.items():
        key = _normalize_figure_label(label)
        if key not in asset_paths:
            continue
        _, filename = asset_paths[key]
        fig_ref = f"fig/{filename}"
        for original in {str(asset or "").strip(), str(asset or "").replace("\\", "/").strip()}:
            if original:
                text = text.replace(original, fig_ref)

    placeholder_pattern = re.compile(
        r"\\(?:kgimageplaceholder|imageplaceholder|pptimageplaceholder)\s*(?:\[([^\]]*)\])?\s*\{([^{}]*)\}",
        re.DOTALL,
    )

    def replace_placeholder(match: re.Match[str]) -> str:
        options = match.group(1) or ""
        label = match.group(2) or ""
        figure_key = _figure_key_from_placeholder(options, label)
        asset_info = asset_paths.get(figure_key)
        if not asset_info:
            return match.group(0)
        _, filename = asset_info
        return "\\begin{center}\n  \\includegraphics[width=0.7\\textwidth]{fig/" + filename + "}\n\\end{center}"

    return placeholder_pattern.sub(replace_placeholder, text)


def _build_overleaf_package(req: OverleafPackageRequest) -> tuple[bytes, str]:
    latex = (req.latex or "").strip()
    if not latex:
        raise ValueError("没有可发送到 Overleaf 的 LaTeX 内容")

    figure_assets = req.figure_assets or {}
    used_names: set[str] = set()
    asset_paths: dict[str, tuple[Path, str]] = {}
    for index, (label, asset) in enumerate(figure_assets.items(), start=1):
        key = _normalize_figure_label(label)
        if not key:
            continue
        path = _resolve_uploaded_asset_path(str(asset or ""))
        if not path:
            continue
        filename = _safe_overleaf_filename(path.name, f"image_{index}", used_names)
        asset_paths[key] = (path, filename)

    prepared_latex = _prepare_overleaf_latex(latex, figure_assets, asset_paths)
    title = req.chapter_title or req.title or "presentation"
    zip_filename = _safe_saved_project_id(title, "presentation") + "_overleaf.zip"

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.tex", prepared_latex)
        archive.writestr(
            "README.txt",
            "This ZIP was generated by the Knowledge Graph Teaching System for Overleaf.\n"
            "Open main.tex in Overleaf to edit and compile the Beamer presentation.\n",
        )
        for path, filename in asset_paths.values():
            archive.write(path, f"fig/{filename}")
    return buffer.getvalue(), zip_filename


def _render_pdf_bytes_to_pages(pdf_bytes: bytes, dpi: int = 168) -> list[dict]:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local installation
        raise RuntimeError("服务器未安装 PyMuPDF，无法把 PDF 渲染为 PPT 背景图片") from exc

    pages: list[dict] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    zoom = max(0.5, min(4.0, dpi / 72.0))
    matrix = fitz.Matrix(zoom, zoom)
    try:
        for index, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            pages.append({
                "page_index": index,
                "image": "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii"),
                "width": pix.width,
                "height": pix.height,
            })
    finally:
        doc.close()
    return pages


def _latex_compiler_command(tex_filename: str = "main.tex") -> list[str] | None:
    candidate_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
        Path(os.environ.get("ProgramFiles", "")) / "MiKTeX" / "miktex" / "bin" / "x64",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "MiKTeX" / "miktex" / "bin" / "x64",
    ]
    for name in ("xelatex", "pdflatex"):
        exe = shutil.which(name)
        if exe:
            return [exe, "-interaction=nonstopmode", "-halt-on-error", tex_filename]
        exe_name = f"{name}.exe" if os.name == "nt" else name
        for directory in candidate_dirs:
            if not str(directory):
                continue
            candidate = directory / exe_name
            if candidate.exists():
                return [str(candidate), "-interaction=nonstopmode", "-halt-on-error", tex_filename]
    exe = shutil.which("tectonic")
    if exe:
        return [exe, tex_filename]
    return None


def _compile_latex_to_pdf_bytes(latex: str) -> bytes:
    compiler = _latex_compiler_command("main.tex")
    if not compiler:
        raise RuntimeError("当前服务器未安装 xelatex / pdflatex / tectonic，不能直接把 .tex 编译成高保真页面。请先安装 TeX Live/MiKTeX，或在此处导入对应 PDF。")

    with tempfile.TemporaryDirectory(prefix="kg-beamer-render-") as temp_name:
        temp_dir = Path(temp_name)
        tex_path = temp_dir / "main.tex"
        tex_path.write_text(latex or "", encoding="utf-8")
        last_output = ""
        for _ in range(2):
            proc = subprocess.run(
                compiler,
                cwd=str(temp_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
            last_output = proc.stdout or ""
            if proc.returncode != 0:
                tail = "\n".join(last_output.splitlines()[-24:])
                raise RuntimeError("LaTeX 编译失败：\n" + tail)
        pdf_path = temp_dir / "main.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LaTeX 编译未生成 PDF 文件")
        return pdf_path.read_bytes()


def _compile_latex_file_to_pdf_bytes(tex_path: Path) -> bytes:
    tex_path = tex_path.resolve()
    compiler = _latex_compiler_command(tex_path.name)
    if not compiler:
        raise RuntimeError("当前服务器未安装 xelatex / pdflatex / tectonic，不能直接把 .tex 编译成高保真页面。请先安装 TeX Live/MiKTeX，或导入 Overleaf 编译后的 PDF。")

    last_output = ""
    for _ in range(2):
        proc = subprocess.run(
            compiler,
            cwd=str(tex_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        last_output = proc.stdout or ""
        if proc.returncode != 0:
            tail = "\n".join(last_output.splitlines()[-24:])
            raise RuntimeError("LaTeX 编译失败：\n" + tail)
    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        raise RuntimeError("LaTeX 编译未生成 PDF 文件")
    return pdf_path.read_bytes()


def _count_generated_slides(latex: str) -> int:
    try:
        parsed = parse_latex_to_slides(latex or "")
        slides = parsed.get("slides") if isinstance(parsed, dict) else []
        if isinstance(slides, list):
            return len(slides)
    except Exception:
        logger.exception("Failed to count generated slides from LaTeX")
    return len(re.findall(r"\\begin\{frame\}", latex or ""))


def _extract_latex_frames(latex: str) -> list[str]:
    return re.findall(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?[\s\S]*?\\end\{frame\}", latex or "")


def _frame_title(frame: str) -> str:
    match = re.search(r"\\begin\{frame\}(?:\[[^\]]*\])?\{([^{}]*)\}", frame or "")
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    match = re.search(r"\\frametitle\{([^{}]*)\}", frame or "")
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _normalize_frame_body(frame: str) -> str:
    text = re.sub(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", frame or "")
    text = re.sub(r"\\frametitle\{[^{}]*\}", " ", text)
    text = re.sub(r"\\end\{frame\}", " ", text)
    text = re.sub(r"%.*", " ", text)
    text = re.sub(r"\\(?:begin|end)\{[^{}]*\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r" \1 ", text)
    text = re.sub(r"[{}\\$#&_^\[\](),.;:，。；：、（）]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _frame_body_key(frame: str) -> str:
    body = _normalize_frame_body(frame)
    words = re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", body)
    return " ".join(words[:160])


def _frame_content_score(frame: str) -> int:
    body = _normalize_frame_body(frame)
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", body))
    latin_words = len(re.findall(r"[a-z0-9]+", body))
    return cjk_chars + latin_words * 2


def _clean_content_anchor(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"^[-*+]\s+", "", text)
    text = re.sub(r"^\d+[.)、]\s*", "", text)
    text = text.strip(" -:：;；,，。")
    if len(text) > 170:
        text = text[:170].rsplit(" ", 1)[0] or text[:170]
    return text.strip()


def _anchor_key(value: str) -> str:
    text = _clean_content_anchor(value).lower()
    text = re.sub(r"[`*_~#>\[\](){}，。；：、,.!?;:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_content_anchors(content: str, limit: int = 140) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        clean = _clean_content_anchor(raw)
        if not clean:
            return
        score = len(re.findall(r"[\u4e00-\u9fff]", clean)) + len(re.findall(r"[A-Za-z0-9]+", clean)) * 2
        if score < 12:
            return
        key = _anchor_key(clean)
        if not key or key in seen:
            return
        seen.add(key)
        anchors.append(clean)

    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^#{1,6}\s+", line):
            add(line)
            continue
        if re.match(r"^[-*+]\s+", line) or re.match(r"^\d+[.)、]\s+", line):
            add(line)
            continue
        if re.search(r"(Figure|Fig\.?|图|表|Table)\s*[\d.]*", line, re.IGNORECASE):
            add(line)
            continue
        if re.search(r"(\$[^$]+\$|\\\(|\\\[|=|\\frac|\\sum|\\int|\\varphi|\\sigma)", line):
            add(line)
            continue
        if len(line) >= 24 and len(anchors) < limit // 2:
            add(line)
        if len(anchors) >= limit:
            break
    return anchors[:limit]


BIMSA_FIXED_SECTIONS = [
    "Optimal Selection Intensities For Maximizing Long-Term Response",
    "Effects Of Population Structure On Long-Term Response",
    "Asymptotic Response Due To Mutational Input",
]


def _frame_has_anchor(frame: str, anchors: list[str]) -> bool:
    if not anchors:
        return True
    body = _anchor_key(_normalize_frame_body(frame))
    for anchor in anchors:
        key = _anchor_key(anchor)
        if key and (key[:45] in body or body[:80] in key):
            return True
    return False


def _insert_frames_before_end_document(latex: str, frames: list[str]) -> str:
    if not frames:
        return latex
    end_tag = r"\end{document}"
    insert_at = latex.rfind(end_tag)
    addition = "\n\n" + "\n\n".join(frame.strip() for frame in frames if frame.strip()) + "\n\n"
    if insert_at == -1:
        return latex.rstrip() + addition + end_tag + "\n"
    return latex[:insert_at].rstrip() + addition + latex[insert_at:]


def _bimsa_latex_preamble() -> str:
    return r"""\documentclass[10pt, aspectratio=169]{ctexbeamer}
\usetheme{Madrid}

\usepackage{amsmath, amssymb, amsthm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{caption}
\usepackage{hyperref}
\usepackage{tikz}
\usetikzlibrary{shapes.callouts, tikzmark}
\usetikzlibrary{shapes, positioning}

\newcommand{\E}{\mathrm{E}}
\newcommand{\bbE}{\mathbb{E}}
\newcommand{\bbR}{\mathbb{R}}
\newcommand{\cA}{\mathcal{A}}
\newcommand{\cB}{\mathcal{B}}
\newcommand{\cP}{\mathcal{P}}
\newcommand{\cF}{\mathcal{F}}

\definecolor{myline}{RGB}{0,116,112}
\definecolor{myblue}{RGB}{40,100,180}

\providecommand{\safelogoimage}[1]{\IfFileExists{#1}{\includegraphics[height=39pt, keepaspectratio]{#1}}{\fbox{\parbox[c][30pt][c]{65pt}{\centering\tiny Missing\\image}}}}
\providecommand{\safecontentimage}[1]{\IfFileExists{#1}{\includegraphics[width=0.7\textwidth]{#1}}{\fbox{\parbox[c][0.34\textheight][c]{0.7\textwidth}{\centering\scriptsize Missing image\\\texttt{\detokenize{#1}}}}}}
\providecommand{\safeverticalimage}[1]{\IfFileExists{#1}{\includegraphics[width=\textwidth]{#1}}{\fbox{\parbox[c][0.34\textheight][c]{\textwidth}{\centering\scriptsize Missing image\\\texttt{\detokenize{#1}}}}}}

\setbeamertemplate{frametitle}{%
  \vspace*{0.2cm}%
  \begin{beamercolorbox}[wd=\paperwidth, leftskip=0.5cm, rightskip=0.5cm, ht=0.3cm, dp=0pt]{whitebg}%
    \usebeamerfont{frametitle}\textcolor{black}{\insertframetitle}%
  \end{beamercolorbox}%
  \vspace{0pt}%
  \begin{tikzpicture}[remember picture, overlay]
    \draw[myline, line width=1.5pt]
      ([yshift=-1.3cm] current page.north west) -- ([yshift=-1.3cm] current page.north east);
  \end{tikzpicture}%
  \vspace{0.1cm}%
}

\title[]{ Evolutionary Theory on\\ Polygenic Trait}
\subtitle{XII - Long-term Response: 2. Finite Population Size and Mutation (2)}
\author{Qi WU(吴琦)}
\date{2026-5-26}

\setbeamertemplate{title page}{%
  \begin{tikzpicture}[remember picture, overlay]
    \draw[line width=1.5pt, color=myline]
      ([yshift=-40pt] current page.north west) -- ([yshift=-40pt] current page.north east);
    \node[anchor=north west, inner sep=0, minimum width=0.25\paperwidth,
          minimum height=39pt, fill=gray!30, text=black, align=center]
          at (current page.north west) {Public course in BIMSA in 2026 spring semester};
    \node[anchor=north east, inner sep=0] (f3) at ([xshift=-3pt] current page.north east)
          {\safelogoimage{fig/图片2.png}};
    \node[anchor=north east, inner sep=0] at (f3.north west)
          {\safelogoimage{fig/图片1.png}};
  \end{tikzpicture}%
  \vspace*{36pt}
  \begin{center}
    \begin{tikzpicture}
      \node[draw=none, inner sep=8pt, fill=white, text=black,
            align=center, font=\Huge\bfseries] (titlebox) {\inserttitle};
      \node[draw=none, rounded corners=2pt,
            inner sep=8pt, fill=white, text=black,
            align=center, font=\large,
            below=5pt of titlebox] (subtitlebox) {\insertsubtitle};
      \node[below=5pt of subtitlebox.south east, anchor=north east, align=center, text=black] {
        \insertauthor \\[3pt]
        \insertdate
      };
    \end{tikzpicture}
  \end{center}
}
"""


def _bimsa_title_frame() -> str:
    return r"""\setbeamertemplate{footline}{}

{
\setbeamertemplate{footline}{%
  \leavevmode%
  \makebox[\paperwidth][l]{\includegraphics[width=\paperwidth]{fig/图片3.png}}%
}
\begin{frame}
    \titlepage
\end{frame}
}
"""


def _ensure_complete_bimsa_latex(latex: str) -> str:
    text = _strip_markdown_code_fence(latex or "")
    frames = _extract_latex_frames(text)
    has_document = r"\begin{document}" in text and r"\end{document}" in text
    if not has_document:
        body = "\n\n".join(frame.strip() for frame in frames)
        if not body:
            body = text.strip()
        return _bimsa_latex_preamble().rstrip() + "\n\n\\begin{document}\n\n" + _bimsa_title_frame().rstrip() + "\n\n" + body + "\n\n\\end{document}\n"

    if r"\documentclass" not in text:
        text = _bimsa_latex_preamble().rstrip() + "\n\n" + text
    if r"\titlepage" not in text:
        text = text.replace(r"\begin{document}", r"\begin{document}" + "\n\n" + _bimsa_title_frame().rstrip(), 1)
    return text


def _dedupe_latex_frames(latex: str) -> str:
    frames = _extract_latex_frames(latex)
    if not frames:
        return latex
    seen_titles: set[str] = set()
    seen_bodies: set[str] = set()
    replacements: dict[str, str] = {}
    for frame in frames:
        if r"\titlepage" in frame:
            continue
        title_key = _frame_title(frame).lower()
        body_key = _frame_body_key(frame)
        if (title_key and title_key in seen_titles) or (body_key and body_key in seen_bodies):
            replacements[frame] = ""
            continue
        if title_key:
            seen_titles.add(title_key)
        if body_key:
            seen_bodies.add(body_key)
    result = latex
    for frame, replacement in replacements.items():
        result = result.replace(frame, replacement, 1)
    return result


def _escape_latex_text(value: str) -> str:
    text = str(value or "")
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _english_frame_topic_title(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "Core Topic"
    text = text.replace(r"\textbackslash{}", "\\")
    text = text.replace(r"\_", "_")
    text = re.sub(r"\\bar\s*\{\s*\\?(?:imath|i)\s*\}", "Average Selection Intensity", text, flags=re.IGNORECASE)
    text = re.sub(r"\bN\s*_\s*\{?\s*e\s*\}?", "Effective Population Size", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    text = re.sub(r"\\\((.*?)\\\)", r"\1", text)
    text = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = text.replace("{", " ").replace("}", " ").replace("\\", " ")
    text = re.sub(r"[_^]", " ", text)
    text = re.sub(r"[\u4e00-\u9fff]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.")

    low = text.lower()
    if "tradeoff between" in low and "selection intensity" in low and "effective population size" in low:
        return "Tradeoff Between Selection Intensity and Effective Population Size"
    if not re.search(r"[A-Za-z]", text):
        return "Core Topic"
    return text[:90].strip(" -:;,.") or "Core Topic"


def _split_support_points(value: str) -> list[str]:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return []
    parts = re.split(r"[。；;.!?]\s*|(?:\s+-\s+)", raw)
    seen: set[str] = set()
    points: list[str] = []
    for part in parts:
        clean = part.strip(" -,:：;；，。")
        if not clean or clean in seen:
            continue
        seen.add(clean)
        points.append(clean[:120])
    return points


def _topic_items_from_slide(slide: dict) -> list[str]:
    items: list[str] = []
    for item in slide.get("items") or []:
        clean = re.sub(r"\s+", " ", str(item or "")).strip()
        if clean:
            items.append(clean[:120])
    subtitle = re.sub(r"\s+", " ", str(slide.get("subtitle") or "")).strip()
    if subtitle:
        items.append(subtitle[:120])
    for part in _split_support_points(slide.get("notes") or ""):
        items.append(part[:120])
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _build_auto_expansion_frames(latex: str, minimum_slide_count: int, content: str = "") -> str:
    try:
        parsed = parse_latex_to_slides(latex or "")
    except Exception:
        logger.exception("Failed to parse LaTeX for automatic slide expansion")
        return latex

    slides = parsed.get("slides") if isinstance(parsed, dict) else []
    if not isinstance(slides, list) or len(slides) >= minimum_slide_count:
        return latex

    anchors = _extract_content_anchors(content)
    topics: list[dict[str, object]] = []
    for anchor in anchors:
        topics.append({"title": anchor, "items": [anchor]})
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("type") or "").strip().lower()
        if slide_type in {"title", "toc"}:
            continue
        title = _english_frame_topic_title(slide.get("title") or "Core Topic")
        topic_items = _topic_items_from_slide(slide)
        topics.append({"title": title, "items": topic_items or [title]})

    if not topics:
        topics = [{
            "title": "Chapter Topic",
            "items": [
                "梳理本章核心概念与基本定义",
                "解释关键公式、变量含义和使用条件",
                "结合例子说明知识点之间的联系",
                "总结常见误区与课堂复习重点",
            ],
        }]

    templates = [
        ("Background and Motivation", [
            "说明 {topic} 的问题背景，以及它为什么是本章需要优先理解的核心主题。",
            "从研究目标、应用场景和课堂复习角度，梳理 {topic} 与前后知识点的连接。",
            "指出学习 {topic} 时最容易混淆的概念，并给出本页的辨析重点。",
            "结合知识图谱中的相关节点，建立后续公式、图表或例题讲解的上下文。",
        ]),
        ("Definition and Notation", [
            "给出 {topic} 中关键对象、变量和符号的中文解释，保留必要英文术语。",
            "说明每个变量的含义、单位或适用范围，避免只记公式而不理解条件。",
            "把知识图谱中的相关关系转化为定义之间的依赖链条。",
            "总结本页定义在后续推导、图表解读或课堂提问中的作用。",
        ]),
        ("Formula Explanation", [
            "围绕 {topic} 提取核心公式，并解释公式左端与右端分别代表的含义。",
            "逐项说明参数、变量和假设条件，强调哪些量可观测、哪些量由模型给出。",
            "讨论公式成立的前提，以及在什么情况下不能直接套用。",
            "用一句中文教学语言概括该公式传达的主要结论。",
        ]),
        ("Derivation Step", [
            "把 {topic} 的推导拆成前提、变换、结论三个层次，而不是直接给最终结果。",
            "说明每一步变换依赖的定义、近似或假设，帮助学生追踪逻辑来源。",
            "标出推导中容易跳步的位置，并解释该步骤为什么合理。",
            "总结该推导如何服务于本章的主线问题。",
        ]),
        ("Example Walkthrough", [
            "构造一个与 {topic} 相关的小例子，用具体变量展示概念如何落地。",
            "按输入条件、计算过程、结果解释的顺序组织讲解。",
            "指出例子中哪些结论可以推广，哪些只是当前条件下成立。",
            "给出课堂上可追问的问题，帮助检查学生是否真正理解。",
        ]),
        ("Common Mistakes", [
            "列出学习 {topic} 时常见误区，例如混淆变量、忽略条件或过度解释结果。",
            "用对比方式说明正确理解和错误理解之间的差别。",
            "解释这些误区为什么会影响公式使用、图表解读或结论判断。",
            "给出复习时可以自查的判断标准。",
        ]),
        ("Figure and Table Reading", [
            "说明 {topic} 相关图表应先看坐标、变量、趋势和异常点。",
            "把图表信息转化为中文结论，避免只描述视觉现象。",
            "联系知识图谱中的公式或定义，解释图表趋势背后的机制。",
            "总结该图表对本章核心问题提供了什么证据。",
        ]),
        ("Review and Concept Check", [
            "用问题形式回顾 {topic} 的关键定义、公式和适用条件。",
            "设计一个判断题或简短问答，检查学生是否能区分相近概念。",
            "要求学生说明结论背后的原因，而不是只复述术语。",
            "把本页复习点连接到下一页或下一节的学习目标。",
        ]),
    ]
    needed = minimum_slide_count - len(slides)
    new_frames: list[str] = []
    seen_body_keys = {_frame_body_key(frame) for frame in _extract_latex_frames(latex)}
    seen_titles = {_frame_title(frame).lower() for frame in _extract_latex_frames(latex) if _frame_title(frame)}

    idx = 0
    max_attempts = max(needed * 6, 24)
    while len(new_frames) < needed and idx < max_attempts:
        topic = topics[idx % len(topics)]
        section_title = BIMSA_FIXED_SECTIONS[idx % len(BIMSA_FIXED_SECTIONS)]
        topic_title = _english_frame_topic_title(str(topic.get("title") or section_title))
        template_name, template_bullets = templates[idx % len(templates)]
        frame_title_raw = f"{section_title} - {template_name}"
        if frame_title_raw.lower() in seen_titles:
            frame_title_raw = f"{topic_title} - {template_name} {idx + 1}"
        seen_titles.add(frame_title_raw.lower())
        frame_title = _escape_latex_text(frame_title_raw)
        topic_items = [str(item).strip() for item in list(topic.get("items") or []) if str(item).strip()]
        anchor = anchors[idx % len(anchors)] if anchors else (topic_items[idx % len(topic_items)] if topic_items else topic_title)

        bullets = [line.format(topic=topic_title) for line in template_bullets]
        bullets[0] = f"结合原始知识图谱要点“{anchor}”，说明它在固定章节“{section_title}”中的具体作用。"
        if topic_items and topic_items[0] != anchor:
            bullets[1] = f"补充关联要点“{topic_items[idx % len(topic_items)]}”，说明它与本页主题的依赖关系。"

        frame_lines = [f"\\begin{{frame}}{{{frame_title}}}", "  \\begin{itemize}"]
        for bullet in bullets:
            frame_lines.append(f"    \\item {_escape_latex_text(bullet)}")
        frame_lines.extend(["  \\end{itemize}", "\\end{frame}"])
        frame = "\n".join(frame_lines)
        body_key = _frame_body_key(frame)
        if body_key and body_key in seen_body_keys:
            idx += 1
            continue
        if _frame_content_score(frame) < 90:
            idx += 1
            continue
        seen_body_keys.add(body_key)
        new_frames.append(frame)
        idx += 1

    return _insert_frames_before_end_document(latex, new_frames)


def _strip_markdown_code_fence(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:latex|tex)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


async def _repair_latex_with_deepseek(
    *,
    client: DeepSeekClient,
    content: str,
    latex: str,
    target_count: int,
    current_count: int,
    model: str,
) -> str:
    missing = max(0, target_count - current_count)
    if missing <= 0:
        return latex
    batch_missing = min(missing, 12)
    frames = _extract_latex_frames(latex)
    existing_titles = [_frame_title(frame) or f"Slide {idx + 1}" for idx, frame in enumerate(frames)]
    title_list = "\n".join(f"- {title}" for title in existing_titles[:80])
    content_excerpt = content[:18000]
    anchor_list = "\n".join(f"- {anchor}" for anchor in _extract_content_anchors(content, limit=80))
    repair_system_prompt = (
        "你是 LaTeX Beamer 教学课件补页助手。只输出 LaTeX frame 代码，不输出解释、Markdown 代码块或完整文档。"
        "必须遵守：大标题/专业词汇英文，小标题和正文中文；不得重复已有页面标题或正文。"
    )
    repair_user_prompt = f"""
当前 Beamer 目标页数是 {target_count} 页，但已有 {current_count} 页，还缺 {missing} 页。

已有页面标题如下，禁止重复或只改后缀：
{title_list}

请基于下面知识图谱内容，本轮只补充 exactly {batch_missing} 个新的 \\begin{{frame}}...\\end{{frame}}。
要求：
- 只输出 frame 片段，不要输出 \\documentclass、\\begin{{document}} 或 \\end{{document}}。
- 每个 frame 标题必须不同，标题使用英文。
- 每页正文 3-6 个 bullet，正文解释使用中文，专业术语和变量保留英文。
- 每页必须承担不同教学功能：背景、定义、公式解释、推导、例子、图表解读、误区、概念检查、总结等。
- 禁止复制已有页正文；禁止出现正文要点完全相同但标题不同的页面。
- 优先覆盖知识图谱中尚未出现在已有标题中的节点、关系、公式、图表和例子。
- 每页正文必须引用至少一个下面“可用知识锚点”中的具体信息，不能只写“进一步展开”“复习重点”等空泛句子。
- 补充页必须服务于固定三章节之一：{BIMSA_FIXED_SECTIONS[0]}；{BIMSA_FIXED_SECTIONS[1]}；{BIMSA_FIXED_SECTIONS[2]}。
- 不要新增 section，不要输出 Test Title A2、Test title B2 或空白幻灯。

可用知识锚点：
{anchor_list}

知识图谱内容：
{content_excerpt}
""".strip()

    generated_parts: list[str] = []
    async for chunk in client.stream_generate(
        system_prompt=repair_system_prompt,
        user_prompt=repair_user_prompt,
        model=model,
        max_tokens=min(config.MAX_TOKENS, max(4096, batch_missing * 1100)),
        temperature=max(0.2, min(config.TEMPERATURE, 0.6)),
    ):
        generated_parts.append(chunk)
    generated = _strip_markdown_code_fence("".join(generated_parts))
    repair_frames = _extract_latex_frames(generated)
    if not repair_frames:
        return latex

    anchors = _extract_content_anchors(content)
    seen_titles = {_frame_title(frame).lower() for frame in frames if _frame_title(frame)}
    seen_bodies = {_frame_body_key(frame) for frame in frames if _frame_body_key(frame)}
    accepted: list[str] = []
    for frame in repair_frames:
        title = _frame_title(frame).lower()
        body_key = _frame_body_key(frame)
        if title and title in seen_titles:
            continue
        if body_key and body_key in seen_bodies:
            continue
        if _frame_content_score(frame) < 90:
            continue
        if not _frame_has_anchor(frame, anchors):
            logger.info("Rejecting unanchored repair frame: %s", title or "<untitled>")
            continue
        if title:
            seen_titles.add(title)
        if body_key:
            seen_bodies.add(body_key)
        accepted.append(frame)
        if len(accepted) >= batch_missing:
            break
    return _insert_frames_before_end_document(latex, accepted)


@router.post("/api/generate")
async def generate(payload: dict | None = Body(default=None)) -> StreamingResponse:
    payload = payload or {}
    content = _payload_text(payload, "content").strip()
    if not content:
        return _stream_error("请输入文案内容")

    style = _payload_text(payload, "style", "academic").strip() or "academic"
    custom_requirements = _payload_text(payload, "custom_requirements").strip()
    language = _payload_text(payload, "language", "title_terms_en_content_zh").strip() or "title_terms_en_content_zh"
    slide_count = max(1, min(_payload_int(payload, "slide_count", 7), 80))
    figure_assets = _payload_map(payload, "figure_assets")
    selected_sections = _payload_selected_sections(payload)
    selected_sections_requirement = _selected_sections_requirement(selected_sections)
    if selected_sections_requirement:
        custom_requirements = (
            custom_requirements + "\n" + selected_sections_requirement
            if custom_requirements
            else selected_sections_requirement
        )

    system_prompt = prompt_engine.build_system_prompt(
        style=style,
        custom_requirements=custom_requirements,
        slide_count=slide_count,
        language=language,
        figure_assets=figure_assets,
    )
    user_prompt = prompt_engine.build_user_prompt(
        content,
        custom_requirements,
        slide_count=slide_count,
        figure_assets=figure_assets,
    )
    api_key = _payload_text(payload, "api_key").strip() or _deepseek_setting("DEEPSEEK_API_KEY")
    if not api_key:
        return _stream_error("未配置 DeepSeek API Key，请先在网站右上角齿轮设置中保存 API Key")

    base_url = (
        _payload_text(payload, "base_url").strip()
        or _deepseek_setting("DEEPSEEK_API_BASE")
        or _deepseek_setting("DEEPSEEK_BASE_URL")
        or config.DEEPSEEK_BASE_URL
    )
    model = (
        _payload_text(payload, "model").strip()
        or _deepseek_setting("DEEPSEEK_PRO_MODEL")
        or _deepseek_setting("DEEPSEEK_MODEL")
        or config.DEEPSEEK_MODEL
    )
    logger.info("Generating Beamer: base_url=%s, model=%s, content_len=%s", base_url, model, len(content))
    client = DeepSeekClient(api_key=api_key, base_url=base_url)

    async def event_stream():
        yield f'data: {json.dumps({"type": "heartbeat", "content": "connected"})}\n\n'
        try:
            chunk_count = 0
            generated_parts: list[str] = []
            async for chunk_text in client.stream_generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                max_tokens=config.MAX_TOKENS,
                temperature=config.TEMPERATURE,
            ):
                chunk_count += 1
                generated_parts.append(chunk_text)
            latex = _ensure_complete_bimsa_latex("".join(generated_parts))
            latex = _dedupe_latex_frames(latex)
            actual_slide_count = _count_generated_slides(latex)
            repair_attempts = 0
            while actual_slide_count < slide_count and repair_attempts < 4:
                previous_count = actual_slide_count
                repair_attempts += 1
                logger.info(
                    "Generated %s/%s slides; requesting DeepSeek repair pass %s",
                    actual_slide_count,
                    slide_count,
                    repair_attempts,
                )
                repaired = await _repair_latex_with_deepseek(
                    client=client,
                    content=content,
                    latex=latex,
                    target_count=slide_count,
                    current_count=actual_slide_count,
                    model=model,
                )
                latex = _dedupe_latex_frames(repaired)
                actual_slide_count = _count_generated_slides(latex)
                if actual_slide_count <= previous_count:
                    logger.info("DeepSeek repair pass made no progress at %s slides", actual_slide_count)
                    break
            if actual_slide_count < slide_count:
                logger.info("DeepSeek repair still produced %s/%s slides; using local dedup fallback", actual_slide_count, slide_count)
                latex = _build_auto_expansion_frames(latex, slide_count, content=content)
                latex = _dedupe_latex_frames(latex)
                actual_slide_count = _count_generated_slides(latex)
            if actual_slide_count < slide_count:
                logger.info("Local fallback still produced %s/%s slides; applying strict minimum pass", actual_slide_count, slide_count)
                latex = _build_auto_expansion_frames(latex, slide_count, content=content)
                actual_slide_count = _count_generated_slides(latex)
            latex = _prepare_generated_image_paths(latex, figure_assets)
            latex = _enforce_top_image_bottom_text_layout(latex, figure_assets)
            latex = _merge_duplicate_image_frames(latex)
            latex = _ensure_safe_image_macros(latex)
            latex, missing_equations, resolved_equations = _apply_equation_reference_policy(latex)
            if missing_equations:
                logger.info("Marked %s missing equation references", len(missing_equations))
            logger.info("Beamer generation done: %s chunks, %s slides", chunk_count, actual_slide_count)
            data = json.dumps({"type": "chunk", "content": latex}, ensure_ascii=False)
            yield f"data: {data}\n\n"
            yield f'data: {json.dumps({"type": "done", "content": ""})}\n\n'
        except Exception as exc:
            logger.error("Beamer generation error: %s: %s", type(exc).__name__, exc)
            error_msg = str(exc)
            low = error_msg.lower()
            if "connect" in low or "timeout" in low:
                error_msg = f"无法连接 API ({base_url})，请检查网络或 Base URL"
            elif "401" in error_msg or "auth" in low:
                error_msg = "API Key 无效，请检查 Key 是否正确"
            elif "model" in low:
                error_msg = f"模型 '{model}' 不可用，请检查模型名称"
            error_data = json.dumps({"type": "error", "content": error_msg}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/parse-slides")
async def parse_slides(req: ParseRequest) -> JSONResponse:
    try:
        latex, missing_equations, resolved_equations = _apply_equation_reference_policy(req.latex)
        parsed = parse_latex_to_slides(latex)
        parsed["latex"] = latex
        parsed["missing_equations"] = missing_equations
        parsed["resolved_equations"] = resolved_equations
        return JSONResponse(content=parsed)
    except Exception as exc:
        logger.error("Beamer parse error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/render-latex-pages")
async def render_latex_pages(req: RenderLatexRequest) -> JSONResponse:
    try:
        latex = req.latex or ""
        try:
            parsed = parse_latex_to_slides(latex)
        except Exception:
            parsed = {"title": Path(req.filename or "presentation.tex").stem, "slides": []}
        pdf_bytes = _compile_latex_to_pdf_bytes(latex)
        return JSONResponse(content={
            **parsed,
            "latex": latex,
            "missing_equations": [],
            "resolved_equations": [],
            "rendered_pages": _render_pdf_bytes_to_pages(pdf_bytes),
            "render_source": "latex",
            "filename": req.filename,
        })
    except Exception as exc:
        logger.error("Beamer LaTeX render error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/overleaf-package")
@router.post("/api/overleaf-package/")
async def overleaf_package(req: OverleafPackageRequest) -> JSONResponse:
    try:
        zip_bytes, filename = _build_overleaf_package(req)
        snip_uri = "data:application/zip;base64," + base64.b64encode(zip_bytes).decode("ascii")
        return JSONResponse(content={
            "success": True,
            "filename": filename,
            "snip_uri": snip_uri,
            "size": len(zip_bytes),
        })
    except Exception as exc:
        logger.error("Overleaf package error: %s", exc)
        return JSONResponse(content={"success": False, "error": str(exc)}, status_code=500)


@router.post("/api/render-pdf-pages")
async def render_pdf_pages(file: UploadFile = File(...)) -> JSONResponse:
    try:
        if Path(file.filename or "").suffix.lower() != ".pdf":
            return JSONResponse(content={"error": "请选择 PDF 文件"}, status_code=400)
        content = await file.read()
        if not content:
            return JSONResponse(content={"error": "PDF 文件为空"}, status_code=400)
        return JSONResponse(content={
            "success": True,
            "filename": file.filename or "presentation.pdf",
            "rendered_pages": _render_pdf_bytes_to_pages(content),
            "render_source": "pdf",
        })
    except Exception as exc:
        logger.error("Beamer PDF render error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


def _select_uploaded_latex_tex(files: list[UploadFile]) -> UploadFile | None:
    candidates: list[tuple[bool, int, str, UploadFile]] = []
    for upload in files:
        rel_name = (upload.filename or "").replace("\\", "/")
        if Path(rel_name).suffix.lower() not in {".tex", ".latex"}:
            continue
        name = Path(rel_name).name.lower()
        candidates.append((name != "main.tex", rel_name.count("/"), rel_name.lower(), upload))
    candidates.sort(key=lambda item: item[:3])
    return candidates[0][3] if candidates else None


@router.post("/api/render-latex-project")
async def render_latex_project(files: List[UploadFile] = File(...)) -> JSONResponse:
    try:
        if not files:
            return JSONResponse(content={"error": "未收到 LaTeX 项目文件"}, status_code=400)

        tex_upload = _select_uploaded_latex_tex(files)
        if not tex_upload:
            return JSONResponse(content={"error": "项目目录中未找到 .tex 文件"}, status_code=400)

        file_names = [file.filename or "" for file in files]
        root_name = _detect_common_root(file_names)
        if root_name and Path(root_name).suffix:
            root_name = ""

        with tempfile.TemporaryDirectory(prefix="kg-latex-project-") as temp_name:
            temp_dir = Path(temp_name)
            tex_rel_name = ""
            asset_urls: dict[str, str] = {}
            package_id = uuid.uuid4().hex
            package_dir = UPLOAD_DIR / package_id
            package_dir.mkdir(parents=True, exist_ok=True)

            for upload in files:
                raw_name = upload.filename or ""
                rel_name = _normalize_package_rel_path(raw_name, root_name=root_name)
                if not rel_name:
                    continue
                rel_path = Path(rel_name)
                if any(part in ("..", "") for part in rel_path.parts):
                    continue

                data = await upload.read()
                target = temp_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

                if upload is tex_upload:
                    tex_rel_name = rel_path.as_posix()

                if rel_path.suffix.lower() in OVERLEAF_ASSET_EXTENSIONS:
                    upload_target = package_dir / rel_path
                    upload_target.parent.mkdir(parents=True, exist_ok=True)
                    upload_target.write_bytes(data)
                    asset_urls[rel_path.as_posix()] = f"/beamer-generator/uploads/{package_id}/{rel_path.as_posix()}"

            if not tex_rel_name:
                tex_rel_name = _normalize_package_rel_path(tex_upload.filename or "", root_name=root_name)
            tex_path = temp_dir / tex_rel_name
            if not tex_path.exists():
                return JSONResponse(content={"error": "主 .tex 文件无法读取"}, status_code=400)

            latex = _decode_text_bytes(tex_path.read_bytes())
            try:
                parsed = parse_latex_to_slides(latex)
            except Exception:
                parsed = {"title": Path(tex_rel_name).stem, "slides": []}
            pdf_bytes = _compile_latex_file_to_pdf_bytes(tex_path)
            return JSONResponse(content={
                **parsed,
                "success": True,
                "filename": Path(tex_rel_name).name,
                "tex_filename": Path(tex_rel_name).name,
                "latex": latex,
                "asset_urls": asset_urls,
                "asset_base_url": f"/beamer-generator/uploads/{package_id}/",
                "rendered_pages": _render_pdf_bytes_to_pages(pdf_bytes),
                "render_source": "latex_project",
            })
    except Exception as exc:
        logger.error("Beamer LaTeX project render error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


def _decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _clean_markdown_source(text: str) -> str:
    lines = []
    in_front_matter = False
    for index, line in enumerate((text or "").splitlines()):
        if index == 0 and line.strip() == "---":
            in_front_matter = True
            continue
        if in_front_matter:
            if line.strip() == "---":
                in_front_matter = False
            continue
        lines.append(line.rstrip())
    cleaned = "\n".join(lines).strip()
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


def _normalize_package_rel_path(name: str, root_name: str = "") -> str:
    path = Path((name or "").replace("\\", "/"))
    parts = [part for part in path.parts if part not in ("", ".", "/")]
    if root_name and parts and parts[0] == root_name:
        parts = parts[1:]
    while parts and parts[0] in (".", ".."):
        parts = parts[1:]
    return "/".join(parts)


def _detect_common_root(file_names: list[str]) -> str:
    roots = []
    for name in file_names:
        parts = [part for part in Path(name.replace("\\", "/")).parts if part not in ("", ".", "/")]
        if parts:
            roots.append(parts[0])
    if not roots:
        return ""
    first = roots[0]
    if all(root == first for root in roots):
        return first
    return ""


OVERLEAF_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".pdf"}


def _select_overleaf_tex_member(infos: list[zipfile.ZipInfo], root_name: str = "") -> zipfile.ZipInfo | None:
    tex_infos = []
    for info in infos:
        rel_name = _normalize_package_rel_path(info.filename, root_name=root_name)
        if not rel_name or Path(rel_name).suffix.lower() not in {".tex", ".latex"}:
            continue
        name = Path(rel_name).name.lower()
        tex_infos.append((name != "main.tex", rel_name.count("/"), rel_name.lower(), info))
    tex_infos.sort(key=lambda item: item[:3])
    return tex_infos[0][3] if tex_infos else None


def _asset_url_for_graphic_target(target: str, asset_urls: dict[str, str]) -> str:
    raw = str(target or "").strip().strip('"').strip("'")
    if not raw or raw.startswith(("http://", "https://", "data:", "/")):
        return raw
    normalized = raw.replace("\\", "/").lstrip("./")
    normalized = normalized.split("?", 1)[0].split("#", 1)[0]
    key_map = {key.lower(): value for key, value in asset_urls.items()}
    direct = key_map.get(normalized.lower())
    if direct:
        return direct
    if Path(normalized).suffix:
        return raw
    for ext in OVERLEAF_ASSET_EXTENSIONS:
        match = key_map.get((normalized + ext).lower())
        if match:
            return match
    return raw


def _rewrite_latex_graphic_paths_to_upload_urls(latex: str, asset_urls: dict[str, str]) -> str:
    pattern = re.compile(r"(\\includegraphics\s*(?:\[[^\]]*\])?\s*)\{([^{}]+)\}", re.DOTALL)

    def replace(match: re.Match[str]) -> str:
        prefix = match.group(1)
        target = match.group(2)
        rewritten = _asset_url_for_graphic_target(target, asset_urls)
        return f"{prefix}{{{rewritten}}}"

    return pattern.sub(replace, latex or "")


def _import_overleaf_zip_bytes(data: bytes, filename: str) -> dict:
    package_id = uuid.uuid4().hex
    package_dir = UPLOAD_DIR / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    asset_urls: dict[str, str] = {}

    with zipfile.ZipFile(BytesIO(data)) as zf, tempfile.TemporaryDirectory(prefix="kg-overleaf-import-") as temp_name:
        infos = [
            info for info in zf.infolist()
            if not info.is_dir()
            and "__MACOSX/" not in info.filename.replace("\\", "/")
            and not Path(info.filename).name.startswith("._")
        ]
        root_name = _detect_common_root([info.filename for info in infos])
        if root_name and Path(root_name).suffix:
            root_name = ""
        tex_info = _select_overleaf_tex_member(infos, root_name=root_name)
        if not tex_info:
            raise ValueError("Overleaf ZIP 中未找到 .tex 文件")

        temp_dir = Path(temp_name)
        tex_rel_name = ""
        for info in infos:
            rel_name = _normalize_package_rel_path(info.filename, root_name=root_name)
            if not rel_name:
                continue
            rel_path = Path(rel_name)
            if any(part in ("..", "") for part in rel_path.parts):
                continue
            raw = zf.read(info)
            temp_target = temp_dir / rel_path
            temp_target.parent.mkdir(parents=True, exist_ok=True)
            temp_target.write_bytes(raw)

            if info.filename == tex_info.filename:
                tex_rel_name = rel_path.as_posix()

            if rel_path.suffix.lower() in OVERLEAF_ASSET_EXTENSIONS:
                upload_target = package_dir / rel_path
                upload_target.parent.mkdir(parents=True, exist_ok=True)
                upload_target.write_bytes(raw)
                asset_urls[rel_path.as_posix()] = f"/beamer-generator/uploads/{package_id}/{rel_path.as_posix()}"

        if not tex_rel_name:
            tex_rel_name = _normalize_package_rel_path(tex_info.filename, root_name=root_name)
        tex_path = temp_dir / tex_rel_name
        if not tex_path.exists():
            raise ValueError("Overleaf ZIP 中的主 .tex 文件无法读取")

        latex = _decode_text_bytes(tex_path.read_bytes())
        rewritten_latex = _rewrite_latex_graphic_paths_to_upload_urls(latex, asset_urls)
        parsed = parse_latex_to_slides(rewritten_latex)
        result = {
            **parsed,
            "success": True,
            "filename": filename,
            "tex_filename": Path(tex_rel_name).name,
            "latex": rewritten_latex,
            "asset_urls": asset_urls,
            "asset_base_url": f"/beamer-generator/uploads/{package_id}/",
            "render_source": "overleaf_zip",
        }
        try:
            pdf_bytes = _compile_latex_file_to_pdf_bytes(tex_path)
            result["rendered_pages"] = _render_pdf_bytes_to_pages(pdf_bytes)
        except Exception as exc:
            result["render_error"] = str(exc)
        return result


@router.post("/api/import-overleaf-package")
async def import_overleaf_package(file: UploadFile = File(...)) -> JSONResponse:
    try:
        filename = file.filename or "overleaf.zip"
        if Path(filename).suffix.lower() != ".zip":
            return JSONResponse(content={"error": "请选择从 Overleaf 下载的 .zip 源码包"}, status_code=400)
        content = await file.read()
        if not content:
            return JSONResponse(content={"error": "上传文件为空"}, status_code=400)
        return JSONResponse(content=_import_overleaf_zip_bytes(content, filename))
    except zipfile.BadZipFile:
        return JSONResponse(content={"error": "ZIP 文件无法读取，请确认文件未损坏"}, status_code=400)
    except Exception as exc:
        logger.error("Overleaf ZIP import error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/resolve-missing-equations")
async def resolve_missing_equations(payload: dict | None = Body(default=None)) -> JSONResponse:
    try:
        payload = payload or {}
        latex = _payload_text(payload, "latex")
        source = _payload_text(payload, "source")
        filename = _payload_text(payload, "filename") or "supplement"
        if not latex.strip():
            return JSONResponse(content={"error": "当前没有可补全的 LaTeX 内容"}, status_code=400)
        if not source.strip():
            return JSONResponse(content={"error": "补充章节内容为空"}, status_code=400)
        marked_latex, still_missing, resolved = _apply_equation_reference_policy(
            latex,
            source=source,
            source_id=filename,
            source_title=filename,
        )
        return JSONResponse(content={
            "success": True,
            "latex": marked_latex,
            "resolved": resolved,
            "missing": [item.get("label") or item.get("key") for item in still_missing],
            "missing_equations": still_missing,
        })
    except Exception as exc:
        logger.error("Equation resolve error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


def _rewrite_markdown_image_links(text: str, asset_urls: dict[str, str]) -> str:
    pattern = re.compile(r"(!\[[^\]]*?\]\()([^)]+)(\))")

    def replace(match: re.Match[str]) -> str:
        prefix, target, suffix = match.group(1), match.group(2), match.group(3)
        raw_target = target.strip().strip('"').strip("'")
        if raw_target.startswith(("http://", "https://", "data:", "/")):
            return match.group(0)
        normalized = raw_target.lstrip("./")
        normalized = normalized.replace("\\", "/")
        normalized = normalized.split("?", 1)[0].split("#", 1)[0]
        url = asset_urls.get(normalized)
        if not url:
            return match.group(0)
        return f"{prefix}{url}{suffix}"

    return pattern.sub(replace, text or "")


def _store_uploaded_package_files(
    files: list[UploadFile],
    package_id: str,
    require_markdown: bool = True,
) -> tuple[str, dict[str, str], str, str]:
    package_dir = UPLOAD_DIR / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    file_names = [file.filename or "" for file in files]
    root_name = _detect_common_root(file_names)
    asset_urls: dict[str, str] = {}
    markdown_bytes: bytes | None = None
    markdown_name = ""

    for upload in files:
        raw_name = upload.filename or ""
        rel_name = _normalize_package_rel_path(raw_name, root_name=root_name)
        if not rel_name:
            continue
        rel_path = Path(rel_name)
        if any(part in ("..", "") for part in rel_path.parts):
            continue

        target = package_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        data = upload.file.read()
        target.write_bytes(data)
        asset_urls[rel_path.as_posix()] = f"/beamer-generator/uploads/{package_id}/{rel_path.as_posix()}"

        if markdown_bytes is None and rel_path.suffix.lower() in {".md", ".markdown"}:
            markdown_bytes = data
            markdown_name = rel_path.name

    if markdown_bytes is None:
        if not require_markdown:
            return "", asset_urls, "", root_name
        raise HTTPException(status_code=400, detail="未找到 md / markdown 知识图谱文件")

    markdown_text = _clean_markdown_source(_decode_text_bytes(markdown_bytes))
    rewritten = _rewrite_markdown_image_links(markdown_text, asset_urls)
    return rewritten, asset_urls, markdown_name, root_name


def _extract_markdown_from_zip(data: bytes) -> tuple[str, list[str]]:
    contents: list[tuple[str, str]] = []
    with zipfile.ZipFile(BytesIO(data)) as zf:
        infos = [
            info for info in zf.infolist()
            if not info.is_dir()
            and not Path(info.filename).name.startswith("._")
            and Path(info.filename).suffix.lower() in {".md", ".markdown", ".txt"}
        ]
        infos.sort(key=lambda item: item.filename.lower())
        for info in infos:
            raw = zf.read(info)
            text = _clean_markdown_source(_decode_text_bytes(raw))
            if not text:
                continue
            title = Path(info.filename).stem
            contents.append((info.filename, f"# {title}\n\n{text}"))

    merged = "\n\n---\n\n".join(text for _name, text in contents)
    return merged, [name for name, _text in contents]


@router.post("/api/import-markdown-source")
async def import_markdown_source(file: UploadFile = File(...)):
    try:
        filename = file.filename or "source.md"
        ext = Path(filename).suffix.lower()
        content = await file.read()
        if not content:
            return JSONResponse(content={"error": "上传文件为空"}, status_code=400)

        if ext not in {".md", ".markdown"}:
            return JSONResponse(content={"error": "仅支持 .md/.markdown 知识图谱文件"}, status_code=400)

        if ext == ".zip":
            text, files = _extract_markdown_from_zip(content)
            if not text:
                return JSONResponse(content={"error": "压缩包中未找到 .md/.markdown/.txt 文件"}, status_code=400)
            return {
                "filename": filename,
                "files": files,
                "content": text,
                "char_count": len(text),
            }

        if ext not in {".md", ".markdown"}:
            return JSONResponse(content={"error": "仅支持 .md/.markdown/.txt/.zip 文件"}, status_code=400)

        text = _clean_markdown_source(_decode_text_bytes(content))
        return {
            "filename": filename,
            "files": [filename],
            "content": text,
            "char_count": len(text),
        }
    except zipfile.BadZipFile:
        return JSONResponse(content={"error": "ZIP 文件无法读取，请确认文件未损坏"}, status_code=400)
    except Exception as exc:
        logger.error("Beamer markdown import error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/import-knowledge-package")
async def import_knowledge_package(files: List[UploadFile] = File(...)):
    try:
        if not files:
            return JSONResponse(content={"error": "未收到知识图谱文件包"}, status_code=400)

        package_id = uuid.uuid4().hex
        markdown_text, asset_urls, markdown_name, root_name = _store_uploaded_package_files(files, package_id)

        title = ""
        for line in markdown_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                break
        if not title:
            title = Path(markdown_name or root_name or "knowledge-package").stem

        return {
            "success": True,
            "file_name": markdown_name or root_name,
            "graph_type": "knowledge_package",
            "chapter_hint": {
                "title": title,
                "content": markdown_text,
            },
            "markdown_content": markdown_text,
            "parsed": {
                "nodes": 0,
                "relations": 0,
                "files": len(files),
                "assets": max(0, len(files) - 1),
            },
            "result": {
                "package_id": package_id,
                "package_name": root_name or package_id,
                "markdown_file": markdown_name,
                "asset_base_url": f"/beamer-generator/uploads/{package_id}/",
                "asset_urls": asset_urls,
            },
            "message": "知识图谱文件包导入成功",
            "imported_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Beamer knowledge package import error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/api/import-image-package")
async def import_image_package(files: List[UploadFile] = File(...)):
    try:
        if not files:
            return JSONResponse(content={"error": "未收到图片包文件"}, status_code=400)

        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
        image_files = [file for file in files if Path(file.filename or "").suffix.lower() in image_exts]
        if not image_files:
            return JSONResponse(content={"error": "图片包中未找到可用图片文件"}, status_code=400)

        package_id = uuid.uuid4().hex
        _, asset_urls, _, root_name = _store_uploaded_package_files(image_files, package_id, require_markdown=False)

        return {
            "success": True,
            "graph_type": "image_package",
            "package_id": package_id,
            "package_name": root_name or package_id,
            "parsed": {
                "files": len(image_files),
                "assets": len(asset_urls),
            },
            "result": {
                "package_id": package_id,
                "package_name": root_name or package_id,
                "asset_base_url": f"/beamer-generator/uploads/{package_id}/",
                "asset_urls": asset_urls,
            },
            "message": "图片包导入成功",
            "imported_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Beamer image package import error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.options("/api/export-pptx")
@router.options("/api/export-pptx/")
async def export_pptx_options() -> Response:
    return Response(status_code=204)


@router.post("/api/export-pptx")
@router.post("/api/export-pptx/")
async def export_pptx(req: ExportRequest) -> Response:
    try:
        pptx_bytes = generate_pptx(req.model_dump(), upload_dir=str(UPLOAD_DIR))
        return Response(
            content=pptx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": "attachment; filename=presentation.pptx"},
        )
    except Exception as exc:
        logger.error("Beamer export error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.options("/api/save-project")
@router.options("/api/save-project/")
async def save_project_options() -> Response:
    return Response(status_code=204)


@router.post("/api/save-project")
@router.post("/api/save-project/")
async def save_project(req: SaveProjectRequest) -> Response:
    try:
        data = req.model_dump()
        latex = data.pop("latex", "") or ""
        chapter_id = _safe_saved_project_id(data.pop("chapter_id", "") or data.get("title") or "presentation")
        chapter_title = data.pop("chapter_title", "") or data.get("title") or chapter_id
        if latex.strip():
            latex, missing_equations, resolved_equations = _apply_equation_reference_policy(
                latex,
                source_id=chapter_id,
                source_title=chapter_title,
            )
            _update_equation_index_from_source(latex, chapter_id, chapter_title)
            data["missing_equations"] = missing_equations
            data["resolved_equations"] = resolved_equations

        saved_payload = {
            **data,
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "latex": latex,
            "updated_at": datetime.now().isoformat(),
        }
        _saved_project_path(chapter_id).write_text(
            json.dumps(saved_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return JSONResponse(content={
            "success": True,
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "title": saved_payload.get("title") or chapter_title,
            "slide_count": len(saved_payload.get("slides") or []),
            "slides": [
                {
                    "page_index": idx,
                    "title": (slide or {}).get("title") or f"Slide {idx + 1}",
                    "type": (slide or {}).get("type") or "content",
                }
                for idx, slide in enumerate(saved_payload.get("slides") or [])
            ],
            "missing_equations": saved_payload.get("missing_equations") or [],
            "missing_equation_count": len(saved_payload.get("missing_equations") or []),
            "resolved_equations": saved_payload.get("resolved_equations") or [],
            "updated_at": saved_payload["updated_at"],
        })
    except Exception as exc:
        logger.error("Beamer save project error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.get("/api/saved-projects")
async def list_saved_projects() -> JSONResponse:
    projects = []
    for path in sorted(SAVED_PROJECT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        summary = _saved_project_summary(path)
        if summary:
            projects.append(summary)
    return JSONResponse(content={"projects": projects})


@router.get("/api/saved-projects/{chapter_id}")
async def get_saved_project(chapter_id: str) -> JSONResponse:
    path = _saved_project_path(chapter_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Saved PPT project not found")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@router.options("/api/saved-projects/{chapter_id}")
async def delete_saved_project_options(chapter_id: str) -> Response:
    return Response(status_code=204)


@router.delete("/api/saved-projects/{chapter_id}")
async def delete_saved_project(chapter_id: str) -> JSONResponse:
    path = _saved_project_path(chapter_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Saved PPT project not found")
    path.unlink()
    return JSONResponse(content={
        "success": True,
        "chapter_id": _safe_saved_project_id(chapter_id),
    })


@router.get("/api/saved-projects/{chapter_id}/slides/{page_index}")
async def get_saved_project_slide(chapter_id: str, page_index: int) -> JSONResponse:
    path = _saved_project_path(chapter_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Saved PPT project not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    slides = data.get("slides") if isinstance(data.get("slides"), list) else []
    if page_index < 0 or page_index >= len(slides):
        raise HTTPException(status_code=404, detail="Saved PPT slide not found")
    return JSONResponse(content={
        "chapter_id": data.get("chapter_id") or chapter_id,
        "chapter_title": data.get("chapter_title") or data.get("title") or chapter_id,
        "page_index": page_index,
        "slide": slides[page_index],
        "latex": data.get("latex") or "",
    })


@router.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        ext = Path(file.filename or "img.png").suffix or ".png"
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = UPLOAD_DIR / filename
        content = await file.read()
        filepath.write_bytes(content)
        return {
            "url": f"/beamer-generator/uploads/{filename}",
            "filename": filename,
            "size": len(content),
        }
    except Exception as exc:
        logger.error("Beamer image upload error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)
