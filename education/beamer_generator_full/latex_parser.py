"""LaTeX Beamer 解析器 — 将 .tex 源码解析为结构化的幻灯片 JSON"""
import re
from typing import List, Optional


def parse_latex_to_slides(latex: str) -> dict:
    """
    解析 LaTeX Beamer 源码，返回结构化幻灯片数据。
    """
    result = {
        "title": _extract_command(latex, "title") or "Presentation",
        "subtitle": _extract_command(latex, "subtitle") or "",
        "author": _extract_command(latex, "author") or "",
        "date": _extract_command(latex, "date") or "",
        "slides": [],
    }

    doc_match = re.search(r"\\begin\{document\}(.+?)\\end\{document\}", latex, re.DOTALL)
    body = doc_match.group(1) if doc_match else latex

    frames = _extract_frames(body)

    slide_id = 0
    for frame in frames:
        slide = _parse_frame(frame, slide_id)
        if slide:
            result["slides"].append(slide)
            slide_id += 1

    if not result["slides"]:
        result["slides"].append({
            "id": 0,
            "type": "title",
            "title": result["title"],
            "subtitle": result["subtitle"],
            "items": [],
            "equations": [],
            "table": None,
            "placeholders": [],
            "notes": f"{result['author']}  {result['date']}",
        })

    return result


def _extract_command(latex: str, cmd: str) -> Optional[str]:
    """提取 LaTeX 命令参数，支持嵌套花括号"""
    # 找到 \cmd 或 \cmd[...] 后面的 { ，然后手动匹配花括号
    pattern = rf"\\{cmd}(?:\[[^\]]*\])?\{{"
    match = re.search(pattern, latex)
    if not match:
        return None
    start = match.end()
    content = _match_braces(latex, start - 1)
    if content:
        return _clean_latex_text(content)
    return None


def _match_braces(text: str, open_pos: int) -> Optional[str]:
    """从 open_pos 位置的 { 开始，匹配到对应的 }，返回内部内容"""
    if open_pos >= len(text) or text[open_pos] != '{':
        return None
    depth = 0
    i = open_pos
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[open_pos + 1:i]
        i += 1
    return None


def _extract_frames(body: str) -> List[str]:
    """提取所有 frame"""
    frames = []
    pattern = r"\\begin\{frame\}(.*?)\\end\{frame\}"
    last_end = 0
    for m in re.finditer(pattern, body, re.DOTALL):
        frame_text = m.group(0)
        prefix = body[last_end:m.start()]
        if _looks_like_review_background_prefix(prefix):
            frame_text = "%__KG_REVIEW_BACKGROUND__\n" + frame_text
        frames.append(frame_text)
        last_end = m.end()
    return frames


def _looks_like_review_background_prefix(prefix: str) -> bool:
    """Detect frames wrapped by the browser's review-background template."""
    if not prefix:
        return False
    tail = prefix[-4000:]
    if "__KG_REVIEW_BACKGROUND__" in tail:
        return True
    has_background = r"\setbeamertemplate{background}" in tail
    has_review_marker = "复习内容空白幻灯" in tail or r"\def\backcolor{gray!30}" in tail
    return has_background and has_review_marker


