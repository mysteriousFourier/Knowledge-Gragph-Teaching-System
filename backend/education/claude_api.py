"""DeepSeek API client kept under the legacy module path for compatibility."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import httpx

from kg_constraints import (
    KG_CONSTRAINED_SYSTEM_PROMPT,
    build_constrained_generation_prompt,
    build_learning_plan,
    evidence_from_graph,
    evidence_from_rag,
    expand_formula_references,
    format_evidence,
    relation_evidence_from_graph,
)

DEFAULT_DEEPSEEK_FLASH_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_PRO_MODEL = "deepseek-v4-pro"
_DEFAULT_TIMEOUT = object()

QA_SYSTEM_PROMPT = """你是一个公式友好的教学问答助手。
图谱和检索内容是参考上下文，不是拒答规则。用户问公式、定义、推导或概念时，先直接回答。
如果上下文有相关材料，优先使用并保留原文术语；如果上下文没有命中，但问题属于常见数学/机器学习/课程知识，可以用通用知识回答，并简短标注“通用说明”。
不要因为 LearningPlan 或 evidence 不足而拒答；只在问题涉及具体课程私有内容且上下文完全缺失时说明需要补充材料。
公式必须用 LaTeX 输出，并解释主要符号。"""


def get_deepseek_model(kind: str = "flash") -> str:
    """Resolve task-specific DeepSeek model names."""
    if kind == "pro":
        return (
            os.getenv("DEEPSEEK_PRO_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or DEFAULT_DEEPSEEK_PRO_MODEL
        ).strip() or DEFAULT_DEEPSEEK_PRO_MODEL
    return (os.getenv("DEEPSEEK_FLASH_MODEL") or DEFAULT_DEEPSEEK_FLASH_MODEL).strip() or DEFAULT_DEEPSEEK_FLASH_MODEL


def _parse_read_timeout(value: str | None, default: float | None) -> float | None:
    text = str(value or "").strip().lower()
    if not text or text == "default":
        return default
    if text in {"0", "none", "off", "false"}:
        return None
    try:
        return max(float(text), 1.0)
    except ValueError:
        return default


def _generation_read_timeout() -> float | None:
    return _parse_read_timeout(os.getenv("DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS"), None)


class DeepSeekAPIClient:
    """DeepSeek chat-completions client for lecture, QA, and exercise generation."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
        self.model = (model or get_deepseek_model("flash")).strip() or DEFAULT_DEEPSEEK_FLASH_MODEL

    async def generate_lecture(self, graph_data: Dict, chapter_data: Dict, style: str = "引导式教学") -> str:
        prompt = self._build_lecture_prompt(graph_data, chapter_data, style)
        lecture = expand_formula_references(
            await self._call_deepseek(
                prompt,
                max_tokens=5200,
                system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT,
                read_timeout_seconds=_generation_read_timeout(),
            ),
            expand_labels=True,
        )
        if self._lecture_needs_completion(lecture):
            repair_prompt = f"""
请基于原始任务重写一份完整授课文案，不要只补几句话。

原始任务：
{prompt}

上一次输出不完整或结构不足：
{lecture}

必须满足：
1. 输出完整可直接授课的 Markdown 文案。
2. 至少覆盖导入、核心概念、关系链路、例题/推导、课堂提问、易错点、总结。
3. 不要输出题纲、备注、自检说明或 JSON。
4. 保留知识图谱/章节证据约束，不要扩展未授权内容。
"""
            lecture = expand_formula_references(
                await self._call_deepseek(
                    repair_prompt,
                    max_tokens=5200,
                    system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT,
                    read_timeout_seconds=_generation_read_timeout(),
                ),
                expand_labels=True,
            )
        return lecture

    @staticmethod
    def _lecture_needs_completion(text: str) -> bool:
        content = str(text or "").strip()
        if len(content) < 900:
            return True
        required_markers = ["导入", "核心", "关系", "例", "提问", "易错", "总结"]
        present = sum(1 for marker in required_markers if marker in content)
        if present < 5:
            return True
        trailing_markers = ("...", "……", "如下", "包括", "首先", "例如")
        return content.endswith(trailing_markers)

    async def answer_question(self, graph_data: Dict, question: str, search_results: Optional[List[Dict]] = None) -> str:
        prompt = self._build_qa_prompt(graph_data, question, search_results)
        return expand_formula_references(
            await self._call_deepseek(prompt, max_tokens=1800, system_prompt=QA_SYSTEM_PROMPT),
            expand_labels=True,
        )

    async def natural_supplement(self, original_text: str, supplement: str) -> str:
        prompt = f"""
请将以下补充内容自然地融入原文中。

原文：
{original_text}

补充内容：
{supplement}

要求：
1. 不要使用生硬的过渡词。
2. 保持原文的逻辑结构和语气。
3. 输出直接可用的最终文本，不要附加说明。
"""
        return await self._call_deepseek(prompt)

    async def generate_exercises(
        self,
        chapter_title: str,
        chapter_content: str,
        count: int = 5,
        graph_data: Optional[Dict] = None,
        feedback_guidance: Optional[str] = None,
    ) -> Dict:
        chapter_content = expand_formula_references(chapter_content)
        chapter_data = {"title": chapter_title, "content": chapter_content}
        evidence = evidence_from_graph(
            graph_data,
            query=f"{chapter_title}\n{chapter_content[:800]}",
            chapter_data=chapter_data,
            limit=8,
        )
        if chapter_content.strip():
            chapter_evidence = {
                "index": 1,
                "id": "chapter_content",
                "label": chapter_title,
                "type": "chapter_content",
                "content": chapter_content[:1200],
                "source": "chapter",
            }
            evidence = [chapter_evidence] + [
                item for item in evidence if isinstance(item, dict) and item.get("id") != "chapter_content"
            ]
        relations = relation_evidence_from_graph(graph_data, evidence)
        learning_plan = build_learning_plan(
            query=chapter_title,
            evidence=evidence,
            relations=relations,
            learner_intent="practice",
            learning_level="beginner",
            task="exercise",
            chapter_data=chapter_data,
        )
        requirements = [
            f"生成 {max(1, count)} 道单选题，不要生成示例题、占位题或模板题。",
            "必须返回足量题目；即使材料较短，也要从定义、公式含义、变量作用、概念关系、常见误解等不同角度出题。",
            "题干要像 NotebookLM 的材料测验一样自然、短、面向学生；不要在题干或选项里出现 LearningPlan、evidence、知识图谱、图谱证据、当前证据等内部约束词。",
            "禁止生成泛题，例如 'Which statement is directly stated in the material?'、'What is this?'、'下列哪项正确？'。题干必须明确考察一个概念、定理、公式、变量含义或条件关系。",
            "不要把授课文案结构当作知识点：禁止考察或作为选项输出“授课文案、教学目标、课堂导入、启发提问、教学要点、小组讨论、课后思考、章节标题、Chapter 标题”等页面/教学脚手架文本。",
            "如果材料含有 [[SEE_FORMULA:...]]、[[SEE_TABLE:...]] 等占位引用，但没有给出公式或表格正文，不要围绕该占位符出题。",
            "题干必须少于 32 个英文词或 72 个中文字符；每个选项少于 24 个英文词或 90 个中文字符。",
            "题干、正确选项和解析必须能在课程材料、章节正文或 evidence 中找到依据。",
            "英文原文、术语、公式和变量名保持英文，不要为了出题强行翻译。",
            "每道题必须有 4 个选项，且只有 1 个正确答案；错误选项要与本章内容相关，但不能与证据冲突。",
            "不要把整句原文直接复制成所有选项；正确选项可以保留关键术语，但选项应像答案而不是长段落。",
            "禁止输出‘选项一/选项二/示例/测试/sample/最符合当前证据/依据不足’等占位或内部约束内容。",
            "解析用 1-2 句说明为什么正确，必要时标注原文编号，例如‘原文[1]’。",
            "只返回合法 JSON，不要返回 Markdown、代码块或额外说明。",
            'JSON 格式：{"exercises":[{"id":"ex_1","question":"题目内容","options":["A. ...","B. ...","C. ...","D. ..."],"correct_answer":"A","explanation":"答案解析，依据[1]..."}]}',
        ]
        requirements = [
            f"Generate {max(1, count)} natural multiple-choice questions for students, similar to NotebookLM or ChatGPT study quizzes.",
            "Use the chapter content first. Use graph evidence only as supporting context; do not turn evidence constraints into question text.",
            "Each question must test one clear concept, formula, variable meaning, relation, or condition from the material.",
            "Prefer conceptual understanding questions: ask why a condition matters, what a theorem implies, how two quantities relate, or what would change if an assumption changes.",
            "Do not make the whole quiz definition recall. At least 60% of questions should test reasoning about implications, conditions, or relationships.",
            "Do not ask generic meta-questions such as 'Which statement is directly stated in the material?', 'What is this?', or 'Which option is correct?'.",
            "Do not use repetitive stems such as 'Which option best explains ...' for every question; vary the wording naturally.",
            "Each question must have exactly four concise options and one correct answer. Options should answer the same type of thing the question asks.",
            "Keep each option under 14 English words or 36 Chinese characters unless it is a formula.",
            "Keep the correct option similar in length and style to the three distractors. Do not make the correct option a long source sentence while the distractors are short fragments.",
            "For concept questions, options should usually be short answer phrases of comparable length, not full paragraphs.",
            "If a question asks for a formula, all four options must be formula-like expressions. If it asks for a definition or relation, do not use unrelated formulas as distractors.",
            "Do not generate more than one formula-recognition question unless formulas are the explicit focus of the chapter.",
            "When equations are relevant, use the actual LaTeX formula from the source, not only an equation number or placeholder.",
            "Do not reuse the same four options across different questions.",
            "Keep English source wording, formulas, variables, and technical terms in English. Use Chinese only as light explanation when helpful.",
            "Return valid JSON only with this shape: {\"exercises\":[{\"id\":\"ex_1\",\"question\":\"...\",\"options\":[\"A. ...\",\"B. ...\",\"C. ...\",\"D. ...\"],\"correct_answer\":\"A\",\"explanation\":\"...\"}]}",
        ]
        if feedback_guidance:
            requirements.append("教师历史赞踩反馈（用于本次生成方向，不是模型训练）：\n" + feedback_guidance)

        prompt = build_constrained_generation_prompt(
            task_title="生成课程材料测验题",
            user_input=chapter_title,
            source_content=chapter_content,
            learning_plan=learning_plan,
            requirements=requirements,
        )
        response = await self._call_deepseek(
            prompt,
            max_tokens=4200,
            system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT,
            read_timeout_seconds=_generation_read_timeout(),
        )
        try:
            payload = json.loads(_strip_json_fence(response))
            if isinstance(payload, list):
                return {"exercises": payload}
            if isinstance(payload, dict) and isinstance(payload.get("exercises"), list):
                return payload
            if isinstance(payload, dict) and "id" not in payload:
                payload["id"] = f"ex_{chapter_title.replace(' ', '_')}_1"
            return payload
        except json.JSONDecodeError as exc:
            raise ValueError(f"DeepSeek did not return valid exercise JSON: {response[:300]}") from exc
    def _build_lecture_prompt(self, graph_data: Dict, chapter_data: Dict, style: str) -> str:
        chapter_data = dict(chapter_data or {})
        title = chapter_data.get("title", "未命名章节")
        content = expand_formula_references(chapter_data.get("content", ""))
        chapter_data["content"] = content
        evidence = evidence_from_graph(graph_data, query=f"{title}\n{content[:1200]}", chapter_data=chapter_data, limit=10)
        if content.strip():
            chapter_evidence = {
                "index": 1,
                "id": "chapter_content",
                "label": title,
                "type": "chapter_content",
                "content": content[:1800],
                "source": "chapter",
            }
            evidence = [chapter_evidence] + [
                item for item in evidence if isinstance(item, dict) and item.get("id") != "chapter_content"
            ]
        relations = relation_evidence_from_graph(graph_data, evidence)
        learning_plan = build_learning_plan(
            query=title,
            evidence=evidence,
            relations=relations,
            learner_intent="explain",
            learning_level="beginner",
            task="lecture",
            chapter_data=chapter_data,
        )
        return build_constrained_generation_prompt(
            task_title="生成授课文案",
            user_input=title,
            source_content=content,
            learning_plan=learning_plan,
            requirements=[
                f"教学风格：{style}。",
                "生成完整授课文案，使用 Markdown 二级/三级标题组织，不要只给提纲。",
                "必须覆盖：导入、核心概念讲解、关系链路、例题或推导、课堂提问、易错点、收束总结。",
                "讲解顺序必须跟随 LearningPlan 中的知识点和关系，不要跳到未授权高级内容。",
                "每个核心段落都要落到证据或章节正文，不要泛泛而谈。",
                "章节正文或证据为英文时，术语、公式、变量名和关键定义保留英文；中文讲解只做辅助，不要改写原义。",
                "长度控制在 1400-2200 字；若内容复杂，优先保证完整性，不要突然截断。",
                "只输出授课文案本身，不要附加自检说明。",
            ],
        )

    def _build_qa_prompt(self, graph_data: Dict, question: str, search_results: Optional[List[Dict]] = None) -> str:
        if search_results:
            evidence = evidence_from_rag(search_results, limit=8)
            relations = []
        else:
            evidence = evidence_from_graph(graph_data, query=question, limit=8)
            relations = relation_evidence_from_graph(graph_data, evidence)
        learning_plan = build_learning_plan(
            query=question,
            evidence=evidence,
            relations=relations,
            learner_intent=None,
            learning_level="beginner",
            task="qa",
        )

        return f"""请回答学生问题。

学生问题：
{question}

可参考的课程/图谱上下文：
{format_evidence(learning_plan.get("evidence") or [])}

回答规则：
1. 先直接回答问题，不要先说“依据不足”。
2. 如果问题是公式、符号、定义、推导、例题，请给出公式本身，并用 LaTeX 写清楚，例如 `$...$` 或 `$$...$$`。
3. 如果上下文没有命中，但这是常见数学、机器学习或课程基础知识，可以用通用知识回答，并标注“通用说明”；不要空泛拒答。
4. 如果上下文命中英文材料，英文术语、公式、变量名和关键定义保持英文。
5. 只有在问题询问某个课程私有材料、而上下文完全没有该材料时，才说明需要补充原文。
6. 可以引用依据编号，但不要输出 LearningPlan、自检过程或内部约束说明。"""

    async def _call_deepseek(
        self,
        prompt: str,
        max_tokens: int = 2000,
        system_prompt: Optional[str] = None,
        read_timeout_seconds: object = _DEFAULT_TIMEOUT,
    ) -> str:
        if not self.api_key:
            raise ValueError("未配置 DeepSeek API 密钥，请设置 DEEPSEEK_API_KEY 环境变量")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a concise, reliable teaching assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }

        if read_timeout_seconds is _DEFAULT_TIMEOUT:
            read_timeout_value = _parse_read_timeout(os.getenv("DEEPSEEK_READ_TIMEOUT_SECONDS"), 90.0)
        else:
            read_timeout_value = read_timeout_seconds
        timeout = httpx.Timeout(connect=10.0, read=read_timeout_value, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if response.status_code != 200:
                raise Exception(f"DeepSeek API 调用失败: {response.status_code} - {response.text}")
            result = response.json()
            try:
                return result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise Exception(f"DeepSeek API 返回格式不正确: {exc}") from exc


# Compatibility exports for existing imports.
ClaudeAPIClient = DeepSeekAPIClient
_deepseek_client: Optional[DeepSeekAPIClient] = None


def get_deepseek_client() -> DeepSeekAPIClient:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekAPIClient()
    return _deepseek_client


def get_claude_client() -> DeepSeekAPIClient:
    return get_deepseek_client()


def _strip_json_fence(text: str) -> str:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = clean.removeprefix("```json").removeprefix("```").strip()
        if clean.endswith("```"):
            clean = clean[:-3].strip()
    first_obj = clean.find("{")
    last_obj = clean.rfind("}")
    first_arr = clean.find("[")
    last_arr = clean.rfind("]")
    if first_obj >= 0 and last_obj > first_obj:
        clean = clean[first_obj:last_obj + 1]
    elif first_arr >= 0 and last_arr > first_arr:
        clean = clean[first_arr:last_arr + 1]
    return clean
