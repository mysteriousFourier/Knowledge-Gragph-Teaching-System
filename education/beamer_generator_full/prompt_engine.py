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
            "zh": "所有幻灯片内容使用中文。",
            "en": "所有幻灯片内容使用英文。",
            "auto": "根据输入内容自动选择语言，默认以中文输出。",
        }

        prompt = self._base_system_prompt.rstrip() + "\n\n"
        prompt += "## 本次生成要求\n"
        prompt += f"- 风格：{style_instructions.get(style, style_instructions['academic'])}\n"
        prompt += f"- 语言：{language_map.get(language, language_map['auto'])}\n"
        if slide_count > 0:
            prompt += f"- 页数：必须生成 {slide_count} 页幻灯片，包含封面/目录时也计入总数。\n"

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
        if not sparse_for_target:
            return ""

        min_expansion_slides = max(2, min(slide_count - 3, slide_count // 3))
        if very_sparse_for_target:
            min_expansion_slides = max(min_expansion_slides, min(slide_count - 3, slide_count // 2))

        return (
            "## 内容扩展模式\n"
            f"- 目标页数为 {slide_count} 页，但原始材料偏少，必须围绕主题主动扩展相关知识。\n"
            f"- 至少生成 {min_expansion_slides} 页“知识扩展/教学补充”内容，不要重复原文。\n"
            "- 扩展内容可包括：背景、定义、原理、推导、示例、对比、常见错误、课堂提问、应用场景、总结回顾。\n"
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
