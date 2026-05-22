"""PPTX 生成器 — 将结构化幻灯片 JSON 转为 .pptx 文件"""
import io
import os
import re
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE

try:
    from PIL import Image as PILImage
except Exception:  # pragma: no cover - optional dependency fallback
    PILImage = None


# 主色调（与 LaTeX 模板一致）
COLOR_MYLINE = RGBColor(0, 116, 112)
COLOR_MYBLUE = RGBColor(40, 100, 180)
COLOR_BLACK = RGBColor(0, 0, 0)
COLOR_WHITE = RGBColor(255, 255, 255)
COLOR_GRAY = RGBColor(153, 153, 153)
COLOR_LIGHT_GRAY = RGBColor(240, 242, 245)

# 16:9 尺寸
SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)
BODY_LEFT = Inches(0.72)
BODY_RIGHT = Inches(0.72)
BODY_TOP = Inches(1.62)
BODY_BOTTOM = Inches(0.46)


def _prepare_text_frame(tf, font_size=None, color=None, bold=False, italic=False, align=None, vertical_anchor=None):
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    if vertical_anchor is not None:
        tf.vertical_anchor = vertical_anchor
    tf.margin_left = Inches(0.04)
    tf.margin_right = Inches(0.04)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    p = tf.paragraphs[0]
    if font_size is not None:
        p.font.size = Pt(font_size)
    if color is not None:
        p.font.color.rgb = color
    p.font.bold = bold
    p.font.italic = italic
    if align is not None:
        p.alignment = align
    return p


def _style_paragraph(p, font_size=None, color=None, bold=False, italic=False, align=None):
    if font_size is not None:
        p.font.size = Pt(font_size)
    if color is not None:
        p.font.color.rgb = color
    p.font.bold = bold
    p.font.italic = italic
    if align is not None:
        p.alignment = align


def _image_size(image_source):
    if PILImage is None:
        return None

    try:
        if isinstance(image_source, (str, bytes, os.PathLike)):
            with PILImage.open(image_source) as img:
                return img.size

        pos = None
        if hasattr(image_source, "tell"):
            try:
                pos = image_source.tell()
            except Exception:
                pos = None
        if hasattr(image_source, "seek"):
            image_source.seek(0)
        with PILImage.open(image_source) as img:
            size = img.size
        if pos is not None and hasattr(image_source, "seek"):
            image_source.seek(pos)
        return size
    except Exception:
        return None


def generate_pptx(slides_data: dict, upload_dir: str = "") -> bytes:
    """
    将结构化幻灯片数据生成 PPTX 二进制内容。

    参数:
        slides_data: parse_latex_to_slides() 返回的字典
        upload_dir: 上传图片的存储目录

    返回: PPTX 文件的 bytes
    """
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    meta = slides_data
    slides = slides_data.get("slides", [])
    figure_asset_paths = _build_figure_asset_lookup(slides_data.get("figure_assets", {}), upload_dir)

    for slide_data in slides:
        slide_type = slide_data.get("type", "content")

        if slide_type == "title":
            _add_title_slide(prs, meta, slide_data)
        elif slide_type == "toc":
            _add_toc_slide(prs, slide_data)
        else:
            _add_content_slide(prs, slide_data, upload_dir, figure_asset_paths)

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()


# ================================================================
#  标题页
# ================================================================
def _add_title_slide(prs: Presentation, meta: dict, slide_data: dict):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白布局

    # 顶部横线
    _add_top_line(slide)

    # 左上角机构标签
    tag = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(3.5), Inches(0.55)
    )
    tag.fill.solid()
    tag.fill.fore_color.rgb = COLOR_LIGHT_GRAY
    tag.line.fill.background()
    tf = tag.text_frame
    p = _prepare_text_frame(tf, font_size=11, color=COLOR_BLACK, align=PP_ALIGN.CENTER, vertical_anchor=MSO_ANCHOR.MIDDLE)
    p.text = "Presentation"

    # 主标题
    title_box = slide.shapes.add_textbox(
        Inches(1.35), Inches(2.05), Inches(10.6), Inches(1.8)
    )
    tf = title_box.text_frame
    p = _prepare_text_frame(tf, font_size=34, color=COLOR_BLACK, bold=True, align=PP_ALIGN.CENTER)
    p.text = meta.get("title", "")

    # 副标题
    if meta.get("subtitle"):
        subtitle_box = slide.shapes.add_textbox(
            Inches(1.9), Inches(3.7), Inches(9.5), Inches(0.8)
        )
        tf = subtitle_box.text_frame
        p = _prepare_text_frame(tf, font_size=19, color=COLOR_BLACK, align=PP_ALIGN.CENTER)
        p.text = meta["subtitle"]

    # 作者 + 日期
    info_parts = []
    if meta.get("author"):
        info_parts.append(meta["author"])
    if meta.get("date"):
        info_parts.append(meta["date"])
    if info_parts:
        info_box = slide.shapes.add_textbox(
            Inches(4.9), Inches(5.0), Inches(5.1), Inches(0.5)
        )
        tf = info_box.text_frame
        p = _prepare_text_frame(tf, font_size=13, color=COLOR_GRAY, align=PP_ALIGN.RIGHT)
        p.text = "  |  ".join(info_parts)


