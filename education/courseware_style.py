from __future__ import annotations

import io
import posixpath
import re
import zipfile
from typing import Any, Dict, List, Optional

MAX_STYLE_REFERENCE_BYTES = 20 * 1024 * 1024
MAX_STYLE_REFERENCE_TEX_BYTES = 256 * 1024
MAX_STYLE_GUIDANCE_CHARS = 2000


def build_style_reference_profile(file_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """Extract a compact, prompt-safe courseware style profile."""
    if not file_bytes:
        return {"success": False, "error": "参考风格文件为空"}
    if len(file_bytes) > MAX_STYLE_REFERENCE_BYTES:
        return {"success": False, "error": "参考风格文件超过 20MB 限制"}

    lower_name = (filename or "").lower()
    if lower_name.endswith(".zip"):
        extracted = _extract_tex_from_zip(file_bytes)
    elif lower_name.endswith(".tex"):
        extracted = {
            "success": True,
            "tex_content": _decode_text(file_bytes[: MAX_STYLE_REFERENCE_TEX_BYTES + 1]),
            "tex_source_file": filename or "reference.tex",
            "archive_file_count": 1,
            "archive_image_count": 0,
            "archive_image_paths": [],
            "truncated": len(file_bytes) > MAX_STYLE_REFERENCE_TEX_BYTES,
        }
    else:
        return {"success": False, "error": "参考风格目前支持 .zip 或 .tex"}

    if not extracted.get("success"):
        return extracted

    tex_content = str(extracted.get("tex_content") or "")
    profile = _profile_from_tex(tex_content)
    profile.update(
        {
            "source_file": extracted.get("tex_source_file") or filename,
            "archive_file_count": extracted.get("archive_file_count", 0),
            "archive_image_count": extracted.get("archive_image_count", 0),
            "archive_image_paths": extracted.get("archive_image_paths", []),
            "truncated": bool(extracted.get("truncated")),
        }
    )
    guidance = build_style_reference_guidance({"profile": profile})
    return {
        "success": True,
        "source_filename": filename,
        "profile": profile,
        "guidance": guidance,
        **({"warning": "参考 TeX 较长，已截断后抽取风格。"} if profile.get("truncated") else {}),
    }


def build_style_reference_guidance(style_reference: Optional[Dict[str, Any]]) -> str:
    if not isinstance(style_reference, dict):
        return ""
    guidance = str(style_reference.get("guidance") or "").strip()
    if guidance:
        return guidance[:MAX_STYLE_GUIDANCE_CHARS]
    profile = style_reference.get("profile") if isinstance(style_reference.get("profile"), dict) else style_reference
    if not isinstance(profile, dict):
        return ""

    parts: List[str] = []
    document_class = profile.get("document_class")
    document_options = profile.get("document_options") or []
    if document_class:
        suffix = f" with options {', '.join(document_options[:4])}" if document_options else ""
        parts.append(f"Use a similar Beamer foundation: {document_class}{suffix}.")
    themes = profile.get("themes") or []
    if themes:
        parts.append("Keep the reference theme family: " + ", ".join(themes[:4]) + ".")
    colors = profile.get("colors") or []
    if colors:
        color_text = ", ".join(
            f"{item.get('name')}={item.get('model')} {item.get('value')}"
            for item in colors[:5]
            if isinstance(item, dict) and item.get("name")
        )
        if color_text:
            parts.append("Use restrained academic colors similar to: " + color_text + ".")
    templates = profile.get("beamertemplates") or []
    if templates:
        parts.append("Mirror these Beamer template conventions when applicable: " + ", ".join(templates[:6]) + ".")
    signals = profile.get("style_signals") or []
    if signals:
        parts.append("Visual style signals to preserve: " + ", ".join(signals[:8]) + ".")
    layout = profile.get("layout_summary") if isinstance(profile.get("layout_summary"), dict) else {}
    if layout:
        parts.append(
            "Prefer the reference pacing and density: "
            f"{layout.get('frame_count', 0)} frames, "
            f"{layout.get('image_frame_count', 0)} image-heavy frames, "
            f"{layout.get('formula_frame_count', 0)} formula-heavy frames, "
            f"{layout.get('columns_frame_count', 0)} column layouts."
        )
    parts.append(
        "Do not copy source course content, authorship, dates, logos, or figure assets; transfer only layout, typography, color, and pacing style."
    )
    return " ".join(part for part in parts if part).strip()[:MAX_STYLE_GUIDANCE_CHARS]


def _extract_tex_from_zip(file_bytes: bytes) -> Dict[str, Any]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        return {"success": False, "error": f"参考 ZIP 解析失败: {exc}"}

    try:
        names = [name for name in archive.namelist() if not name.endswith("/") and not name.startswith("__MACOSX/")]
        tex_name = _select_tex_entry(names)
        if not tex_name:
            return {"success": False, "error": "参考 ZIP 中未找到 .tex 主文件"}
        info = archive.getinfo(tex_name)
        truncated = info.file_size > MAX_STYLE_REFERENCE_TEX_BYTES
        with archive.open(info) as handle:
            tex_bytes = handle.read(MAX_STYLE_REFERENCE_TEX_BYTES + 1)
        image_paths = [
            name
            for name in names
            if posixpath.splitext(name.lower())[1] in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg"}
        ]
        return {
            "success": True,
            "tex_content": _decode_text(tex_bytes[:MAX_STYLE_REFERENCE_TEX_BYTES]),
            "tex_source_file": tex_name,
            "archive_file_count": len(names),
            "archive_image_count": len(image_paths),
            "archive_image_paths": image_paths[:20],
            "truncated": truncated or len(tex_bytes) > MAX_STYLE_REFERENCE_TEX_BYTES,
        }
    finally:
        archive.close()


def _select_tex_entry(names: List[str]) -> str:
    tex_names = [name for name in names if name.lower().endswith(".tex")]
    if not tex_names:
        return ""
    for preferred in ("main.tex", "lecture.tex", "slides.tex", "presentation.tex"):
        match = next((name for name in tex_names if posixpath.basename(name).lower() == preferred), "")
        if match:
            return match
    return sorted(tex_names, key=lambda item: (item.count("/"), len(item), item.lower()))[0]


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _profile_from_tex(tex_content: str) -> Dict[str, Any]:
    preamble = tex_content.split(r"\begin{document}", 1)[0]
    frames = re.findall(r"\\begin\{frame\}[\s\S]*?\\end\{frame\}", tex_content)
    document_class, document_options = _extract_document_class(preamble)
    package_names = _extract_package_names(preamble)
    beamertemplates = _extract_beamertemplates(preamble)
    colors = _extract_colors(preamble)
    layout_summary = _layout_summary(frames)
    style_signals = _style_signals(tex_content, preamble, frames)
    return {
        "document_class": document_class,
        "document_options": document_options,
        "themes": _extract_themes(preamble),
        "packages": package_names[:20],
        "colors": colors,
        "newcommands": _extract_newcommands(preamble)[:20],
        "beamertemplates": beamertemplates,
        "layout_summary": layout_summary,
        "style_signals": style_signals,
        "sample_frame_titles": _extract_frame_titles(frames)[:10],
    }


def _extract_document_class(preamble: str) -> tuple[str, List[str]]:
    match = re.search(r"\\documentclass(?:\[([^\]]*)\])?\{([^}]+)\}", preamble)
    if not match:
        return "", []
    options = [item.strip() for item in str(match.group(1) or "").split(",") if item.strip()]
    return str(match.group(2) or "").strip(), options


def _extract_themes(preamble: str) -> List[str]:
    themes: List[str] = []
    for command in ("usetheme", "usecolortheme", "usefonttheme", "useinnertheme", "useoutertheme"):
        for match in re.finditer(rf"\\{command}(?:\[[^\]]*\])?\{{([^}}]+)\}}", preamble):
            value = str(match.group(1) or "").strip()
            if value:
                themes.append(f"{command}:{value}")
    return themes


def _extract_package_names(preamble: str) -> List[str]:
    names: List[str] = []
    for match in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", preamble):
        names.extend(item.strip() for item in str(match.group(1) or "").split(",") if item.strip())
    return _dedupe(names)


def _extract_colors(preamble: str) -> List[Dict[str, str]]:
    colors: List[Dict[str, str]] = []
    for match in re.finditer(r"\\definecolor\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}", preamble):
        colors.append(
            {
                "name": str(match.group(1) or "").strip(),
                "model": str(match.group(2) or "").strip(),
                "value": str(match.group(3) or "").strip(),
            }
        )
    return colors[:12]


def _extract_newcommands(preamble: str) -> List[str]:
    names = re.findall(r"\\(?:newcommand|renewcommand)\{?\\([A-Za-z@]+)\}?", preamble)
    return _dedupe([f"\\{name}" for name in names])


def _extract_beamertemplates(preamble: str) -> List[str]:
    names = re.findall(r"\\setbeamertemplate\{([^}]+)\}", preamble)
    return _dedupe([str(name).strip() for name in names if str(name).strip()])


def _layout_summary(frames: List[str]) -> Dict[str, int]:
    return {
        "frame_count": len(frames),
        "columns_frame_count": sum(1 for frame in frames if r"\begin{columns}" in frame),
        "image_frame_count": sum(1 for frame in frames if r"\includegraphics" in frame),
        "formula_frame_count": sum(1 for frame in frames if _has_formula(frame)),
        "tikz_frame_count": sum(1 for frame in frames if r"\begin{tikzpicture}" in frame),
        "itemize_frame_count": sum(1 for frame in frames if r"\begin{itemize}" in frame),
    }


def _style_signals(tex_content: str, preamble: str, frames: List[str]) -> List[str]:
    signals: List[str] = []
    combined = preamble + "\n" + "\n".join(frames[:12])
    if "aspectratio=169" in combined or "16:9" in combined:
        signals.append("16:9 widescreen Beamer")
    if "ctexbeamer" in combined or r"\usepackage{ctex}" in combined:
        signals.append("Chinese-capable Beamer setup")
    if "frametitle" in preamble and "current page.north west" in preamble and r"\draw" in preamble:
        signals.append("thin top rule under frame titles")
    if "title page" in preamble and r"\includegraphics" in preamble:
        signals.append("custom title page with institutional logos")
    if "fill=white" in preamble and "text=black" in preamble:
        signals.append("white title blocks with black text")
    if r"\setlength{\itemsep}" in tex_content:
        signals.append("explicit item spacing control")
    if r"\textcolor{black}" in tex_content:
        signals.append("mostly black body text")
    if any(r"\begin{columns}" in frame for frame in frames):
        signals.append("uses columns for figure/text layouts")
    if any(r"\begin{tikzpicture}" in frame for frame in frames):
        signals.append("uses TikZ overlays for precise placement")
    return _dedupe(signals)


def _extract_frame_titles(frames: List[str]) -> List[str]:
    titles: List[str] = []
    for frame in frames:
        match = re.search(r"\\begin\{frame\}(?:\s*(?:<[^>]*>|\[[^\]]*\]))*\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", frame)
        if not match:
            continue
        title = re.sub(r"\\(?:textbf|textit|textcolor)\{(?:[^{}]+)\}\{([^{}]+)\}", r"\1", str(match.group(1)))
        title = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", lambda item: item.group(1) or "", title)
        title = re.sub(r"\s+", " ", title).strip()
        if title:
            titles.append(title)
    return titles


def _has_formula(frame: str) -> bool:
    return any(token in frame for token in (r"\[", r"\begin{equation}", "$$", r"\begin{align}", r"\begin{gather}"))


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
