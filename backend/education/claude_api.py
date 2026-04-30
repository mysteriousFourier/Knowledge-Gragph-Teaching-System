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
    relation_evidence_from_graph,
)

DEFAULT_DEEPSEEK_FLASH_MODEL = "deepseek-v4flash"
DEFAULT_DEEPSEEK_PRO_MODEL = "deepseek-v4pro"


def get_deepseek_model(kind: str = "flash") -> str:
    """Resolve task-specific DeepSeek model names."""
    if kind == "pro":
        return (
            os.getenv("DEEPSEEK_PRO_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or DEFAULT_DEEPSEEK_PRO_MODEL
        ).strip() or DEFAULT_DEEPSEEK_PRO_MODEL
    return (os.getenv("DEEPSEEK_FLASH_MODEL") or DEFAULT_DEEPSEEK_FLASH_MODEL).strip() or DEFAULT_DEEPSEEK_FLASH_MODEL


class DeepSeekAPIClient:
    """DeepSeek chat-completions client for lecture, QA, and exercise generation."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
        self.model = (model or get_deepseek_model("flash")).strip() or DEFAULT_DEEPSEEK_FLASH_MODEL

    async def generate_lecture(self, graph_data: Dict, chapter_data: Dict, style: str = "引导式教学") -> str:
        prompt = self._build_lecture_prompt(graph_data, chapter_data, style)
        return await self._call_deepseek(prompt, system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT)

    async def answer_question(self, graph_data: Dict, question: str, search_results: Optional[List[Dict]] = None) -> str:
        prompt = self._build_qa_prompt(graph_data, question, search_results)
        return await self._call_deepseek(prompt, max_tokens=900, system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT)

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
    ) -> Dict:
        chapter_data = {"title": chapter_title, "content": chapter_content}
        evidence = evidence_from_graph(
            graph_data,
            query=f"{chapter_title}\n{chapter_content[:800]}",
            chapter_data=chapter_data,
            limit=8,
        )
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
        prompt = build_constrained_generation_prompt(
            task_title="生成知识图谱约束的单选练习题",
            user_input=chapter_title,
            source_content=chapter_content,
            learning_plan=learning_plan,
            requirements=[
                f"生成 {max(1, count)} 道单选题；如果前端只支持单题，返回最核心的一题。",
                "题干、选项、正确答案和解析都必须能在 LearningPlan.evidence 中找到依据。",
                "不要把图谱中没有的高级概念做成正确选项。",
                "解析必须标注依据编号，如“依据[1]”。",
                "只返回 JSON，不要返回额外说明。",
                'JSON 格式：{"exercises":[{"id":"题目ID","question":"题目内容","options":["A. ...","B. ...","C. ...","D. ..."],"correct_answer":"A/B/C/D","explanation":"答案解析"}]}',
            ],
        )
        response = await self._call_deepseek(prompt, max_tokens=1000, system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT)
        try:
            payload = json.loads(_strip_json_fence(response))
            if isinstance(payload, list):
                return {"exercises": payload}
            if isinstance(payload, dict) and isinstance(payload.get("exercises"), list):
                return payload
            if isinstance(payload, dict) and "id" not in payload:
                payload["id"] = f"ex_{chapter_title.replace(' ', '_')}_1"
            return payload
        except json.JSONDecodeError:
            return {
                "id": f"ex_{chapter_title.replace(' ', '_')}_1",
                "question": f"关于 {chapter_title}，以下哪项说法是正确的？",
                "options": ["A. 选项一", "B. 选项二", "C. 选项三", "D. 选项四"],
                "correct_answer": "A",
                "explanation": response,
            }

    def _build_lecture_prompt(self, graph_data: Dict, chapter_data: Dict, style: str) -> str:
        title = chapter_data.get("title", "未命名章节")
        content = chapter_data.get("content", "")
        evidence = evidence_from_graph(graph_data, query=f"{title}\n{content[:1200]}", chapter_data=chapter_data, limit=10)
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
                f"教学风格为：{style}。",
                "文案适合课堂讲解，结构清晰，便于教师直接备课使用。",
                "讲解顺序必须跟随 LearningPlan 中的知识点和关系，不要跳到未授权高级内容。",
                "适当加入启发式提问，但问题必须基于图谱证据。",
                "长度控制在 600-1000 字左右。",
                "不要附加解释或前缀，只输出授课文案。",
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

        return build_constrained_generation_prompt(
            task_title="回答学生问题",
            user_input=question,
            learning_plan=learning_plan,
            requirements=[
                "只使用上述 LearningPlan 和 evidence 回答，不要编造图谱中没有的信息。",
                "如果依据不足，明确说明“当前图谱依据不足”，并指出还需要什么信息。",
                "回答要直接、清晰，适合学生阅读。",
                "必要时引用依据编号，如“依据[2]”。",
            ],
        )

    async def _call_deepseek(
        self,
        prompt: str,
        max_tokens: int = 2000,
        system_prompt: Optional[str] = None,
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

        timeout = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0)
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
    return clean