# ================================================================
#  目录导航页
# ================================================================
def _add_toc_slide(prs: Presentation, slide_data: dict):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    _add_top_line(slide)
    _add_frame_title(slide, slide_data.get("title", "Contents"))

    items = slide_data.get("items", [])
    if not items:
        return

    body_box = slide.shapes.add_textbox(
        Inches(2.9), Inches(2.0), Inches(7.6), Inches(4.8)
    )
    tf = body_box.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"{i + 1}.  {item}"
        _style_paragraph(p, font_size=17, color=COLOR_BLACK, align=PP_ALIGN.LEFT)
        p.space_after = Pt(10)


# ================================================================
#  内容页
# ================================================================
def _add_content_slide(prs: Presentation, slide_data: dict, upload_dir: str, figure_asset_paths: dict[str, str]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    _add_top_line(slide)
    _add_frame_title(slide, slide_data.get("title", ""))
    body_left = BODY_LEFT
    body_right = BODY_RIGHT
    body_top = BODY_TOP
    body_bottom = BODY_BOTTOM
    body_width = SLIDE_WIDTH - body_left - body_right
    body_height = SLIDE_HEIGHT - body_top - body_bottom

    # 副标题条（蓝线下方描述）
    if slide_data.get("subtitle"):
        sub_box = slide.shapes.add_textbox(
            Inches(0.6), Inches(1.08), Inches(12.0), Inches(0.4)
        )
        tf = sub_box.text_frame
        p = _prepare_text_frame(tf, font_size=11, color=COLOR_GRAY)
        p.text = f"  {slide_data['subtitle']}"

    # 计算正文区域起始 Y
    body_top = BODY_TOP
    current_y = body_top

    # 表格
    if slide_data.get("table"):
        current_y = _add_table(slide, slide_data["table"], current_y)

    # 列表项
    items = slide_data.get("items", [])
    if items:
        equation_reserve = Inches(0.8 + 0.35 * max(1, len(slide_data.get("equations", []))))
        available_h = max(Inches(0.9), body_top + body_height - current_y - equation_reserve)
        estimated_h = Inches(min(4.0, 0.34 * max(1, len(items)) + 0.25))
        item_box = slide.shapes.add_textbox(
            body_left, current_y, body_width, min(available_h, estimated_h)
        )
        tf = item_box.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"•  {item}"
            _style_paragraph(p, font_size=15, color=COLOR_BLACK)
            p.space_after = Pt(8)
            p.level = 0
        current_y = current_y + min(available_h, estimated_h) + Inches(0.06)

    # 公式（渲染为图片插入，避免在 PPT 中显示 LaTeX 源码）
    equations = slide_data.get("equations", [])
    if equations:
        eq_top = current_y
        for i, eq in enumerate(equations):
            img_stream = _render_equation_image(eq)
            if img_stream:
                top = eq_top + Inches(i * 0.72)
                _add_picture_fit(slide, img_stream, body_left, top, body_width, Inches(0.72))
            else:
                eq_box = slide.shapes.add_textbox(
                    body_left + Inches(0.05), eq_top + Inches(i * 0.55), body_width - Inches(0.1), Inches(0.5)
                )
                tf = eq_box.text_frame
                p = _prepare_text_frame(tf, font_size=14, color=COLOR_MYBLUE, italic=True, align=PP_ALIGN.CENTER)
                p.text = _formula_to_plain_text(eq)

    # 备注（callout 标注内容放在 PPT 备注区）
    if slide_data.get("notes"):
        notes_slide = slide.notes_slide
        notes_tf = notes_slide.notes_text_frame
        notes_tf.text = slide_data["notes"]

    # 图片占位
    images = slide_data.get("images", [])
    for img in images:
        img_path = img.get("path", "")
        if upload_dir:
            img_path = os.path.join(upload_dir, os.path.basename(img_path))
        if os.path.exists(img_path):
            x = _editor_px_to_slide_x(img.get("x", 0))
            y = _editor_px_to_slide_y(img.get("y", 0))
            w = _editor_px_to_slide_x(img.get("width", 200))
            h_px = _safe_float(img.get("height", 0), 0)
            h = _editor_px_to_slide_y(h_px) if h_px > 0 else Inches(1.8)
            _add_picture_fit(slide, img_path, x, y, max(Inches(0.8), w), max(Inches(0.6), h))

    _add_image_placeholders(slide, slide_data.get("placeholders", []), figure_asset_paths, upload_dir)
    _add_textboxes(slide, slide_data.get("textboxes", []))


# ================================================================
#  辅助函数
# ================================================================
def _add_top_line(slide):
    """顶部青色横线"""
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0.95),
        SLIDE_WIDTH, Pt(2.5),
    )
    line.fill.solid()
    line.fill.fore_color.rgb = COLOR_MYLINE
    line.line.fill.background()


