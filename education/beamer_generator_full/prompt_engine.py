"""Prompt engine for Beamer generation."""

from __future__ import annotations

import re
from pathlib import Path


class PromptEngine:
    def __init__(self, system_prompt_path: str):
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            self._base_system_prompt = f.read()

    def _strict_language_policy(self) -> str:
        return (
            "## 强制语言规则（最高优先级）\n"
            "- 严禁生成纯英文 PPT。即使输入材料、参考论文或用户额外要求主要是英文，也必须按“大标题、人名、专业词汇英文；小标题和具体内容中文”的规则输出。\n"
            "- 大标题必须使用英文，包括封面 \\title{}、每页 \\frametitle{}、目录页标题、Review/Summary 页标题。\n"
            "- 人名、英文文献作者名、专业术语、学科关键词、模型名、算法名、变量名、公式名保留英文。\n"
            "- 小标题、页面说明、正文要点、公式解释、变量含义、例题步骤、课堂提问、复习总结、callout 标注文字必须使用中文表达；必要的专业词汇可保留英文。\n"
            "- 普通 itemize/enumerate 列表不能整页全英文；除专有名词、变量和公式外，每个正文页至少大部分 bullet 需要包含中文讲解。\n"
            "- 如果原文是英文，请把解释性句子翻译/改写成中文教学语言，而不是照抄英文段落。\n"
            "- 不提供其他语言版本，也不允许根据输入材料自动切换为纯中文或纯英文。\n"
        )

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
            "title_terms_en_content_zh": "唯一语言风格：大标题、人名、专业词汇使用英文；小标题和具体内容使用中文。",
            "zh": "唯一语言风格：大标题、人名、专业词汇使用英文；小标题和具体内容使用中文。",
            "en": "唯一语言风格：大标题、人名、专业词汇使用英文；小标题和具体内容使用中文，禁止纯英文。",
            "auto": "唯一语言风格：大标题、人名、专业词汇使用英文；小标题和具体内容使用中文，禁止纯英文。",
        }

        prompt = self._base_system_prompt.rstrip() + "\n\n"
        prompt += self._strict_language_policy() + "\n"
        prompt += "## 本次生成要求\n"
        prompt += f"- 风格：{style_instructions.get(style, style_instructions['academic'])}\n"
        prompt += f"- 语言：{language_map.get(language, language_map['title_terms_en_content_zh'])}\n"
        prompt += "- 中英混排规则：PPT 与 LaTeX 中每一页最上方的大标题（包括 \\title{}、\\frametitle{}、目录页标题、总结页标题）必须使用英文；人名、英文文献作者名、专业术语和学科关键词必须使用英文；小标题、正文要点、页面说明、例题解释、课堂提问、总结文字和其他具体内容必须使用中文。\n"
        prompt += "- 不要把专业术语强行翻译成中文；首次出现时可写成“中文解释（English Term）”，之后优先保留英文术语。\n"
        prompt += "- \\title{}、\\frametitle{}、关键概念词、变量名、模型名、方法名、定理名、算法名、图表中的专业列名优先使用英文；普通 bullet 内容、解释句、课堂引导语使用中文，必要的专业词汇保留英文。\n"
        prompt += self._build_equation_reference_prompt()
        prompt += self._chapter_policy_for_slide_count(slide_count)
        if slide_count > 0:
            prompt += f"- 最少页数：必须生成至少 {slide_count} 页幻灯片，包含封面/目录时也计入总数；可以超过，但不得少于该数。\n"
            if slide_count >= 40:
                prompt += f"- 硬性约束：最终 LaTeX 必须包含不少于 {slide_count} 个 \\begin{{frame}}...\\end{{frame}} 页面；不得只生成短版后依赖系统补页。\n"
                prompt += "- 生成前请在内部先规划完整页面清单，但不要把规划说明输出到结果中；最终只输出完整 .tex。\n"
                prompt += "- 去重要求：每页 \\frametitle 必须不同；任意两页正文 bullet 不得超过 60% 相同，禁止只改标题而复用同一组要点。\n"
                prompt += "- 覆盖要求：长知识图谱必须按所有主要节点、关系、公式、图表、例子和结论分配页面，不得只围绕前几个节点生成。\n"
                prompt += f"- 详细程度：按“每章至少 {slide_count} 页”的教学标准展开，不要把多个核心知识点压缩到同一页；知识图谱内容不够时，允许并要求结合通识知识补充背景、定义、推导、例子与复习总结。\n"
                prompt += "- 页面结构：严格仿照 260526-bimsa-12(1).tex 的三章节骨架，包含 Review 页、本章目录页、每个固定 section 的高亮目录页、背景/动机页、定义页、公式解释页、推导步骤页、图示解读页、表格解读页、例题页、实验或数据解释页、回顾总结页。\n"
                prompt += "- 单页内容：每页需要 3-6 个清晰要点；公式页必须包含公式含义、变量解释和使用条件。\n"

        if custom_requirements.strip():
            prompt += "\n## 用户额外要求\n"
            prompt += custom_requirements.strip() + "\n"
            prompt += self._build_free_requirement_strategy_prompt(custom_requirements)
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
            strategy_prompt = self._build_free_requirement_strategy_prompt(custom_requirements).strip()
            if strategy_prompt:
                parts.append("")
                parts.append(strategy_prompt)
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
        parts.append(self._chapter_policy_for_slide_count(slide_count).strip())
        if slide_count >= 40:
            parts.append(f"必须一次性输出不少于 {slide_count} 页，不允许输出 6-8 页短版；不要把大量知识图谱压缩为少数综述页。")
            parts.append("生成时请把每个主要 Markdown 标题、知识图谱节点、公式、图表、关系边和例子拆成独立教学页面，并分别归入固定的三个 section。")
            parts.append("严禁出现正文要点完全相同但标题不同的页面；若页面目的不同，正文必须分别体现定义、推导、例子、误区、图表解读或复习提问的差异。")
        parts.append("")
        parts.append(self._strict_language_policy().strip())
        parts.append("")
        parts.append(self._build_equation_reference_prompt().strip())
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
        detailed_chapter_mode = slide_count >= 40
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
            f"- 最少页数为 {slide_count} 页，必须围绕本章主题主动扩展相关知识并保持内容详细；若知识图谱内容不足，优先用 DeepSeek 自身知识补充背景、定义、推导、例子和总结。\n"
            f"- 至少生成 {min_expansion_slides} 页“知识扩展/教学补充”内容，不要重复原文。\n"
            "- 扩展内容可包括：背景、定义、原理、推导、示例、对比、常见错误、课堂提问、应用场景、图示解读、表格解读、实验结果解释、总结回顾。\n"
            "- 每个核心概念、关键公式、重要图表、例题步骤和结论总结都优先单独成页。\n"
            "- 不要用一页承载过多内容；如果一个知识点包含多个公式或推导步骤，应拆分为多页讲解。\n"
            "- 如果导入了多个 Markdown 文件，必须覆盖每个文件的主要标题和关键节点，并在页面标题或正文中体现对应主题。\n"
            "- 不能用同一批 bullet 反复生成不同标题页；Review、Definition、Formula、Example、Concept Check、Summary 页面必须有不同正文。\n"
            "- 仿照课程风格：先用 Review 或章节导航页建立结构，再用动机页、图页、表页、推导页和总结页逐步展开，不要直接从头到尾只写 bullet 列表。\n"
            "- 所有扩展必须与原主题强相关，不要编造无法验证的具体事实、年份、统计数字或案例来源。\n"
            "- 每一页都要有明确标题和 3-6 个要点。\n"
        )

    def _chapter_policy_for_slide_count(self, slide_count: int) -> str:
        if slide_count < 20:
            return (
                "\n## 紧凑课件结构规则\n"
                "- 按最少页数生成紧凑 Beamer 课件，默认至少 7 页；不要套用三章节长课件骨架。\n"
                "- 建议结构：标题页、核心背景/问题页、2-4 页关键概念/公式/图表解释页、总结页；如最少页数更少，可合并目录和背景页。\n"
                "- 每页承担明确教学功能，正文保持 3-5 个要点；优先覆盖知识图谱中最关键的概念、公式、图表和关系。\n"
                "- 保留参考模板的视觉风格和标题页样式，但不要为了凑页数插入空白页、Test Title 页或无关填充页。\n"
            )
        return self._fixed_bimsa_chapter_policy()

    def _fixed_bimsa_chapter_policy(self) -> str:
        return (
            "\n## 固定参考模板与章节填充规则（最高优先级）\n"
            "- 必须严格按照参考文件 `260526-bimsa-12(1).tex` 的 LaTeX 格式、首页、Review 页、本章目录页和章节划分生成。\n"
            "- 标题页元信息固定为：\\title[]{ Evolutionary Theory on\\\\ Polygenic Trait}；\\subtitle{XII - Long-term Response: 2. Finite Population Size and Mutation (2)}；\\author{Qi WU(吴琦)}；\\date{2026-5-26}。\n"
            "- 第一页必须是带 `fig/图片3.png` 背景的 \\titlepage，并保留右上角 `fig/图片1.png`、`fig/图片2.png` 标识。\n"
            "- 正式章节只能有这 3 个 section，且顺序不能改变：1. Optimal Selection Intensities For Maximizing Long-Term Response；2. Effects Of Population Structure On Long-Term Response；3. Asymptotic Response Due To Mutational Input。\n"
            "- 知识图谱中的所有知识点必须按语义填入上述 3 个 section；禁止新增其他 section，禁止把内容放到无意义占位页。\n"
            "- 每个 section 前必须插入和参考文件一致的目录高亮页，当前 section 黑色，其余 section gray。\n"
            "- 禁止输出 Test Title A2、Test title B2、空白幻灯、占位页或与知识图谱无关的填充内容。\n"
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
            "\n## 图片引用规则\n"
            "- 如果需要在某一页引用图片，必须直接写 \\includegraphics，不要只写 Figure 文字说明，也不要使用普通占位。\n"
            "- 图片地址必须使用带图片编号的 fig/ 路径格式，例如 Figure 25.1 写成 \\includegraphics[width=0.7\\textwidth]{fig/图25_1.png}。\n"
            "- 如果原文出现 Figure 26.6、Fig. 26.6 或图 26.6，即使没有额外说明，也必须在同一 frame 中插入 \\includegraphics[width=0.7\\textwidth]{fig/图26_6.png}。\n"
            "- 图片下方或右侧可以保留中文解释或 caption，但不能用 Figure 26.6 代替图片本体。\n"
            "- 如果用户明确指定图片位置，请仍然使用 fig/图片编号路径，并按横向图/竖向图模板摆放。\n"
            "- 同一张图片只能生成一个图片 frame；如果有多段文字都解释 Figure 27.1 这样的同一图片，必须把这些说明合并到同一个 Figure 27.1 frame 的说明文字里，不要拆成两页重复图片。\n"
            "- 凡是 PPT 页面中有横向扁图，必须严格使用“上图下文”版式，但 frame 标题必须写图片编号，例如 \\begin{frame}{Figure 27.1}；正文先 \\centering，再使用 \\safecontentimage{fig/27.1.png}，再 \\vspace{0.3cm}，最后用 \\begin{center}\\parbox{0.95\\textwidth}{\\scriptsize ...}\\end{center} 放图片说明。\n"
            "- 凡是 PPT 页面中有竖向图，必须严格使用“左图右文”版式，但 frame 标题必须写图片编号，例如 \\begin{frame}{Figure 27.2}；正文使用 \\begin{columns}[T]；左列 0.45\\textwidth 内先 \\centering 再使用 \\safeverticalimage{fig/27.2.png}；右列 0.45\\textwidth 内直接写 \\scriptsize 图片说明。\n"
        )

    def _build_free_requirement_strategy_prompt(self, text: str) -> str:
        source = text or ""
        if not source.strip():
            return ""

        def contains(*patterns: str) -> bool:
            return any(re.search(pattern, source, re.IGNORECASE) for pattern in patterns)

        wants_more_examples = contains(
            r"(多|更多|多一些|多生成|增加|补充|丰富).{0,8}(示例|例子|参照|案例|举例|类比|比喻)",
            r"(示例|例子|参照|案例|举例|类比|比喻).{0,8}(多|更多|多一些|增加|补充|丰富)",
            r"(more|many|additional|extra).{0,16}(example|case|analogy)",
        )
        wants_examples = wants_more_examples or contains(
            r"(示例|例子|参照|案例|举例|类比|比喻|example|case|analogy)"
        )
        wants_plain_explanation = contains(
            r"(浅显|易懂|通俗|直观|简单|入门|初学|基础|小白|白话|好懂|看得懂|plain|easy|intuitive)",
            r"(知识点|概念|内容).{0,12}(展开|讲解|解释|说明).{0,12}(浅显|易懂|通俗|直观|简单|白话|好懂)",
            r"(浅显|易懂|通俗|直观|简单|白话|好懂).{0,12}(展开|讲解|解释|说明)",
        )
        wants_expanded_points = contains(
            r"(知识点|概念|要点|重点).{0,12}(展开|拆开|讲细|详细|细讲|展开讲)",
            r"(展开|讲细|详细).{0,12}(知识点|概念|要点|重点)",
        )

        rules = [
            "## 自由要求执行策略（必须落实到页面内容）",
            "- 用户自由要求是硬性生成要求，不能只在内容中复述；必须具体体现在每页选材、标题、讲解方式和页面结构中。",
            "- 对用户用口语表达的要求也要做语义识别，例如“多生成一些参照事例”“知识点用比较浅显易懂的方式展开”等，必须转化为示例数量、讲解顺序和页面拆分规则。",
        ]

        if wants_examples:
            rules.extend(
                [
                    "- 示例化要求：每个核心概念、关键公式或重要结论优先配 1 个短参照示例、生活化类比或简化情境。",
                    "- 示例页标题可使用 Example、Intuition、From Example to Rule、Concept Check 等英文大标题；正文用中文解释例子如何对应本章知识点。",
                    "- 不要把示例写成孤立故事；示例之后必须回扣到定义、公式变量、图示含义或知识图谱关系。",
                ]
            )
            if wants_more_examples:
                rules.extend(
                    [
                        "- 多示例要求：每个主要 section 至少安排 1 页 Example / Reference Case / Concept Check；如果页数允许，核心概念页后紧跟一个参照事例页。",
                        "- 对同一知识点可使用“一个直观小例子 + 一个学科内参照例子”的组合，但两者都必须短小，避免挤占公式或定义讲解。",
                    ]
                )

        if wants_plain_explanation:
            rules.extend(
                [
                    "- 通俗化要求：先讲直观含义，再给正式术语或公式；公式页必须先解释变量和使用场景，再说明数学表达。",
                    "- 正文句子要短，避免连续堆砌抽象名词；必要术语首次出现时用中文解释加英文术语。",
                    "- 对难点使用“先看问题-再看原因-最后看结论”的讲解顺序，降低理解门槛。",
                ]
            )

        if wants_expanded_points or wants_plain_explanation:
            rules.extend(
                [
                    "- 知识点展开要求：不要把多个新概念压缩到同一页；每个核心知识点至少包含“直观解释、关键关系、简短例子、回到公式/图谱关系”的讲解链条。",
                    "- 对抽象概念先用一句中文白话解释其作用，再说明它和前后知识点的关系，最后给出课堂可检查的小问题或小结。",
                ]
            )

        if re.search(r"(罗列|堆砌|生硬|不要.*要点|少.*要点|列表|bullet)", source, re.IGNORECASE):
            rules.extend(
                [
                    "- 反罗列要求：避免生成整页只有 4-6 条孤立 bullet 的页面；除目录和总结页外，优先采用“问题-解释-例子-小结”的组织方式。",
                    "- 如果必须使用 itemize，每条 bullet 要写成解释性句子，并体现因果、对比、步骤或教学提示，不要只列名词短语。",
                    "- 对同一知识点，优先拆成“直观理解页、公式/定义页、示例页、总结页”，不要压缩成一页生硬清单。",
                ]
            )

        if re.search(r"(本章|章节|本节|教材|chapter|section)", source, re.IGNORECASE):
            rules.extend(
                [
                    "- 章节聚焦要求：所有示例、扩展和类比都必须服务于本章主题，不能生成泛泛的通用课程介绍。",
                    "- 页面顺序应体现本章学习路径：背景问题、核心概念、关键公式/图表、参照示例、应用或误区、总结回顾。",
                ]
            )

        if len(rules) <= 3:
            return (
                "\n".join(
                    rules
                    + [
                        "- 对无法归类的自由要求，也必须转化为具体页面行为：标题、内容取舍、讲解深度、示例数量或排版结构至少有一项发生对应变化。",
                        "- 生成前在内部检查自由要求是否已经落到 LaTeX 页面中；最终只输出完整 .tex，不输出检查说明。",
                    ]
                )
                + "\n"
            )

        rules.append("- 生成前在内部检查上述自由要求是否已经落到 LaTeX 页面中；最终只输出完整 .tex，不输出检查说明。")
        return "\n".join(rules) + "\n"

    def _build_equation_reference_prompt(self) -> str:
        return (
            "\n## 公式引用完整性规则\n"
            "- 凡是正文中引用公式编号（例如 公式(2.3)、Equation (2.3)、Eq. (2.3)、\\eqref{...}、\\ref{eq:...}），必须在同一页或相邻页给出对应公式的 LaTeX 代码。\n"
            "- 不允许只写“见公式/由公式可得”而没有公式本体；公式页必须包含公式、变量含义和使用条件。\n"
            "- 公式变量解释展示规则：不要用 itemize/enumerate 或普通文字逐项罗列“每一项表示什么”；必须在公式中用 \\tikzmark 标记关键项，并用蓝色 rectangle callout 箭头框指向对应公式项进行注释。\n"
            "- 每个蓝色箭头框使用 draw=blue, fill=white, rounded corners，注释文字用中文短句；callout 只做公式旁注，不要混入公式正文。\n"
            "- 如果公式项较多，优先标注 2-4 个最关键变量或参数，剩余说明可放在一句中文总结中，但不能生成逐项文字清单。\n"
            "- 如果导入材料中没有找到被引用公式的原文，不要编造公式；必须在对应 frame 中写入缺失公式标记：\\kgmissingequation{num:2.3}{Equation 2.3} 或 \\kgmissingequation{label:eq:name}{Equation eq:name}。\n"
            "- 缺失公式标记用于后续用户导入补充章节后自动替换，不能删除或改写成普通文字。\n"
        )

    def _build_figure_asset_prompt(self, figure_assets: dict[str, str]) -> str:
        if not figure_assets:
            return ""

        pairs: list[str] = []
        for label, asset in list(figure_assets.items())[:24]:
            label_text = str(label or "").strip()
            asset_text = self._short_asset_name(str(asset or "").strip())
            if label_text and asset_text:
                pairs.append(f"- {label_text} -> fig/{asset_text}")

        if not pairs:
            return ""

        return (
            "\n## 图片编号到图片文件的映射\n"
            "以下是当前导入的图号和图片文件对应关系。生成 LaTeX 时，看到相同图号必须直接插入对应图片地址：\n"
            + "\n".join(pairs)
            + "\n- 例如看到 Figure 26.6，如果映射文件名是 图26_6.png，就在对应 frame 内写成 \\includegraphics[width=0.7\\textwidth]{fig/图26_6.png}。\n"
            + "- 不要把图号改写成普通正文，也不要只写 Figure 26.6 而不插图。\n"
            + "- 即使正文要说明 Figure 26.6，也必须另外插入 \\includegraphics，确保 PPT 能插入真实图片。\n"
            + "- 同一张图片只能出现一个图片 frame；多段解释同一 Figure 时，必须把文字合并到同一页图片说明中。\n"
            + "- 含图片的 frame 必须根据图片方向严格套用版式：横向扁图用“上图下文”排版，竖向图用“左图右文”排版；但 frame 标题必须是图片编号，例如 {Figure 26.6}，不能写成“上图下文”或“左图右文”。\n"
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