def _parse_frame(frame_text: str, slide_id: int) -> Optional[dict]:
    """解析单个 frame"""
    review_background = "%__KG_REVIEW_BACKGROUND__" in frame_text
    # ---- 标题提取（支持嵌套花括号）----
    title = ""
    header_match = re.search(r"\\begin\{frame\}\s*\{", frame_text)
    if header_match:
        content = _match_braces(frame_text, header_match.end() - 1)
        if content:
            title = _clean_frame_title_text(content)

    ft_match = re.search(r"\\frametitle\{", frame_text)
    if ft_match:
        content = _match_braces(frame_text, ft_match.end() - 1)
        if content:
            title = _clean_frame_title_text(content)

    # ---- 类型识别 ----
    frame_type = "content"
    if "\\titlepage" in frame_text:
        frame_type = "title"
    elif _is_toc_frame(frame_text):
        frame_type = "toc"

    # ---- 副标题（蓝线下方 TikZ 小字）----
    subtitle = ""
    sub_match = re.search(
        r"\\node\[anchor=north west.*?\]\s*\{.*?\\item\s+(.+?)\n",
        frame_text, re.DOTALL
    )
    if sub_match:
        subtitle = _clean_latex_text(sub_match.group(1))

    # ---- 提取各类内容 ----
    items = _extract_items(frame_text)
    equations = _extract_equations(frame_text)
    table = _extract_table(frame_text)
    placeholders = _extract_image_placeholders(frame_text)
    images = _extract_includegraphics(frame_text)
    callouts = _extract_callouts(frame_text)
    overview = _extract_overview(frame_text)

    notes_parts = []
    if overview:
        notes_parts.append(overview)
    return {
        "id": slide_id,
        "type": frame_type,
        "title": title,
        "subtitle": subtitle,
        "items": items,
        "equations": equations,
        "table": table,
        "images": images,
        "placeholders": placeholders,
        "callouts": callouts,
        "reviewBackground": review_background,
        "notes": "\n".join(notes_parts) if notes_parts else "",
    }


def _is_toc_frame(frame_text: str) -> bool:
    """判断是否为目录导航页"""
    gray_count = frame_text.count("\\textcolor{gray}")
    black_count = frame_text.count("\\textcolor{black}")
    has_textbf_num = bool(re.search(r"\\textbf\{\d+\.\}", frame_text))
    return (gray_count + black_count >= 3) and has_textbf_num


def _extract_items(frame_text: str) -> List[str]:
    """提取 itemize 列表中的有意义文本"""
    items = []

    # ---- 第一步：逐行预清理，彻底移除干扰内容 ----
    lines = frame_text.split("\n")
    clean_lines = []
    in_tikz = 0  # tikzpicture 嵌套深度

    for line in lines:
        stripped = line.strip()

        # 跟踪 tikzpicture 环境（跳过其中所有内容）
        if "\\begin{tikzpicture}" in stripped:
            in_tikz += 1
        if in_tikz > 0:
            if "\\end{tikzpicture}" in stripped:
                in_tikz -= 1
            continue

        # 跳过 \setlength 行（根源问题：\itemsep 包含 \item 子串）
        if "\\setlength" in stripped:
            continue
        # 跳过纯格式设置行
        if stripped.startswith("\\vspace") or stripped.startswith("\\vfill"):
            continue
        if stripped.startswith("\\begin{minipage}") or stripped.startswith("\\end{minipage}"):
            continue
        if stripped.startswith("\\begin{center}") or stripped.startswith("\\end{center}"):
            continue
        # 跳过 onslide 只包含 tikz 的行
        if stripped.startswith("\\onslide") and "tikzpicture" in stripped:
            continue

        clean_lines.append(line)

    cleaned_frame = _remove_display_math_blocks("\n".join(clean_lines))

    # ---- 第二步：按 \item 分割提取内容 ----
    # 使用自定义分割：正确处理方括号内嵌套花括号的情况
    # 如 \item[\textcolor{black}{\textbf{1.}}]
    item_positions = _find_real_items(cleaned_frame)

    for i, pos in enumerate(item_positions):
        # 内容从当前 \item 标记结束到下一个 \item 或 \end{itemize}/\end{frame}
        start = pos
        end = item_positions[i + 1] if i + 1 < len(item_positions) else len(cleaned_frame)
        chunk = cleaned_frame[start:end]

        # 截断到 \end{itemize} 或 \end{frame}
        for stop in [r"\end{itemize}", r"\end{enumerate}", r"\end{frame}"]:
            stop_idx = chunk.find(stop)
            if stop_idx != -1:
                chunk = chunk[:stop_idx]

        cleaned = _clean_latex_text(chunk.strip())

        if not cleaned or len(cleaned) <= 1:
            continue
        if _is_format_junk(cleaned):
            continue

        items.append(cleaned)

    return items