def _add_frame_title(slide, title: str):
    """页面标题（横线上方）"""
    title_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(0.4), Inches(12), Inches(0.5)
    )
    tf = title_box.text_frame
    p = _prepare_text_frame(tf, font_size=22, color=COLOR_BLACK, bold=True)
    p.text = title


def _add_table(slide, table_data: dict, top_y) -> float:
    """添加表格，返回表格底部的 Y 坐标"""
    headers = table_data.get("headers", [])
    rows_data = table_data.get("rows", [])
    if not headers:
        return top_y

    n_cols = len(headers)
    n_rows = len(rows_data) + 1  # +1 表头

    table_width = Inches(11)
    table_height = Inches(0.4 * n_rows)
    left = Inches(1)

    table_shape = slide.shapes.add_table(
        n_rows, n_cols, left, top_y, table_width, table_height
    )
    table = table_shape.table

    # 表头
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        tf = cell.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _prepare_text_frame(tf, font_size=13, color=COLOR_WHITE, bold=True, vertical_anchor=MSO_ANCHOR.MIDDLE)
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_MYLINE

    # 数据行
    for i, row in enumerate(rows_data):
        for j, val in enumerate(row):
            if j < n_cols:
                cell = table.cell(i + 1, j)
                cell.text = val
                tf = cell.text_frame
                tf.word_wrap = True
                tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
                _prepare_text_frame(tf, font_size=12, color=COLOR_BLACK, vertical_anchor=MSO_ANCHOR.MIDDLE)
                # 交替行背景
                if i % 2 == 1:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = RGBColor(245, 247, 250)

    return top_y + table_height + Inches(0.3)


def _add_image_placeholders(slide, placeholders: list, figure_asset_paths: dict[str, str], upload_dir: str = ""):
    """Add editable image placeholder boxes from parsed or manually edited data."""
    if not placeholders:
        return

    for ph in placeholders:
        if not isinstance(ph, dict):
            continue
        x = _editor_px_to_slide_x(ph.get("x", 570))
        y = _editor_px_to_slide_y(ph.get("y", 150))
        w = _editor_px_to_slide_x(ph.get("width", 245))
        h = _editor_px_to_slide_y(ph.get("height", 230))
        w = max(Inches(0.8), min(w, SLIDE_WIDTH - x))
        h = max(Inches(0.6), min(h, SLIDE_HEIGHT - y))

        figure_path = _resolve_figure_placeholder_path(ph, figure_asset_paths, upload_dir)
        if figure_path and os.path.exists(figure_path):
            _add_picture_fit(slide, figure_path, x, y, w, h)
            continue

        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(232, 246, 245)
        shape.line.color.rgb = COLOR_MYLINE
        shape.line.width = Pt(1.5)

        tf = shape.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = str(ph.get("label") or "图片占位")
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = COLOR_MYLINE


