"""Prompt engine for Beamer generation."""

from __future__ import annotations

import re
from pathlib import Path


class PromptEngine:
    def __init__(self, system_prompt_path: str):
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            self._base_system_prompt = f.read()

    def build_system_prompt(
        self,
        style: str = "academic",
        custom_requirements: str = "",
        slide_count: int = 0,
        language: str = "auto",
        figure_assets: dict[str, str] | None = None,
    ) -> str:
        style_instructions = {
            "academic": "使用正式学术风格，适合课程讲义、学术报告和教学演示。",
            "business": "使用简洁商务风格，适合汇报和展示，强调结论、数据和结构化表达。",
            "minimal": "使用极简风格，减少装饰，突出重点内容和关键信息。",
        }
        language_map = {
            "zh": "按中英混排规则输出：每页顶部标题使用英文，正文说明使用中文，专业词汇保留英文。",
            "en": "按中英混排规则输出：每页顶部标题、人名和专业词汇使用英文，正文说明使用中文。",
            "auto": "根据输入内容自动识别专业词汇，默认按中英混排规则输出，且每页顶部标题使用英文。",
        }

        prompt = self._base_system_prompt.rstrip() + "\n\n"
        prompt += "## 本次生成要求\n"
        prompt += f"- 风格：{style_instructions.get(style, style_instructions['academic'])}\n"
        prompt += f"- 语言：{language_map.get(language, language_map['auto'])}\n"
        prompt += "- 中英混排规则：PPT 与 LaTeX 中每一页最上方的标题（包括 \\title{}、\\frametitle{}、目录页标题、总结页标题）必须使用英文；人名、英文文献作者名、专业术语和学科关键词必须使用英文；正文要点、页面说明、例题解释、课堂提问、总结文字和其他具体内容必须使用中文。\n"
        prompt += "- 不要把专业术语强行翻译成中文；首次出现时可写成“中文解释（English Term）”，之后优先保留英文术语。\n"
        prompt += "- \\title{}、\\frametitle{}、关键概念词、变量名、模型名、方法名、定理名、算法名、图表中的专业列名优先使用英文；普通 bullet 内容、解释句、课堂引导语使用中文，必要的专业词汇保留英文。\n"
        if slide_count > 0:
            prompt += f"- 页数：必须生成 {slide_count} 页幻灯片，包含封面/目录时也计入总数。\n"
            if slide_count >= 25:
                prompt += "- 详细程度：按“每章至少 25 页”的教学标准展开，不要把多个核心知识点压缩到同一页；知识图谱内容不够时，允许并要求结合通识知识补充背景、定义、推导、例子与复习总结。\n"
                prompt += "- 页面结构：优先仿照 BIMSA 课程讲义的节奏组织页面，包含 Review 页、本章目录页、背景/动机页、定义页、公式解释页、推导步骤页、图示解读页、表格解读页、例题页、实验或数据解释页、回顾总结页。\n"
                prompt += "- 单页内容：每页需要 3-6 个清晰要点；公式页必须包含公式含义、变量解释和使用条件。\n"

        if custom_requirements.strip():
            prompt += "\n## 用户额外要求\n"
            prompt += custom_requirements.strip() + "\n"
            prompt += self._build_image_placeholder_prompt(custom_requirements)
            prompt += self._build_figure_asset_prompt(figure_assets or {})
            hints = self._extract_requirement_hints(custom_requirements)
            if any(hints.values()):
                prompt += "\n## 可直接落到 LaTeX 的字段\n"
                if hints["title"]:
                    prompt += f"- \\title{{{hints['title']}}}\n"
                if hints["subtitle"]:
                    prompt += f"- \\subtitle{{{hints['subtitle']}}}\n"
                if hints["author"]:
                    prompt += f"- \\author{{{hints['author']}}}\n"
                if hints["date"]:
                    prompt += f"- \\date{{{hints['date']}}}\n"
                prompt += (
                    "- 封面、标题页和第一页相关要求优先使用 \\titlepage 和标题页结构实现，不要只写普通列表。\n"
                )

        if figure_assets and not custom_requirements.strip():
            prompt += self._build_figure_asset_prompt(figure_assets)

        return prompt

    def build_user_prompt(
        self,
        content: str,
        custom_requirements: str = "",
        slide_count: int = 0,
        figure_assets: dict[str, str] | None = None,
    ) -> str:
        parts: list[str] = []

        if custom_requirements.strip():
            hints = self._extract_requirement_hints(custom_requirements)
            parts.append("## 本次生成必须满足的额外要求")
            parts.append("")
            for line in custom_requirements.strip().splitlines():
                line = line.strip()
                if line:
                    parts.append(f"- {line}")
            placeholder_prompt = self._build_image_placeholder_prompt(custom_requirements).strip()
            if placeholder_prompt:
                parts.append("")
                parts.append(placeholder_prompt)
            if any(hints.values()):
                parts.append("")
                parts.append("## 已解析出的可直接使用字段")
                if hints["title"]:
                    parts.append(f"- title: {hints['title']}")
                if hints["subtitle"]:
                    parts.append(f"- subtitle: {hints['subtitle']}")
                if hints["author"]:
                    parts.append(f"- author: {hints['author']}")
                if hints["date"]:
                    parts.append(f"- date: {hints['date']}")
            parts.append("")
            parts.append("请在生成的 LaTeX 代码中逐条满足以上要求。")
            parts.append("")
            parts.append("---")
            parts.append("")

        parts.append("请根据以下内容生成完整的 LaTeX Beamer 演示文稿代码。")
        parts.append("必须输出完整 .tex 文件内容，从 \\documentclass 开始，到 \\end{document} 结束。")
        parts.append("不要输出解释性文字、Markdown 代码块标记或额外说明。")
        parts.append("")
        parts.append("---")
        parts.append("")

        expansion_prompt = self._build_content_expansion_prompt(content, slide_count)
        if expansion_prompt:
            parts.append(expansion_prompt)
            parts.append("")
            parts.append("---")
            parts.append("")

        figure_assets_prompt = self._build_figure_asset_prompt(figure_assets or {})
        if figure_assets_prompt:
            parts.append(figure_assets_prompt)
            parts.append("")
            parts.append("---")
            parts.append("")

        parts.append(content)
        return "\n".join(parts)

    def _build_content_expansion_prompt(self, content: str, slide_count: int) -> str:
        if slide_count <= 0:
            return ""

        density = self._estimate_content_density(content)
        sparse_for_target = slide_count >= 8 and density < slide_count * 55
        very_sparse_for_target = slide_count >= 12 and density < slide_count * 35
        detailed_chapter_mode = slide_count >= 25
        if not sparse_for_target:
            if not detailed_chapter_mode:
                return ""

        min_expansion_slides = max(2, min(slide_count - 3, slide_count // 3))
        if detailed_chapter_mode:
            min_expansion_slides = max(min_expansion_slides, min(slide_count - 3, 8))
        if very_sparse_for_target:
            min_expansion_slides = max(min_expansion_slides, min(slide_count - 3, slide_count // 2))

        return (
            "## 内容扩展模式\n"
            f"- 目标页数为 {slide_count} 页，必须围绕本章主题主动扩展相关知识，保证每章至少 25 页且内容详细；若知识图谱内容不足，优先用 DeepSeek 自身知识补充背景、定义、推导、例子和总结。\n"
            f"- 至少生成 {min_expansion_slides} 页“知识扩展/教学补充”内容，不要重复原文。\n"
            "- 扩展内容可包括：背景、定义、原理、推导、示例、对比、常见错误、课堂提问、应用场景、图示解读、表格解读、实验结果解释、总结回顾。\n"
            "- 每个核心概念、关键公式、重要图表、例题步骤和结论总结都优先单独成页。\n"
            "- 不要用一页承载过多内容；如果一个知识点包含多个公式或推导步骤，应拆分为多页讲解。\n"
            "- 仿照 BIMSA 课程风格：先用 Review 或章节导航页建立结构，再用动机页、图页、表页、推导页和实验页逐步展开，不要直接从头到尾只写 bullet 列表。\n"
            "- 所有扩展必须与原主题强相关，不要编造无法验证的具体事实、年份、统计数字或案例来源。\n"
            "- 每一页都要有明确标题和 3-6 个要点。\n"
        )

    def _estimate_content_density(self, content: str) -> int:
        text = re.sub(r"\s+", " ", content or "").strip()
        cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin_words = len(re.findall(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", text))
        return cjk_chars + latin_words * 2

    def _build_image_placeholder_prompt(self, text: str) -> str:
        if not re.search(r"(图|图片|插图|配图|占位|留白|image|picture|placeholder)", text or "", re.IGNORECASE):
            return ""
        return (
            "\n## 图片占位规则\n"
            "- 如果需要在某一页保留图片位置，不要直接写 \\includegraphics。\n"
            "- 请使用结构化占位命令：\\kgimageplaceholder[figure=Figure 26.6,right]{图片占位}。\n"
            "- 如果原文出现 Figure 26.x、Fig. 26.x 或图 26.x，即使没有额外说明，也必须在同一 frame 放置对应 \\kgimageplaceholder。\n"
            "- 占位命令的大括号文字必须保留图号，例如 {Figure 26.6}，不要只写“图片占位”。\n"
            "- 位置可用 right、left、center、top-right、top-left、bottom-right、bottom-left。\n"
            "- 如果用户明确指定页码或位置，请把占位命令放进对应 frame 中。\n"
            "- 占位文字要简短，保留给后续 PPT 编辑器和图片包自动匹配使用。\n"
        )

    def _build_figure_asset_prompt(self, figure_assets: dict[str, str]) -> str:
        if not figure_assets:
            return ""

        pairs: list[str] = []
        for label, asset in list(figure_assets.items())[:24]:
            label_text = str(label or "").strip()
            asset_text = self._short_asset_name(str(asset or "").strip())
            if label_text and asset_text:
                pairs.append(f"- {label_text} -> {asset_text}")

        if not pairs:
            return ""

        return (
            "\n## 图片编号到图片文件的映射\n"
            "以下是当前导入的图号和图片文件对应关系。生成 LaTeX 时，看到相同图号就用对应的占位命令保留位置：\n"
            + "\n".join(pairs)
            + "\n- 例如看到 Figure 26.6，就在对应 frame 内写成 \\kgimageplaceholder[figure=Figure 26.6,right]{Figure 26.6} 或等价结构。\n"
            + "- 不要把图号改写成普通正文，也不要省略 figure= 这个锚点。\n"
            + "- 即使正文要说明 Figure 26.6，也必须另外保留图片占位命令，确保 PPT 能插入真实图片。\n"
        )

    def _short_asset_name(self, value: str) -> str:
        if not value:
            return ""
        cleaned = value.split("?", 1)[0].split("#", 1)[0].replace("\\", "/")
        return Path(cleaned).name

    def _extract_requirement_hints(self, text: str) -> dict[str, str]:
        patterns = {
            "title": [
                r"(?:标题|题目|封面标题)\s*[:：]\s*([^\n，。;；]+)",
                r"(?:第一页|封面页).*?(?:标题|题目)\s*[:：]\s*([^\n，。;；]+)",
            ],
            "subtitle": [
                r"(?:副标题|小标题)\s*[:：]\s*([^\n，。;；]+)",
            ],
            "author": [
                r"(?:作者|署名|讲者)\s*[:：]\s*([^\n，。;；]+)",
            ],
            "date": [
                r"(?:日期|时间)\s*[:：]\s*([^\n，。;；]+)",
            ],
        }

        result = {"title": "", "subtitle": "", "author": "", "date": ""}
        source = text or ""
        for key, regex_list in patterns.items():
            for pattern in regex_list:
                match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)
                if match:
                    result[key] = match.group(1).strip()
                    break
        return result