def _find_real_items(text: str) -> List[int]:
    """
    找到所有真正的 \\item 位置（返回 item 内容开始的位置）。
    正确跳过 \\item[...] 中的方括号参数（包含嵌套花括号的情况）。
    """
    positions = []
    i = 0
    while i < len(text):
        # 查找下一个 \item
        idx = text.find("\\item", i)
        if idx == -1:
            break

        # 确保是 \item 而不是 \itemsep 等
        after = idx + 5
        if after < len(text) and text[after].isalpha():
            # \itemsep, \itemize 等 — 不是 \item，跳过
            i = after
            continue

        # 跳过 overlay <N->
        pos = after
        if pos < len(text) and text[pos] == '<':
            close = text.find('>', pos)
            if close != -1:
                pos = close + 1

        # 跳过空白
        while pos < len(text) and text[pos] in ' \t':
            pos += 1

        # 跳过方括号参数 [...] （支持嵌套花括号）
        if pos < len(text) and text[pos] == '[':
            depth_brace = 0
            pos += 1  # 跳过 [
            while pos < len(text):
                ch = text[pos]
                if ch == '{':
                    depth_brace += 1
                elif ch == '}':
                    depth_brace -= 1
                elif ch == ']' and depth_brace == 0:
                    pos += 1  # 跳过 ]
                    break
                pos += 1

        # 跳过空白
        while pos < len(text) and text[pos] in ' \t':
            pos += 1

        # pos 现在指向真正的 item 内容开始位置
        positions.append(pos)
        i = pos

    return positions


def _is_format_junk(text: str) -> bool:
    """判断是否为纯格式残留（不应作为 item 展示）"""
    junk_patterns = [
        r"^\s*$",                         # 空白
        r"^\\",                           # 以反斜杠命令开头
        r"^\{",                           # 以花括号开头
        r"^[0-9]+\.?\s*$",               # 纯数字
        r"^-\s*$",                        # 纯短横线
        r"^sep",                          # \setlength 残留的 sep
        r"^\d+\.?\d*\s*$",               # 纯数值
    ]
    for p in junk_patterns:
        if re.match(p, text):
            return True
    # 太短且不像真正内容
    if len(text) <= 3 and not any(c.isalpha() for c in text):
        return True
    return False


def _remove_display_math_blocks(text: str) -> str:
    """从正文提取源中移除显示公式，避免公式源码混进普通文案。"""
    s = re.sub(r"(?<!\\)\\\[[\s\S]*?(?<!\\)\\\]", "\n", text)
    s = re.sub(r"\$\$[\s\S]*?\$\$", "\n", s)
    s = re.sub(r"\\begin\{(?:align|equation|gather|multline)\*?\}[\s\S]*?\\end\{(?:align|equation|gather|multline)\*?\}", "\n", s)
    # 处理 AI 偶尔漏掉 \] 的情况：从 \[ 到当前 frame 末尾的内容按公式处理，不进入正文 item。
    s = re.sub(r"(?<!\\)\\\[[\s\S]*?(?=\\end\{frame\}|$)", "\n", s)
    return s


def _extract_equations(frame_text: str) -> List[str]:
    """提取数学公式"""
    equations = []
    for m in re.finditer(r"(?<!\\)\\\[(.*?)(?<!\\)\\\]", frame_text, re.DOTALL):
        eq = _clean_latex_equation(m.group(1))
        if _is_readable_equation(eq) and not _has_equivalent_equation(equations, eq):
            equations.append(eq)
    for m in re.finditer(
        r"\\begin\{align\*?\}(.*?)\\end\{align\*?\}", frame_text, re.DOTALL
    ):
        eq = _clean_latex_equation(m.group(1))
        if _is_readable_equation(eq) and not _has_equivalent_equation(equations, eq):
            equations.append(eq)
    return equations