def _add_textboxes(slide, textboxes: list):
    """Add free-position text boxes saved by the browser PPT editor."""
    if not textboxes:
        return

    for tb in textboxes:
        text = str(tb.get("text", "") if isinstance(tb, dict) else "")
        if not text.strip():
            continue

        x = _editor_px_to_slide_x(tb.get("x", 40))
        y = _editor_px_to_slide_y(tb.get("y", 190))
        w = _editor_px_to_slide_x(tb.get("width", 260))
        h = _editor_px_to_slide_y(tb.get("height", 96))
        w = max(Inches(0.6), min(w, SLIDE_WIDTH - x))
        h = max(Inches(0.25), min(h, SLIDE_HEIGHT - y))

        box = slide.shapes.add_textbox(x, y, w, h)
        tf = box.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.margin_left = Inches(0.06)
        tf.margin_right = Inches(0.06)
        tf.margin_top = Inches(0.03)
        tf.margin_bottom = Inches(0.03)

        bg = _parse_rgb_color(tb.get("bg", ""))
        if bg:
            box.fill.solid()
            box.fill.fore_color.rgb = bg
        else:
            box.fill.background()
        box.line.color.rgb = RGBColor(200, 205, 214)
        box.line.width = Pt(0.5)

        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(_safe_float(tb.get("fontSize", 14), 14))
        p.font.color.rgb = _parse_rgb_color(tb.get("color", "")) or COLOR_BLACK
        p.font.bold = bool(tb.get("bold", False))
        p.font.italic = bool(tb.get("italic", False))
        align = str(tb.get("align", "left") or "left").lower()
        if align == "center":
            p.alignment = PP_ALIGN.CENTER
        elif align == "right":
            p.alignment = PP_ALIGN.RIGHT
        else:
            p.alignment = PP_ALIGN.LEFT


def _build_figure_asset_lookup(figure_assets: dict, upload_dir: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not isinstance(figure_assets, dict):
        return lookup

    for label, asset in figure_assets.items():
        key = _normalize_figure_label(label)
        if not key:
            continue
        path = _resolve_uploaded_asset_path(str(asset or ""), upload_dir)
        if path and os.path.exists(path):
            lookup[key] = path
    return lookup


def _resolve_figure_placeholder_path(ph: dict, figure_asset_paths: dict[str, str], upload_dir: str = "") -> Optional[str]:
    for direct_key in ("asset", "url", "path"):
        direct_path = _resolve_uploaded_asset_path(str(ph.get(direct_key, "") or ""), upload_dir)
        if direct_path and os.path.exists(direct_path):
            return direct_path

    label = _normalize_figure_label(ph.get("figure") or ph.get("label", ""))
    if not label:
        return None
    return figure_asset_paths.get(label)


def _normalize_figure_label(value: str) -> str:
    text = str(value or "")
    match = re.search(r"figure\s*\d+(?:\.\d+)?", text, re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(0)).strip().lower()
    return re.sub(r"\s+", " ", text).strip().lower()


def _resolve_uploaded_asset_path(value: str, upload_dir: str) -> str:
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    if raw.startswith("data:"):
        return ""

    normalized = raw.replace("\\", "/")
    if normalized.startswith("http://") or normalized.startswith("https://"):
        marker = "/beamer-generator/uploads/"
        idx = normalized.find(marker)
        if idx != -1:
            normalized = normalized[idx + len(marker):]
        else:
            return ""

    if normalized.startswith("/beamer-generator/uploads/"):
        normalized = normalized.split("/beamer-generator/uploads/", 1)[1]
    elif normalized.startswith("/uploads/"):
        normalized = normalized.split("/uploads/", 1)[1]
    elif os.path.isabs(raw) and os.path.exists(raw):
        return raw

    normalized = normalized.lstrip("./")
    if not normalized or normalized.startswith(".."):
        return ""

    candidate = Path(upload_dir) / normalized if upload_dir else Path(normalized)
    return str(candidate)


def _add_picture_fit(slide, image_path: str, left, top, box_width, box_height):
    """Insert a picture and keep it contained inside the target box."""
    try:
        size = _image_size(image_path)
        if not size or not size[0] or not size[1]:
            pic = slide.shapes.add_picture(image_path, left, top, width=box_width)
            pic.left = left
            pic.top = top
            return pic

        img_w, img_h = size
        scale = min(float(box_width) / float(img_w), float(box_height) / float(img_h))
        width = Emu(int(img_w * scale))
        height = Emu(int(img_h * scale))
        pic = slide.shapes.add_picture(
            image_path,
            left + Emu(int((int(box_width) - int(width)) / 2)),
            top + Emu(int((int(box_height) - int(height)) / 2)),
            width=width,
            height=height,
        )
        return pic
    except Exception:
        return None


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _editor_px_to_slide_x(value) -> Emu:
    return Emu(int(_safe_float(value, 0) / 860.0 * int(SLIDE_WIDTH)))


def _editor_px_to_slide_y(value) -> Emu:
    return Emu(int(_safe_float(value, 0) / 484.0 * int(SLIDE_HEIGHT)))


def _parse_rgb_color(value: str) -> Optional[RGBColor]:
    s = str(value or "").strip()
    if not s or s in {"transparent", "rgba(0, 0, 0, 0)"}:
        return None
    if s.startswith("#"):
        raw = s[1:]
        if len(raw) == 3:
            raw = "".join(ch * 2 for ch in raw)
        if len(raw) == 6:
            try:
                return RGBColor(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
            except ValueError:
                return None
    match = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([0-9.]+))?\)", s)
    if match:
        if match.group(4) is not None and _safe_float(match.group(4), 1) <= 0:
            return None
        return RGBColor(
            max(0, min(255, int(match.group(1)))),
            max(0, min(255, int(match.group(2)))),
            max(0, min(255, int(match.group(3)))),
        )
    return None


