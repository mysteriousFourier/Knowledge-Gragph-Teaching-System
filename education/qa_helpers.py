from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from KGTS.education.claude_api import DeepSeekAPIClient, get_deepseek_model
from KGTS.education.kg_constraints import (
    build_learning_plan,
    check_generation_consistency,
    evidence_from_graph,
    evidence_from_rag,
    relation_evidence_from_graph,
)
from KGTS.core.bridge import build_local_answer, build_rag_context


def _build_plan_from_rag(question: str, rag: Dict[str, Any], task: str = "qa") -> Dict[str, Any]:
    evidence = evidence_from_rag(rag.get("llm_context") or [], limit=8)
    return build_learning_plan(
        query=question,
        evidence=evidence,
        learner_intent=None,
        learning_level="beginner",
        task=task,
    )


def _safe_consistency_report(output: str, learning_plan: Dict[str, Any], task: str) -> Dict[str, Any]:
    try:
        return check_generation_consistency(output, learning_plan, task=task)
    except Exception as exc:
        return {
            "knowledge_support_ratio": 0.0,
            "unsupported_concept_rate": 1.0,
            "learning_goal_alignment": 0.0,
            "difficulty_match": "unknown",
            "hint_policy_violated": False,
            "is_safe_to_show": bool(str(output or "").strip()),
            "warnings": [f"Consistency check unavailable: {exc}"],
        }


def _build_question_fallback_response(
    question: str,
    *,
    model: Optional[str] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        local = build_local_answer(question)
    except Exception as exc:
        local = {
            "answer": "Knowledge graph and memory retrieval are currently unavailable, so I cannot produce a grounded answer. Please check that the backend service and graph data are available.",
            "context": "",
            "llm_context": [],
            "keyword_hits": [],
            "semantic_hits": [],
            "memory_hits": [],
        }
        warning = f"{warning or 'Question fallback used'}; local retrieval failed: {exc}"

    sources = local.get("llm_context") or []
    learning_plan = build_learning_plan(
        query=question,
        evidence=evidence_from_rag(sources, limit=8),
        learner_intent=None,
        learning_level="beginner",
        task="qa",
    )
    answer = str(local.get("answer") or "").strip() or "I could not find relevant graph or memory evidence for this question. Please add the source passage or ask with a more specific term."
    payload = {
        "success": True,
        "answer": answer,
        "question": question,
        "model": model or get_deepseek_model("flash"),
        "answered_at": datetime.now().isoformat(),
        "retrieval_context": local.get("context") or "",
        "sources": sources,
        "learning_plan": learning_plan,
        "consistency_report": _safe_consistency_report(answer, learning_plan, task="qa"),
        "keyword_hits": local.get("keyword_hits") or [],
        "semantic_hits": local.get("semantic_hits") or [],
        "vector_hits": local.get("vector_hits") or local.get("semantic_hits") or [],
        "retrieval_mode": local.get("retrieval_mode"),
        "retrieval_stats": local.get("retrieval_stats") or {},
        "graphrag_context": local.get("graphrag_context") or {},
        "graph_paths": local.get("graph_paths") or [],
        "formula_context": local.get("formula_context") or [],
        "memory_hits": local.get("memory_hits") or [],
    }
    if warning:
        payload["warning"] = warning
    return payload


def _build_plan_from_graph(
    *,
    query: str,
    graph_data: Optional[Dict[str, Any]],
    task: str,
    chapter_data: Optional[Dict[str, Any]] = None,
    learning_level: str = "beginner",
) -> Dict[str, Any]:
    evidence = evidence_from_graph(graph_data, query=query, chapter_data=chapter_data, limit=10)
    relations = relation_evidence_from_graph(graph_data, evidence)
    return build_learning_plan(
        query=query,
        evidence=evidence,
        relations=relations,
        learner_intent=None,
        learning_level=learning_level,
        task=task,
        chapter_data=chapter_data,
    )


async def answer_with_retrieval(question: str, api_key: Optional[str] = None, timeout_seconds: int = 40) -> Dict[str, Any]:
    qa_model = get_deepseek_model("flash")
    try:
        rag = build_rag_context(question, limit=6)
        learning_plan = _build_plan_from_rag(question, rag, task="qa")
    except Exception as exc:
        return _build_question_fallback_response(
            question,
            model=qa_model,
            warning=f"Retrieval unavailable; used local graph fallback: {exc}",
        )
    fallback_lines = [
        f"- [{item.get('source', 'graph')}] {item.get('label', 'context')}: {str(item.get('content') or '')[:180]}"
        for item in learning_plan.get("evidence", [])
    ]
    fallback_answer = (
        "Based on retrieved graph/memory evidence, keeping source wording in its original language:\n" + "\n".join(fallback_lines)
        if fallback_lines
        else "I could not find directly relevant evidence in the knowledge graph or memory store. Please add the source passage or ask with a more specific term."
    )

    try:
        client = DeepSeekAPIClient(api_key=api_key, model=qa_model)
        answer = await asyncio.wait_for(
            client.answer_question({"nodes": []}, question, rag["llm_context"]),
            timeout=timeout_seconds,
        )
        consistency_report = _safe_consistency_report(answer, learning_plan, task="qa")
        return {
            "success": True,
            "answer": answer,
            "question": question,
            "model": client.model,
            "answered_at": datetime.now().isoformat(),
            "retrieval_context": rag["context"],
            "sources": rag["llm_context"],
            "learning_plan": learning_plan,
            "consistency_report": consistency_report,
            "retrieval_mode": rag.get("retrieval_mode"),
            "retrieval_stats": rag.get("retrieval_stats") or {},
            "graphrag_context": rag.get("graphrag_context") or {},
            "vector_hits": rag.get("vector_hits") or rag.get("semantic_hits") or [],
            "semantic_hits": rag.get("semantic_hits") or [],
            "graph_paths": rag.get("graph_paths") or [],
            "formula_context": rag.get("formula_context") or [],
        }
    except asyncio.TimeoutError:
        warning = "大模型回答超时，已使用图谱和记忆检索结果回答"
    except ValueError:
        warning = "DeepSeek API 未配置，已使用图谱和记忆检索结果回答"
    except Exception as exc:
        warning = f"大模型回答失败，已使用图谱和记忆检索结果回答：{exc}"

    return {
        "success": True,
        "answer": fallback_answer,
        "question": question,
        "model": qa_model,
        "warning": warning,
        "answered_at": datetime.now().isoformat(),
        "retrieval_context": rag["context"],
        "sources": rag["llm_context"],
        "learning_plan": learning_plan,
        "consistency_report": _safe_consistency_report(fallback_answer, learning_plan, task="qa"),
        "memory_hits": rag.get("memory_hits"),
        "semantic_hits": rag.get("semantic_hits"),
        "vector_hits": rag.get("vector_hits") or rag.get("semantic_hits"),
        "retrieval_mode": rag.get("retrieval_mode"),
        "retrieval_stats": rag.get("retrieval_stats") or {},
        "graphrag_context": rag.get("graphrag_context") or {},
        "graph_paths": rag.get("graph_paths") or [],
        "formula_context": rag.get("formula_context") or [],
    }