def _clean_latex_equation(text: str) -> str:
    """清理公式块中的排版命令和意外混入的正文包装。"""
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"^\[\s*", "", s)
    s = re.sub(r"(?<!\\)\\\[", "", s)
    for pattern in [
        r"(?<!\\)\\\]",
        r"\\onslide<[^>]*>\s*\{",
        r"\\only<[^>]*>\s*\{",
        r"\\uncover<[^>]*>\s*\{",
        r"\\pause\b",
        r"\\begin\{tikzpicture\}",
        r"\\begin\{itemize\}",
        r"\\begin\{enumerate\}",
        r"\\begin\{description\}",
        r"\\end\{frame\}",
        r"\\item\b",
        r"\\callout\b",
    ]:
        m = re.search(pattern, s, re.DOTALL)
        if m:
            s = s[:m.start()]
    s = re.sub(r"%[^\n]*", "", s)
    s = re.sub(r"\\(?:begin|end)\{(?:center|minipage|itemize|enumerate|description)\}(?:\{[^}]*\}|\[[^\]]*\])*", "", s)
    s = re.sub(r"\\vspace\*?\{[^}]*\}", "", s)
    s = re.sub(r"\\hspace\*?\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:centering|vfill|hfill|noindent|par)\b", "", s)
    s = re.sub(r"\\nonumber\b", "", s)
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\\tikzmark\{[^}]*\}", "", s)
    s = re.sub(r"\\node(?:\[[^\]]*\])?\{[^{}]*\}", "", s)
    s = re.sub(r"\\end\{tikzpicture\}", "", s)
    s = re.sub(r"\\onslide<[^>]*>", "", s)
    s = re.sub(r"\\\\(?:\[[^\]]*\])?", r" \\\\ ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _equation_signature(eq: str) -> str:
    s = str(eq or "")
    s = re.sub(r"^\[\s*", "", s)
    s = re.sub(r"(?<!\\)\\\[|(?<!\\)\\\]", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def _has_equivalent_equation(equations: List[str], eq: str) -> bool:
    sig = _equation_signature(eq)
    return bool(sig) and any(_equation_signature(existing) == sig for existing in equations)


def _is_readable_equation(eq: str) -> bool:
    """过滤掉误混入公式框的正文、TikZ 和 Beamer overlay 片段。"""
    if not eq:
        return False
    s = eq.strip()
    if len(s) < 2:
        return False
    if len(s) > 420:
        return False
    forbidden = [
        r"\\begin\{",
        r"\\end\{",
        r"\\item\b",
        r"\\onslide",
        r"\\only",
        r"\\uncover",
        r"\\node\b",
        r"\\tikz",
        r"callout",
        r"pic cs:",
    ]
    if any(re.search(p, s) for p in forbidden):
        return False
    math_markers = [
        r"[=<>]",
        r"[_^]",
        r"\\(?:frac|sqrt|sum|prod|int|lim|beta|alpha|gamma|delta|theta|lambda|mu|sigma|phi|omega|bar|overline|hat|vec|tilde|partial|nabla|cdot|times|leq|geq|neq|approx|infty|left|right)\b",
    ]
    if not any(re.search(p, s) for p in math_markers):
        return False
    letters = re.findall(r"[A-Za-z]", s)
    spaces = s.count(" ")
    if letters and spaces > max(12, len(letters) * 0.55):
        return False
    return True


def _extract_table(frame_text: str) -> Optional[dict]:
    """提取表格结构"""
    table_match = re.search(
        r"\\begin\{tabular\}\{([^}]+)\}(.*?)\\end\{tabular\}",
        frame_text, re.DOTALL
    )
    if not table_match:
        return None

    table_body = table_match.group(2)
    rows = []
    for line in table_body.split("\\\\"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"\\(?:toprule|midrule|bottomrule|hline)", "", line).strip()
        if not line:
            continue
        cells = [_clean_latex_text(c.strip()) for c in line.split("&")]
        if any(c for c in cells):
            rows.append(cells)

    if not rows:
        return None

    return {
        "headers": rows[0],
        "rows": rows[1:] if len(rows) > 1 else [],
    }


def _extract_image_placeholders(frame_text: str) -> List[dict]:
    """Extract structured image placeholder commands for PPT editing."""
    placeholders = []
    pattern = re.compile(r"\\(?:kgimageplaceholder|imageplaceholder|pptimageplaceholder)\s*(?:\[([^\]]*)\])?\s*\{", re.DOTALL)
    for match in pattern.finditer(frame_text):
        label = _match_braces(frame_text, match.end() - 1)
        if label is None:
            continue
        location = (match.group(1) or "right").strip() or "right"
        options = _parse_placeholder_options(location)
        box = _placeholder_box_from_location(options.get("position") or location)
        figure_label = _clean_latex_text(options.get("figure") or "")
        box.update({
            "type": "image",
            "label": _clean_latex_text(label) or figure_label or "图片占位",
            "position": options.get("position") or location,
        })
        if figure_label:
            box["figure"] = figure_label
        if options.get("page"):
            box["page"] = options["page"]
        placeholders.append(box)
    return placeholders


def _extract_includegraphics(frame_text: str) -> List[dict]:
    """Extract raw includegraphics commands so real images survive export."""
    images: List[dict] = []
    pattern = re.compile(r"\\includegraphics(?:\[([^\]]*)\])?\{([^}]*)\}", re.DOTALL)
    for match in pattern.finditer(frame_text):
        path = _clean_latex_text(match.group(2) or "")
        if not path:
            continue
        options = match.group(1) or ""
        width = 200.0
        height = 160.0
        width_match = re.search(r"width\s*=\s*([^,\]]+)", options)
        height_match = re.search(r"height\s*=\s*([^,\]]+)", options)
        x_match = re.search(r"(?:^|,)\s*x\s*=\s*([^,\]]+)", options)
        y_match = re.search(r"(?:^|,)\s*y\s*=\s*([^,\]]+)", options)
        if width_match:
            width = _estimate_editor_px_from_latex_dimension(width_match.group(1), width)
        if height_match:
            height = _estimate_editor_px_from_latex_dimension(height_match.group(1), height)
        x = _estimate_editor_px_from_latex_dimension(x_match.group(1), 40.0) if x_match else 40.0
        y = _estimate_editor_px_from_latex_dimension(y_match.group(1), 170.0) if y_match else 170.0
        images.append({"path": path, "x": x, "y": y, "width": width, "height": height})
    return images


def _merge_implicit_figure_placeholders(frame_text: str, placeholders: List[dict]) -> List[dict]:
    """If a frame mentions Figure 26.x but has no structured placeholder, add one."""
    result = list(placeholders or [])
    seen = {
        _normalize_figure_label(ph.get("figure") or ph.get("label", ""))
        for ph in result
        if isinstance(ph, dict)
    }
    for label in _extract_figure_refs(frame_text):
        key = _normalize_figure_label(label)
        if not key or key in seen:
            continue
        box = _placeholder_box_from_location("right")
        box.update({
            "type": "image",
            "label": label,
            "figure": label,
            "position": "right",
        })
        result.append(box)
        seen.add(key)
    return result


def _extract_figure_refs(text: str) -> List[str]:
    refs: List[str] = []
    seen = set()
    for match in re.finditer(r"(?:\bFigure\b|\bFig\.?|图)\s*\d+(?:\.\d+)?", text or "", re.IGNORECASE):
        num_match = re.search(r"\d+(?:\.\d+)?", match.group(0))
        label = f"Figure {num_match.group(0)}" if num_match else re.sub(r"\s+", " ", match.group(0)).strip()
        key = _normalize_figure_label(label)
        if key in seen:
            continue
        seen.add(key)
        refs.append(label)
    return refs


def _normalize_figure_label(value: str) -> str:
    match = re.search(r"(?:\bfigure\b|\bfig\.?|图)\s*\d+(?:\.\d+)?", str(value or ""), re.IGNORECASE)
    if match:
        num_match = re.search(r"\d+(?:\.\d+)?", match.group(0))
        if num_match:
            return f"figure {num_match.group(0)}"
        return re.sub(r"\s+", " ", match.group(0)).strip().lower()
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _parse_placeholder_options(location: str) -> dict:
    raw = str(location or "").strip()
    if not raw:
        return {"position": "right"}

    result = {"position": "right"}
    tokens = [t.strip() for t in re.split(r"[;,]+", raw) if t.strip()]
    for token in tokens:
        kv = re.match(r"([a-zA-Z_]+)\s*=\s*(.+)", token)
        if kv:
            key = kv.group(1).strip().lower()
            value = kv.group(2).strip()
            if key in {"figure", "label", "asset", "ref"}:
                result["figure"] = value
            elif key == "page":
                try:
                    result["page"] = int(float(value))
                except ValueError:
                    pass
            elif key in {"position", "loc", "place"}:
                result["position"] = value
            continue

        lower = token.lower()
        if lower in {"right", "left", "center", "top-right", "top-left", "bottom-right", "bottom-left",
                     "upper-right", "upper-left", "lower-right", "lower-left"}:
            result["position"] = token

    return result


def _placeholder_box_from_location(location: str) -> dict:
    loc = (location or "right").lower().replace("_", "-").strip()
    presets = {
        "right": {"x": 500, "y": 120, "width": 235, "height": 165},
        "left": {"x": 45, "y": 120, "width": 235, "height": 165},
        "center": {"x": 310, "y": 140, "width": 240, "height": 170},
        "top-right": {"x": 500, "y": 90, "width": 235, "height": 150},
        "top-left": {"x": 45, "y": 90, "width": 235, "height": 150},
        "bottom-right": {"x": 500, "y": 285, "width": 235, "height": 145},
        "bottom-left": {"x": 45, "y": 285, "width": 235, "height": 145},
    }
    if loc in {"right-top", "upper-right"}:
        loc = "top-right"
    elif loc in {"left-top", "upper-left"}:
        loc = "top-left"
    elif loc in {"right-bottom", "lower-right"}:
        loc = "bottom-right"
    elif loc in {"left-bottom", "lower-left"}:
        loc = "bottom-left"

    box = dict(presets.get(loc, presets["right"]))
    custom = _parse_placeholder_custom_box(location)
    box.update(custom)
    return box


def _parse_placeholder_custom_box(location: str) -> dict:
    result = {}
    for key, value in re.findall(r"\b(x|y|w|width|h|height)\s*=\s*([0-9.]+)", location or "", re.IGNORECASE):
        n = float(value)
        if key.lower() == "x":
            result["x"] = n
        elif key.lower() == "y":
            result["y"] = n
        elif key.lower() in {"w", "width"}:
            result["width"] = n
        elif key.lower() in {"h", "height"}:
            result["height"] = n
    return result


def _extract_callouts(frame_text: str) -> List[dict]:
    """提取 tikz callout 标注"""
    callouts = []
    pattern = r"\\node\[(?P<opts>[^\]]*rectangle callout[^\]]*)\]\s*at\s*\([\s\S]*?\)\s*\{(?P<text>.*?)\}\s*;"
    for m in re.finditer(pattern, frame_text, re.DOTALL):
        opts = m.group("opts")
        pointer = re.search(r"cs:([A-Za-z0-9_:-]+)", opts)
        width_match = re.search(r"text width\s*=\s*([0-9.]+\s*(?:cm|mm|pt|px|in)?)", opts)
        align_match = re.search(r"align\s*=\s*(left|right|center)", opts)
        width = _estimate_editor_px_from_latex_dimension(width_match.group(1), 250.0) if width_match else 250.0
        text = _clean_latex_text(m.group("text").strip())
        if not text:
            continue
        callouts.append({
            "label": pointer.group(1) if pointer else "",
            "text": text,
            "x": 130.0 + len(callouts) * 18.0,
            "y": 178.0 + len(callouts) * 18.0,
            "width": max(120.0, min(520.0, width)),
            "height": 92.0,
            "fontSize": 12,
            "align": align_match.group(1) if align_match else "center",
        })
    return callouts


def _extract_overview(frame_text: str) -> Optional[str]:
    """提取 fcolorbox 概述框"""
    match = re.search(
        r"\\fcolorbox\{[^}]*\}\{[^}]*\}\{\\parbox\{[^}]*\}\{(.*?)\}\}",
        frame_text, re.DOTALL
    )
    if match:
        return _clean_latex_text(match.group(1))
    return None


def _clean_latex_text(text: str) -> str:
    """清理 LaTeX 文本，移除所有格式命令，保留纯可读文本"""
    if not text:
        return ""

    s = text
    s = s.replace(r"\textbackslash{}", "\\")
    s = s.replace(r"\textbackslash\{\}", "\\")
    s = s.replace(r"\_", "_")
    s = s.replace(r"\$", "$")
    s = s.replace(r"\{", "{").replace(r"\}", "}")

    # ---- 修复上游截断/分割后残留的显示数学和换行尺寸标记 ----
    s = re.sub(r"^\s*\[?\s*\d+(?:\.\d+)?\s*(?:pt|em|ex|cm|mm|in)\]?\s*", "", s)
    s = re.sub(r"(?<!\\)\b\d+(?:\.\d+)?\s*(?:pt|em|ex|cm|mm|in)\]\s*", "", s)
    s = s.replace(r"\[", " ").replace(r"\]", " ")

    # ---- 移除 overlay 标记 <N-> ----
    s = re.sub(r"<\d+->", "", s)

    # ---- 移除整行格式命令 ----
    # \setlength{...}{...} 支持嵌套内容如 0.3\baselineskip
    s = re.sub(r"\\setlength\{[^}]*\}\{[^}]*(?:\{[^}]*\}[^}]*)?\}", "", s)
    s = re.sub(r"\\setlength\{[^}]*\}\{[^}]*\}", "", s)
    s = re.sub(r"\\vspace\*?\{[^}]*\}", "", s)
    s = re.sub(r"\\hspace\*?\{[^}]*\}", "", s)
    s = re.sub(r"\\hangindent=[^\s\\]*", "", s)
    s = re.sub(r"\\hangafter=\d+", "", s)
    s = re.sub(r"\\baselineskip\b", "", s)
    s = re.sub(r"\\itemsep\b", "", s)
    s = re.sub(r"\\topsep\b", "", s)
    s = re.sub(r"\\parskip\b", "", s)
    s = re.sub(r"\\noindent\b", "", s)
    s = re.sub(r"\\par\b", "", s)
    s = re.sub(r"\\centering\b", "", s)
    s = re.sub(r"\\vfill\b", "", s)
    s = re.sub(r"\\hfill\b", "", s)
    s = re.sub(r"\\newline\b", " ", s)
    s = re.sub(r"\\\\(\[.*?\])?", " ", s)  # \\ 或 \\[3pt] 换行
    s = re.sub(r"\\(?:small|footnotesize|tiny|large|Large|LARGE|huge|Huge|normalsize)\b", "", s)
    # LaTeX 注释 % 到行尾
    s = re.sub(r"%[^\n]*", "", s)

    # ---- 保护行内公式，避免后续命令清洗把 \bar{z} 等公式结构破坏 ----
    math_tokens = []

    def _store_math(match: re.Match) -> str:
        math_tokens.append(match.group(0))
        return f"@@MATH{len(math_tokens) - 1}@@"

    s = re.sub(r"\\\([\s\S]*?\\\)", _store_math, s)
    s = re.sub(r"\$[^$\n]+?\$", _store_math, s)

    # ---- 移除 tikzmark ----
    s = re.sub(r"\\tikzmark\{[^}]*\}", "", s)

    # ---- 展开格式命令：保留参数文字 ----
    # 多次迭代以处理嵌套
    for _ in range(3):
        s = re.sub(r"\\parbox\{[^}]*\}\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\makebox(?:\[[^\]]*\])?\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\textbf\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\textit\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\texttt\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\emph\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\underline\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\alert\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\mathbb\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\mathcal\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\textcolor\{[^}]*\}\{([^}]*)\}", r"\1", s)
        s = re.sub(r"\\colorbox\{[^}]*\}\{([^}]*)\}", r"\1", s)

    # ---- 移除剩余的简单命令 ----
    s = re.sub(r"\\(?:quad|qquad|,|;|!|%)", " ", s)
    s = re.sub(r"\\(?:left|right|bigl|bigr|Bigl|Bigr)[.|(|)|\\{|\\}|\[|\]]?", "", s)
    s = re.sub(r"\\(?:cdot|cdots|ldots|dots|infty|approx|simeq|neq|geq|leq|gg|ll|pm|mp|times|div)\b", " ", s)
    s = re.sub(r"\\(?:Rightarrow|Longrightarrow|rightarrow)\b", "→", s)
    s = re.sub(r"\\(?:Leftarrow|leftarrow)\b", "←", s)
    s = re.sub(r"\\(?:sum|prod|int|partial|nabla|forall|exists)\b", "", s)

    # ---- 移除 \usebeamertemplate{...} 等 beamer 命令 ----
    s = re.sub(r"\\usebeamertemplate\{[^}]*\}", "", s)
    s = re.sub(r"\\usebeamerfont\{[^}]*\}", "", s)

    # ---- 移除 \begin{minipage} 等环境标记 ----
    s = re.sub(r"\\begin\{[^}]*\}(?:\{[^}]*\}|\[[^\]]*\])*", "", s)
    s = re.sub(r"\\end\{[^}]*\}", "", s)

    # ---- 删除被错误拼入正文的显示公式尾巴 ----
    s = re.sub(r"(^|\s)(?:sigma|beta|frac|bar|AA:|Aa:|aa:)[^\u4e00-\u9fff。！？；]*$", "", s)

    # ---- 移除残留的 \command 形式（带大括号参数的未知命令）----
    s = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", s)
    # 移除残留的 \command（无参数的未知命令）
    s = re.sub(r"\\[a-zA-Z]+\b", "", s)

    # ---- 最终清理 ----
    s = s.replace("~", " ")
    s = s.replace("\\", " ")
    s = s.replace("{", "").replace("}", "")
    for i, value in enumerate(math_tokens):
        s = s.replace(f"@@MATH{i}@@", value)
    s = re.sub(r"\s+", " ", s).strip()

    return s


def _clean_frame_title_text(text: str) -> str:
    """Clean frame titles for PPT display; titles should stay readable English."""
    raw = str(text or "")
    normalized = raw.replace(r"\textbackslash{}", "\\")
    normalized = normalized.replace(r"\textbackslash\{\}", "\\")
    normalized = normalized.replace(r"\_", "_")
    normalized = normalized.replace(r"\{", "{").replace(r"\}", "}")
    normalized = re.sub(r"\\bar\s*\{\s*\\?(?:imath|i)\s*\}", "Average Selection Intensity", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bN\s*_\s*\{?\s*e\s*\}?", "Effective Population Size", normalized)
    cleaned = _clean_latex_text(normalized)
    cleaned = cleaned.replace(r"\textbackslash{}", " ")
    cleaned = cleaned.replace(r"\_", "_")
    cleaned = re.sub(r"\btextbackslash\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\\bar\s*\{\s*\\?(?:imath|i)\s*\}", "Average Selection Intensity", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bbar\s+(?:imath|i)\b", "Average Selection Intensity", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bN\s*_\s*\{?\s*e\s*\}?", "Effective Population Size", cleaned)
    cleaned = re.sub(r"\$[^$]*\$", " ", cleaned)
    cleaned = re.sub(r"\\[a-zA-Z]+", " ", cleaned)
    cleaned = cleaned.replace("{", " ").replace("}", " ").replace("\\", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,.")
    if (
        "tradeoff between" in cleaned.lower()
        and ("average selection intensity" in cleaned.lower() or "bar imath" in cleaned.lower())
        and "effective population size" in cleaned.lower()
    ):
        cleaned = "Tradeoff Between Selection Intensity and Effective Population Size"
    return cleaned or "Content"


def _estimate_editor_px_from_latex_dimension(value: str, default: float = 200.0) -> float:
    raw = str(value or "").strip()
    if not raw:
        return default
    match = re.match(r"([0-9.]+)\s*(px|pt|cm|mm|in|em|ex)?", raw)
    if not match:
        return default
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    if unit == "px":
        return number
    if unit == "in":
        return number * 96.0
    if unit == "cm":
        return number * 37.8
    if unit == "mm":
        return number * 3.78
    if unit == "pt":
        return number * 1.333
    if unit == "em":
        return number * 16.0
    if unit == "ex":
        return number * 8.0
    return default