def _render_equation_image(equation: str) -> Optional[io.BytesIO]:
    """将 LaTeX 公式渲染为透明 PNG，供 python-pptx 插入。"""
    lines = _split_equation_lines(equation)
    if not lines:
        return None

    fig_height = max(0.42 * len(lines) + 0.16, 0.52)
    fig = plt.figure(figsize=(10.4, fig_height), dpi=220)
    fig.patch.set_alpha(0)

    try:
      for idx, line in enumerate(lines):
          y = 1 - ((idx + 0.5) / len(lines))
          fig.text(
              0.5,
              y,
              f"${line}$",
              ha="center",
              va="center",
              fontsize=18,
              color="#2864B4",
          )

      out = io.BytesIO()
      fig.savefig(out, format="png", transparent=True, bbox_inches="tight", pad_inches=0.05)
      out.seek(0)
      return out
    except Exception:
      return None
    finally:
      plt.close(fig)


def _split_equation_lines(equation: str) -> list[str]:
    s = str(equation or "").strip()
    if not s:
        return []

    s = re.sub(r"\\begin\{(?:aligned|align|equation|gather|split)\*?\}", "", s)
    s = re.sub(r"\\end\{(?:aligned|align|equation|gather|split)\*?\}", "", s)
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\\nonumber\b", "", s)
    s = re.sub(r"\\\\\[[^\]]*\]", r"\\\\", s)

    raw_lines = re.split(r"\\\\", s)
    result: list[str] = []
    for raw in raw_lines:
        line = raw.strip()
        if not line:
            continue
        tag = ""
        tag_match = re.search(r"\\tag\{([^}]*)\}", line)
        if tag_match:
            tag = tag_match.group(1).strip()
            line = re.sub(r"\\tag\{[^}]*\}", "", line)

        line = line.replace("&", "")
        line = _normalize_fraction_shorthand(line)
        line = _normalize_mathtext_unsupported(line)
        line = re.sub(r"\s+", " ", line).strip()
        if tag:
            line = f"{line}\\quad \\mathrm{{({tag})}}"
        if line:
            result.append(line)

    return result


def _normalize_fraction_shorthand(text: str) -> str:
    # LaTeX 允许 \frac18，matplotlib mathtext 更稳定地接受 \frac{1}{8}。
    return re.sub(r"\\frac\s*([A-Za-z0-9])\s*([A-Za-z0-9])", r"\\frac{\1}{\2}", text)


def _normalize_mathtext_unsupported(text: str) -> str:
    s = text
    s = s.replace(r"\,", r"\ ")
    s = s.replace(r"\;", r"\ ")
    s = s.replace(r"\!", "")
    s = s.replace(r"\quad", r"\ ")
    s = s.replace(r"\qquad", r"\ ")
    # mathtext 对 || 支持有限，按普通竖线显示即可。
    s = s.replace(r"\|", "|")
    return s


def _formula_to_plain_text(equation: str) -> str:
    return "  ".join(_split_equation_lines(equation)) or str(equation or "")
