"""
教育模式API服务器 - 为前端提供HTTP接口
集成MCP客户端和Claude API
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import asyncio
import hmac
import os
import re
import sys
import uvicorn
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import (
    DEFAULT_EDUCATION_API_PORT,
    get_auth_config,
    get_bind_host,
    get_env_int,
    load_root_env,
)

load_root_env()

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from mcp_client import get_mcp_client, close_mcp_client, call_mcp_tool
from deepseek_api import DeepSeekAPIClient, get_deepseek_model
from kg_constraints import (
    build_learning_plan,
    check_generation_consistency,
    evidence_from_graph,
    evidence_from_rag,
    relation_evidence_from_graph,
)
from vector_backend_bridge import (
    build_frontend_graph,
    build_local_answer,
    build_rag_context,
    chapter_store,
    get_graph_schema,
    search_nodes as backend_search_nodes,
)


# 创建FastAPI应用
app = FastAPI(
    title="知识图谱教育系统API",
    description="提供授课文案生成、问答等教育功能",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)


# ==================== 请求模型 ====================

class GenerateLectureRequest(BaseModel):
    """生成授课文案请求"""
    chapter_id: str = Field(..., description="章节ID")
    chapter_title: str = Field(..., description="章节标题")
    chapter_content: str = Field(..., description="章节内容")
    style: str = Field("引导式教学", description="教学风格")
    api_key: Optional[str] = Field(None, description="用户提供的DeepSeek API密钥")
    model: Optional[str] = Field(None, description="DeepSeek 模型名")


class AskQuestionRequest(BaseModel):
    """问答请求"""
    question: str = Field(..., description="问题")
    api_key: Optional[str] = Field(None, description="用户提供的DeepSeek API密钥")


class LearningPlanRequest(BaseModel):
    """构建知识图谱约束学习计划请求"""
    query: str = Field(..., description="学习者问题或教师任务")
    chapter_id: Optional[str] = Field(None, description="章节ID")
    task: str = Field("qa", description="任务类型: qa, lecture, exercise, feedback")
    learning_level: str = Field("beginner", description="学习者水平")


class NaturalSupplementRequest(BaseModel):
    """自然补充请求"""
    original_text: str = Field(..., description="原始文案内容")
    supplement: str = Field(..., description="需要补充的内容")
    insert_position: Optional[str] = Field(None, description="插入位置: 'top'在开头添加, 'end'在结尾添加, 'replace'替换选中部分")
    save_draft_if_fail: bool = Field(False, description="如果无法融入是否保存为草稿")
    api_key: Optional[str] = Field(None, description="用户提供的DeepSeek API密钥")


class AddNodeRequest(BaseModel):
    """添加节点请求"""
    content: str = Field(..., description="节点内容")
    type: str = Field(..., description="节点类型: chapter, concept, note, observation")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class UpdateNodeRequest(BaseModel):
    """更新节点请求"""
    node_id: str = Field(..., description="节点ID")
    content: Optional[str] = Field(None, description="新内容")
    metadata: Optional[Dict[str, Any]] = Field(None, description="新元数据")


class LoginRequest(BaseModel):
    """学生登录请求"""
    username: str = Field(..., description="学号/用户名")
    password: str = Field(..., description="密码")


class StudentLoginRequest(LoginRequest):
    """Student login request"""


class TeacherLoginRequest(LoginRequest):
    """Teacher login request"""


class ChapterRequest(BaseModel):
    """章节内容请求"""
    chapter_id: str = Field(..., description="章节ID")


class MarkChapterRequest(BaseModel):
    """标记章节为已学习"""
    chapter_id: str = Field(..., description="章节ID")
    student_id: Optional[str] = Field(None, description="学生ID")


class ExerciseRequest(BaseModel):
    """练习题请求"""
    chapter_id: str = Field(..., description="章节ID")


class CheckAnswerRequest(BaseModel):
    """检查答案请求"""
    exercise_id: str = Field(..., description="练习题ID")
    question: str = Field(..., description="题目")
    answer: str = Field(..., description="用户答案")
    chapter_id: str = Field(..., description="章节ID")
    correct_answer: Optional[str] = Field(None, description="题目标准答案")
    explanation: Optional[str] = Field(None, description="题目解析")


class QuestionRequest(BaseModel):
    """学生提问请求"""
    question: str = Field(..., description="问题")
    student_id: Optional[str] = Field(None, description="学生ID")
    api_key: Optional[str] = Field(None, description="用户提供的DeepSeek API密钥")


class SaveChapterRequest(BaseModel):
    """保存章节请求"""
    title: str = Field(..., description="章节标题")
    content: Optional[str] = Field(None, description="章节内容")
    graph_data: Optional[Dict[str, Any]] = Field(None, description="知识图谱数据")


class SaveLectureRequest(BaseModel):
    """保存授课文案请求"""
    chapter_id: str = Field(..., description="章节ID")
    lecture_content: str = Field(..., description="授课文案")
    graph_data: Optional[Dict[str, Any]] = Field(None, description="知识图谱数据")


class GenerateExercisesRequest(BaseModel):
    """生成练习题请求"""
    chapter_id: str = Field(..., description="章节ID")
    chapter_title: str = Field(..., description="章节标题")
    chapter_content: str = Field(..., description="章节内容")
    count: int = Field(5, description="生成题目数量")
    api_key: Optional[str] = Field(None, description="用户提供的DeepSeek API密钥")
    model: Optional[str] = Field(None, description="DeepSeek 模型名")
    force_regenerate: bool = Field(False, description="是否强制重建题库")


# ==================== API接口 ====================

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "知识图谱教育系统API",
        "version": "1.0.0",
        "endpoints": {
            "teacher": {
                "login": "/api/teacher/login",
                "generate_lecture": "/api/education/generate-lecture",
                "ask_question": "/api/education/ask-question",
                "natural_supplement": "/api/education/natural-supplement",
                "learning_plan": "/api/education/learning-plan",
                "get_graph": "/api/education/graph",
                "add_node": "/api/education/add-node",
                "update_node": "/api/education/update-node",
                "search_nodes": "/api/education/search-nodes"
            },
            "student": {
                "login": "/api/student/login",
                "chapter": "/api/student/chapter",
                "mark_chapter": "/api/student/mark-chapter",
                "exercises": "/api/student/exercises",
                "check_answer": "/api/student/check-answer",
                "question": "/api/student/question",
                "review": "/api/student/review"
            }
        }
    }


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/config-status")
async def config_status():
    """Return non-secret runtime configuration status for the frontend settings panel."""
    return {
        "success": True,
        "deepseek_api_key_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        "flash_model": get_deepseek_model("flash"),
        "pro_model": get_deepseek_model("pro"),
        "env_file": str(ROOT_DIR / ".env"),
    }


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
            "answer": "当前知识图谱和记忆检索暂不可用，无法生成可靠回答。请确认后端服务和图谱数据已启动。",
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
    answer = str(local.get("answer") or "").strip() or "当前知识图谱证据不足，未检索到可用于回答该问题的内容。"
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


def _normalize_exercise_options(options: Any) -> List[str]:
    if isinstance(options, dict):
        normalized = []
        for key, value in options.items():
            key_text = str(key).strip()
            value_text = str(value).strip()
            if not value_text:
                continue
            if key_text and len(key_text) <= 3:
                normalized.append(f"{key_text}. {value_text}")
            else:
                normalized.append(value_text)
        return normalized

    if isinstance(options, list):
        normalized = []
        for item in options:
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("label") or item.get("id") or "").strip()
                text = str(item.get("text") or item.get("content") or item.get("value") or "").strip()
                if not text:
                    continue
                normalized.append(f"{key}. {text}" if key and len(key) <= 3 else text)
            else:
                text = str(item).strip()
                if text:
                    normalized.append(text)
        return normalized

    return []


def _normalize_correct_answer(value: Any) -> str:
    if isinstance(value, int):
        return chr(65 + value) if 0 <= value < 26 else str(value)
    text = str(value or "").strip()
    if not text:
        return ""
    match = text[:1].upper()
    return match if "A" <= match <= "Z" else text


def _is_placeholder_exercise(item: Dict[str, Any], question: str, options: List[str]) -> bool:
    text = " ".join([str(item.get("id") or ""), question, " ".join(options)])
    placeholder_markers = [
        "sample",
        "示例",
        "测试",
        "选项一",
        "选项二",
        "选项三",
        "选项四",
        "当前图谱是否有足够证据",
        "kg_gap",
    ]
    return any(marker.lower() in text.lower() for marker in placeholder_markers)


def _clean_exercise_text(value: Any, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^[#>*\-\d.)、\s]+", "", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip("，。；;,. ") + "..."
    return text


def _chapter_content_evidence(
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_content: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    content = str(chapter_content or "").strip()
    if not content:
        return []

    chunks = re.split(r"(?<=[。！？.!?])\s*|\n+", content)
    candidates: List[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        clean = _clean_exercise_text(chunk, limit=220)
        if len(clean) < 8 or clean in seen:
            continue
        seen.add(clean)
        candidates.append(clean)
        if len(candidates) >= limit:
            break

    if not candidates:
        clean = _clean_exercise_text(content, limit=220)
        if clean:
            candidates.append(clean)

    return [
        {
            "index": index,
            "id": f"{chapter_id}_content_{index}",
            "label": _clean_exercise_text(item, limit=36) or chapter_title or f"章节内容 {index}",
            "type": "chapter_content",
            "content": item,
            "source": "chapter",
        }
        for index, item in enumerate(candidates, start=1)
    ]


def _exercise_distractor_pool(
    sources: List[Dict[str, Any]],
    current_index: int,
    chapter_title: str,
) -> List[str]:
    pool: List[str] = []
    for index, item in enumerate(sources):
        if index == current_index:
            continue
        label = _clean_exercise_text(item.get("label"), limit=70)
        content = _clean_exercise_text(item.get("content"), limit=130)
        if label and content and label not in content:
            pool.append(f"{label} 的核心内容是：{content}")
        elif content:
            pool.append(content)
    pool.extend(
        [
            f"{chapter_title or '本章'}中的知识点可以脱离图谱证据任意扩展。",
            "只要出现相似关键词，就可以忽略原始定义和上下文。",
            "该知识点与本章主题没有关系，因此不需要结合上下文理解。",
        ]
    )

    result: List[str] = []
    seen: set[str] = set()
    for item in pool:
        clean = _clean_exercise_text(item, limit=150)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
        if len(result) >= 8:
            break
    return result


def _build_local_choice_exercise(
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_content: str,
    source: Dict[str, Any],
    all_sources: List[Dict[str, Any]],
    source_index: int,
    exercise_index: int,
) -> Dict[str, Any]:
    label = _clean_exercise_text(source.get("label") or chapter_title or f"知识点 {exercise_index}", limit=80)
    content = _clean_exercise_text(source.get("content") or label, limit=170)
    if not content:
        raise ValueError("题库生成失败：章节内容和图谱证据为空，无法生成可靠练习题")

    distractors = _exercise_distractor_pool(all_sources, source_index, chapter_title)
    options = [content]
    for distractor in distractors:
        if distractor != content:
            options.append(distractor)
        if len(options) == 4:
            break
    while len(options) < 4:
        options.append(f"该说法缺少《{chapter_title or chapter_id}》中的直接证据支持。")

    options = options[:4]
    correct_slot = (exercise_index - 1) % len(options)
    if correct_slot:
        correct_option = options.pop(0)
        options.insert(correct_slot, correct_option)

    letters = ["A", "B", "C", "D"]
    formatted_options = [f"{letters[index]}. {option}" for index, option in enumerate(options)]
    correct_answer = letters[correct_slot]
    evidence = [source]
    plan = build_learning_plan(
        query=chapter_title or label,
        evidence=evidence,
        learner_intent="practice",
        task="practice",
        chapter_data={"id": chapter_id, "title": chapter_title, "content": chapter_content},
    )
    return {
        "id": f"ex_{re.sub(r'[^a-zA-Z0-9_-]+', '_', chapter_id or 'chapter')}_{exercise_index}",
        "question": f"根据《{chapter_title or chapter_id}》的内容，关于“{label}”哪一项表述最符合当前证据？",
        "options": formatted_options,
        "correct_answer": correct_answer,
        "explanation": f"正确选项来自证据[{source.get('index', exercise_index)}]：{content}",
        "source_evidence": evidence,
        "learning_plan": plan,
    }


def _get_exercise_evidence(chapter_id: str, chapter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    chapter = chapter or chapter_store.get_chapter(chapter_id)
    query = " ".join(
        part
        for part in [
            chapter_id,
            str((chapter or {}).get("title") or ""),
            str((chapter or {}).get("content") or "")[:800],
        ]
        if part
    )
    graph_data = (chapter or {}).get("graph_data")
    evidence = evidence_from_graph(graph_data, query=query, chapter_data=chapter, limit=8)
    if evidence:
        return evidence

    try:
        evidence = evidence_from_graph(build_frontend_graph(), query=query, chapter_data=chapter, limit=8)
    except Exception:
        evidence = []
    if evidence:
        return evidence

    try:
        rag = build_rag_context(query or chapter_id, limit=6)
        return evidence_from_rag(rag.get("llm_context") or [], limit=6)
    except Exception:
        return []


def _normalize_exercise_bank(payload: Any) -> List[Dict[str, Any]]:
    raw_items: Any
    if isinstance(payload, dict) and isinstance(payload.get("exercises"), list):
        raw_items = payload["exercises"]
    elif isinstance(payload, dict) and isinstance(payload.get("exercise_bank"), list):
        raw_items = payload["exercise_bank"]
    elif isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = [payload]
    else:
        raw_items = []

    bank: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or item.get("stem") or item.get("prompt") or item.get("title") or "").strip()
        options = _normalize_exercise_options(item.get("options") or item.get("choices") or item.get("answers"))
        if not question or not options:
            continue
        if _is_placeholder_exercise(item, question, options):
            continue
        exercise = dict(item)
        exercise.setdefault("id", f"exercise_{index}")
        exercise["question"] = question
        exercise["options"] = options
        answer = _normalize_correct_answer(
            item.get("correct_answer")
            or item.get("answer")
            or item.get("correct")
            or item.get("correct_option")
        )
        if answer:
            exercise["correct_answer"] = answer
        bank.append(exercise)
    return bank


def _build_local_exercise_response(
    request: GenerateExercisesRequest,
    *,
    graph_data: Optional[Dict[str, Any]] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    chapter_payload = {
        "id": request.chapter_id,
        "title": request.chapter_title,
        "content": request.chapter_content,
    }
    if isinstance(graph_data, dict):
        chapter_payload["graph_data"] = graph_data

    evidence = _get_exercise_evidence(request.chapter_id, chapter_payload)
    exercise_bank = _build_local_exercise_bank(
        chapter_id=request.chapter_id,
        chapter_title=request.chapter_title,
        chapter_content=request.chapter_content,
        evidence=evidence,
        count=request.count,
    )
    saved_chapter = chapter_store.save_exercise_bank(
        chapter_id=request.chapter_id,
        exercises=exercise_bank,
    )
    first_exercise = exercise_bank[0]
    learning_plan = first_exercise.get("learning_plan") or build_learning_plan(
        query=request.chapter_title or request.chapter_id,
        evidence=evidence,
        task="practice",
        chapter_data=chapter_payload,
    )
    payload = {
        "success": True,
        "exercise": first_exercise,
        "exercise_bank": exercise_bank,
        "chapter": saved_chapter,
        "learning_plan": learning_plan,
        "consistency_report": _safe_consistency_report(str(exercise_bank), learning_plan, task="practice"),
        "generated_at": datetime.now().isoformat(),
        "cached": False,
        "fallback": True,
    }
    if warning:
        payload["warning"] = warning
    return payload


def _build_local_exercise_bank(
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_content: str,
    evidence: List[Dict[str, Any]],
    count: int = 5,
) -> List[Dict[str, Any]]:
    target_count = max(1, min(max(count, 1), 10))
    content_evidence = _chapter_content_evidence(
        chapter_id=chapter_id,
        chapter_title=chapter_title,
        chapter_content=chapter_content,
        limit=target_count,
    )
    source_evidence = content_evidence + (evidence or [])
    if not source_evidence:
        raise ValueError("题库生成失败：章节内容和图谱证据为空，无法生成可靠练习题")

    normalized_sources = []
    for index, item in enumerate(source_evidence, start=1):
        if not isinstance(item, dict):
            continue
        content = _clean_exercise_text(item.get("content") or item.get("label"), limit=220)
        if not content:
            continue
        normalized = dict(item)
        normalized["index"] = normalized.get("index") or index
        normalized["label"] = _clean_exercise_text(normalized.get("label") or chapter_title or f"知识点 {index}", limit=80)
        normalized["content"] = content
        normalized.setdefault("source", "graph")
        normalized_sources.append(normalized)

    if not normalized_sources:
        raise ValueError("题库生成失败：没有可用于组题的有效知识点")

    bank: List[Dict[str, Any]] = []
    for index, item in enumerate(normalized_sources[:target_count], start=1):
        bank.append(
            _build_local_choice_exercise(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                source=item,
                all_sources=normalized_sources,
                source_index=index - 1,
                exercise_index=index,
            )
        )
    return bank


async def answer_with_retrieval(question: str, api_key: Optional[str] = None, timeout_seconds: int = 40) -> Dict[str, Any]:
    """Answer with retrieved graph context, then fall back to local retrieval."""
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
        "基于当前图谱和记忆检索，相关内容如下：\n" + "\n".join(fallback_lines)
        if fallback_lines
        else "当前图谱依据不足：图谱和记忆库中没有检索到与该问题直接相关的内容。"
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
        "memory_hits": rag["memory_hits"],
        "semantic_hits": rag["semantic_hits"],
    }


@app.post("/api/education/generate-lecture")
async def generate_lecture(request: GenerateLectureRequest):
    """Generate lecture text with KG constraints."""
    graph_data = None
    try:
        try:
            graph_data = await call_mcp_tool("read_graph")
        except Exception:
            try:
                graph_data = build_frontend_graph()
            except Exception:
                graph_data = None

        chapter_data = {
            "id": request.chapter_id,
            "title": request.chapter_title,
            "content": request.chapter_content,
        }
        learning_plan = _build_plan_from_graph(
            query=request.chapter_title,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            task="lecture",
            chapter_data=chapter_data,
        )
        if not learning_plan.get("evidence"):
            rag = build_rag_context(f"{request.chapter_title}\n{request.chapter_content[:800]}", limit=6)
            learning_plan = build_learning_plan(
                query=request.chapter_title,
                evidence=evidence_from_rag(rag.get("llm_context") or [], limit=6),
                learner_intent="explain",
                learning_level="beginner",
                task="lecture",
                chapter_data=chapter_data,
            )

        claude_client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=request.model or get_deepseek_model("pro"),
        )
        lecture_content = await claude_client.generate_lecture(
            graph_data if isinstance(graph_data, dict) else {"nodes": [], "relations": []},
            chapter_data,
            request.style,
        )

        return {
            "success": True,
            "content": lecture_content,
            "chapter_id": request.chapter_id,
            "style": request.style,
            "model": claude_client.model,
            "learning_plan": learning_plan,
            "consistency_report": _safe_consistency_report(lecture_content, learning_plan, task="lecture"),
            "generated_at": datetime.now().isoformat(),
        }
    except ValueError as e:
        if "API" in str(e).upper():
            return {
                "success": False,
                "error": "DeepSeek API is not configured",
                "message": "Please configure a DeepSeek API key in settings or DEEPSEEK_API_KEY.",
                "fallback": "Local generation is available.",
            }
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generate lecture failed: {str(e)}")

@app.post("/api/education/ask-question")
async def ask_question(request: AskQuestionRequest):
    """
    智能问答

    基于知识图谱回答问题
    """
    try:
        return await answer_with_retrieval(request.question, request.api_key, timeout_seconds=40)

        # 1. 从知识图谱搜索相关节点
        search_result = await call_mcp_tool(
            "search_nodes",
            {
                "keyword": request.question,
                "limit": 5
            }
        )

        # 2. 获取完整知识图谱
        graph_data = await call_mcp_tool("read_graph")

        # 3. 调用Claude生成答案
        # 使用用户提供的API密钥，如果没有则使用环境变量中的API密钥
        claude_client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=get_deepseek_model("flash"),
        )

        answer = await claude_client.answer_question(
            graph_data,
            request.question,
            search_result if isinstance(search_result, list) else [search_result]
        )

        return {
            "success": True,
            "answer": answer,
            "question": request.question,
            "answered_at": datetime.now().isoformat()
        }

    except ValueError as e:
        return _build_question_fallback_response(
            request.question,
            model=get_deepseek_model("flash"),
            warning=f"问答模型不可用，已使用本地图谱检索回答：{e}",
        )
    except Exception as e:
        return _build_question_fallback_response(
            request.question,
            model=get_deepseek_model("flash"),
            warning=f"问答服务异常，已使用本地图谱检索回答：{e}",
        )


@app.post("/api/education/learning-plan")
async def create_learning_plan(request: LearningPlanRequest):
    """返回本轮生成前实际使用的 KG 约束计划，便于教师检查图谱约束是否正确。"""
    try:
        chapter = chapter_store.get_chapter(request.chapter_id) if request.chapter_id else None
        graph_data = None
        if chapter and chapter.get("graph_data"):
            graph_data = chapter.get("graph_data")
        else:
            try:
                graph_data = build_frontend_graph()
            except Exception:
                graph_data = None

        plan = _build_plan_from_graph(
            query=request.query,
            graph_data=graph_data,
            task=request.task,
            chapter_data=chapter,
            learning_level=request.learning_level,
        )
        if not plan.get("evidence"):
            rag = build_rag_context(request.query, limit=6)
            plan = build_learning_plan(
                query=request.query,
                evidence=evidence_from_rag(rag.get("llm_context") or [], limit=6),
                learner_intent=None,
                learning_level=request.learning_level,
                task=request.task,
                chapter_data=chapter,
            )
        return {
            "success": True,
            "learning_plan": plan,
            "created_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"构建学习计划失败: {str(e)}")


@app.post("/api/education/natural-supplement")
async def natural_supplement(request: NaturalSupplementRequest):
    """
    自然补充

    将补充内容自然地融入原文，使用DeepSeek API智能处理
    """
    try:
        # 使用用户提供的API密钥，如果没有则使用环境变量中的API密钥
        claude_client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=get_deepseek_model("pro"),
        )

        result = await claude_client.natural_supplement(
            request.original_text,
            request.supplement
        )

        return {
            "success": True,
            "result": result,
            "model": claude_client.model,
        }

    except ValueError as e:
        if "API密钥" in str(e):
            # DeepSeek API未配置时使用简单过渡
            return {
                "success": True,
                "result": f"{request.original_text}\n\n{request.supplement}",
                "warning": "DeepSeek API未配置，请在设置中配置API密钥"
            }
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自然补充失败: {str(e)}")


@app.get("/api/education/graph")
async def get_graph():
    """
    获取知识图谱

    返回基于 vector_index_system 的真实知识图谱数据
    """
    try:
        return {
            "success": True,
            "data": build_frontend_graph(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取知识图谱失败: {str(e)}")


@app.post("/api/education/add-node")
async def add_node(request: AddNodeRequest):
    """
    添加节点

    向知识图谱添加新节点
    """
    try:
        result = await call_mcp_tool(
            "add_memory",
            {
                "content": request.content,
                "type": request.type,
                "metadata": request.metadata,
            },
        )
        return {
            "success": True,
            "node": result,
            "message": "节点已添加",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加节点失败: {str(e)}")


@app.put("/api/education/update-node")
async def update_node(request: UpdateNodeRequest):
    """
    更新节点

    更新知识图谱中现有节点
    """
    try:
        result = await call_mcp_tool(
            "update_memory",
            {
                "node_id": request.node_id,
                "content": request.content,
                "metadata": request.metadata,
            },
        )
        return {
            "success": True,
            "updated": result,
            "message": "节点已更新",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新节点失败: {str(e)}")


@app.get("/api/education/search-nodes")
async def search_nodes(keyword: str, node_type: Optional[str] = None, limit: int = 10):
    """
    搜索节点

    按关键词搜索知识图谱中的节点
    """
    try:
        return {
            "success": True,
            "results": backend_search_nodes(keyword, node_type=node_type, limit=limit),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索节点失败: {str(e)}")


@app.get("/api/education/schema")
async def get_schema():
    """
    获取图谱结构

    返回知识图谱的统计信息和结构
    """
    try:
        return {
            "success": True,
            "schema": get_graph_schema(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取图谱结构失败: {str(e)}")


# ==================== 章节管理API接口 ====================

@app.post("/api/education/save-chapter")
async def save_chapter(request: SaveChapterRequest):
    """
    保存章节

    保存新章节到本地章节存储，并同步到 vector_index_system
    """
    try:
        chapter_data = chapter_store.save_chapter(
            title=request.title,
            content=request.content,
            graph_data=request.graph_data,
        )

        return {
            "success": True,
            "chapter_id": chapter_data["id"],
            "chapter": chapter_data,
            "message": "章节保存成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存章节失败: {str(e)}")


@app.get("/api/education/list-chapters")
async def list_chapters():
    """
    获取章节列表

    返回所有已保存章节，并合并后端 chapter 节点
    """
    try:
        return {
            "success": True,
            "chapters": chapter_store.list_chapters(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节列表失败: {str(e)}")


@app.get("/api/education/get-chapter")
async def get_chapter(chapter_id: str):
    """
    获取章节数据

    返回指定章节的详细数据，包括授课文案和知识图谱
    """
    try:
        chapter = chapter_store.get_chapter(chapter_id)
        if not chapter:
            return {
                "success": False,
                "error": "章节不存在"
            }
        cleaned_bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
        chapter = dict(chapter)
        chapter["exercise_bank"] = cleaned_bank
        chapter["exercises"] = cleaned_bank[0] if cleaned_bank else None
        return {
            "success": True,
            "chapter": chapter
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节数据失败: {str(e)}")


@app.post("/api/education/save-lecture")
async def save_lecture(request: SaveLectureRequest):
    """
    保存授课文案

    将授课文案和知识图谱保存到指定章节
    """
    try:
        chapter = chapter_store.save_lecture(
            chapter_id=request.chapter_id,
            lecture_content=request.lecture_content,
            graph_data=request.graph_data,
        )
        return {
            "success": True,
            "chapter": chapter,
            "message": "授课文案保存成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存授课文案失败: {str(e)}")


# ==================== 学生端API接口 ====================

def verify_login_credentials(request: LoginRequest, role: str) -> dict[str, str] | None:
    auth = get_auth_config(role)
    if not auth["password"]:
        return None
    username_ok = hmac.compare_digest(request.username, auth["username"])
    password_ok = hmac.compare_digest(request.password, auth["password"])
    if not (username_ok and password_ok):
        return None
    return auth


@app.post("/api/teacher/login")
async def teacher_login(request: TeacherLoginRequest):
    """Teacher login validated on the backend so credentials are not shipped to the browser."""
    try:
        if not get_auth_config("teacher")["password"]:
            return {
                "success": False,
                "error": "教师端登录密码未配置，请在 .env 设置 APP_TEACHER_PASSWORD",
            }

        auth = verify_login_credentials(request, "teacher")
        if auth:
            return {
                "success": True,
                "user_id": auth["user_id"],
                "username": auth["username"],
                "role": "teacher",
                "message": "登录成功",
            }

        return {
            "success": False,
            "error": "用户名或密码错误",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")


@app.post("/api/student/login")
async def student_login(request: StudentLoginRequest):
    """
    学生登录

    验证学生身份
    """
    try:
        # 简单验证逻辑（实际应连接数据库）
        if not get_auth_config("student")["password"]:
            return {
                "success": False,
                "error": "学生端登录密码未配置，请在 .env 设置 APP_STUDENT_PASSWORD",
            }

        auth = verify_login_credentials(request, "student")
        if auth:
            return {
                "success": True,
                "user_id": auth["user_id"],
                "username": auth["username"],
                "role": "student",
                "message": "登录成功"
            }
        else:
            return {
                "success": False,
                "error": "用户名或密码错误"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")


@app.get("/api/student/chapter")
async def get_student_chapter(chapter_id: str):
    """
    获取章节内容

    返回指定章节的详细内容
    """
    try:
        stored_chapter = chapter_store.get_chapter(chapter_id)
        if stored_chapter:
            return {
                "success": True,
                "chapter_id": chapter_id,
                "title": stored_chapter.get("title", chapter_id),
                "content": stored_chapter.get("content") or stored_chapter.get("lecture_content") or "暂无课程内容",
                "notes": stored_chapter.get("lecture_content") or "授课文案暂无",
            }

        evidence = _get_exercise_evidence(chapter_id, {"id": chapter_id, "title": chapter_id, "content": ""})
        content_lines = [
            f"{item.get('label')}: {item.get('content')}"
            for item in evidence
            if item.get("content")
        ]
        chapter_data = {
            "title": f"章节 {chapter_id}",
            "content": "\n\n".join(content_lines) if content_lines else "当前图谱依据不足：暂无课程内容，请先由教师导入或保存章节知识图谱。",
        }

        return {
            "success": True,
            "chapter_id": chapter_id,
            "title": chapter_data["title"],
            "content": chapter_data["content"],
            "notes": "授课文案暂无"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节内容失败: {str(e)}")


@app.post("/api/student/mark-chapter")
async def mark_chapter_as_learned(request: MarkChapterRequest):
    """
    标记章节为已学习

    记录学生的学习进度（不依赖MCP时返回模拟响应）
    """
    try:
        result = chapter_store.mark_learned(
            request.chapter_id,
            request.student_id or "student_001",
        )
        return {
            "success": True,
            "message": "章节已标记为已学习",
            "chapter_id": request.chapter_id,
            "marked_at": result["learned_at"],
            "student_id": result["student_id"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标记章节失败: {str(e)}")


@app.post("/api/student/generate-exercises")
async def generate_exercises(request: GenerateExercisesRequest):
    """
    生成练习题

    基于章节内容和知识图谱，使用Claude生成练习题
    """
    graph_data = None
    try:
        cached_chapter = chapter_store.get_chapter(request.chapter_id)
        cached_bank = _normalize_exercise_bank((cached_chapter or {}).get("exercise_bank") or (cached_chapter or {}).get("exercises"))
        if cached_bank and not request.force_regenerate:
            return {
                "success": True,
                "exercise": cached_bank[0],
                "exercise_bank": cached_bank,
                "cached": True,
                "generated_at": (cached_chapter or {}).get("updated_at") or datetime.now().isoformat(),
            }

        # 1. 获取知识图谱
        try:
            graph_data = await call_mcp_tool("read_graph")
        except Exception:
            try:
                graph_data = build_frontend_graph()
            except Exception:
                graph_data = None
        chapter_data = {
            "id": request.chapter_id,
            "title": request.chapter_title,
            "content": request.chapter_content,
        }
        evidence = evidence_from_graph(
            graph_data if isinstance(graph_data, dict) else None,
            query=f"{request.chapter_title}\n{request.chapter_content[:800]}",
            chapter_data=chapter_data,
            limit=8,
        )
        learning_plan = _build_plan_from_graph(
            query=request.chapter_title,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            task="exercise",
            chapter_data=chapter_data,
        )
        if not learning_plan.get("evidence"):
            return _build_local_exercise_response(
                request,
                graph_data=graph_data if isinstance(graph_data, dict) else None,
                warning="当前图谱证据不足，已预创建本地兜底题库；请先补充章节相关图谱证据。",
            )

        # 2. 调用 DeepSeek 生成题库（结合知识图谱）
        claude_client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=request.model or get_deepseek_model("pro"),
        )

        exercise_timeout = float(os.getenv("EXERCISE_GENERATION_TIMEOUT_SECONDS", "45"))
        exercise_data = await asyncio.wait_for(
            claude_client.generate_exercises(
                request.chapter_title,
                request.chapter_content,
                request.count,
                graph_data,
            ),
            timeout=exercise_timeout,
        )
        exercise_bank = _normalize_exercise_bank(exercise_data)
        if not exercise_bank:
            raise ValueError("DeepSeek 返回的题库格式不可用")
        saved_chapter = chapter_store.save_exercise_bank(
            chapter_id=request.chapter_id,
            exercises=exercise_bank,
        )

        return {
            "success": True,
            "exercise": exercise_bank[0],
            "exercise_bank": exercise_bank,
            "chapter": saved_chapter,
            "model": claude_client.model,
            "learning_plan": learning_plan,
            "consistency_report": _safe_consistency_report(
                str(exercise_bank),
                learning_plan,
                task="practice",
            ),
            "generated_at": datetime.now().isoformat()
        }

    except asyncio.TimeoutError:
        return _build_local_exercise_response(
            request,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            warning="DeepSeek 题库生成超时，已使用章节内容和知识图谱证据预创建本地题库。",
        )
    except ValueError as e:
        return _build_local_exercise_response(
            request,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            warning=f"DeepSeek 题库生成不可用，已使用知识图谱证据预创建本地题库：{e}",
        )
    except Exception as e:
        try:
            return _build_local_exercise_response(
                request,
                graph_data=graph_data if isinstance(graph_data, dict) else None,
                warning=f"题库生成失败，已使用知识图谱证据预创建本地题库：{e}",
            )
        except Exception as fallback_error:
            raise HTTPException(status_code=500, detail=f"生成练习题失败: {fallback_error}")


@app.get("/api/student/exercises")
async def get_student_exercises(chapter_id: str):
    """
    获取练习题

    返回指定章节的练习题，题目必须由章节图谱或检索证据支撑。
    """
    try:
        chapter = chapter_store.get_chapter(chapter_id) or {
            "id": chapter_id,
            "title": chapter_id.replace("_", " "),
            "content": "",
        }
        cached_bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
        if cached_bank:
            return {
                "success": True,
                "chapter_id": chapter_id,
                "exercise": cached_bank[0],
                "exercise_bank": cached_bank,
                "cached": True,
            }

        evidence = _get_exercise_evidence(chapter_id, chapter)
        exercise_bank = _build_local_exercise_bank(
            chapter_id=chapter_id,
            chapter_title=chapter.get("title") or chapter_id,
            chapter_content=chapter.get("content") or "",
            evidence=evidence,
            count=5,
        )
        saved_chapter = chapter_store.save_exercise_bank(
            chapter_id=chapter_id,
            exercises=exercise_bank,
        )
        first_exercise = exercise_bank[0]

        return {
            "success": True,
            "chapter_id": chapter_id,
            "exercise": first_exercise,
            "exercise_bank": exercise_bank,
            "chapter": saved_chapter,
            "learning_plan": first_exercise.get("learning_plan"),
            "consistency_report": _safe_consistency_report(
                str(exercise_bank),
                first_exercise.get("learning_plan") or {},
                task="practice",
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取练习题失败: {str(e)}")


@app.post("/api/student/question")
async def student_ask_question_backend(request: QuestionRequest):
    """基于知识图谱和记忆检索回答学生问题。"""
    try:
        return await answer_with_retrieval(request.question, request.api_key, timeout_seconds=35)

        result = build_local_answer(request.question)
        return {
            "success": True,
            "answer": result["answer"],
            "question": request.question,
            "answered_at": datetime.now().isoformat(),
            "memory_hits": result["memory_hits"],
            "semantic_hits": result["semantic_hits"],
        }
    except Exception as e:
        return _build_question_fallback_response(
            request.question,
            model=get_deepseek_model("flash"),
            warning=f"问答服务异常，已使用本地图谱检索回答：{e}",
        )


@app.get("/api/student/review")
async def get_student_review_data_backend():
    """返回基于已保存章节和学习记录的复习数据。"""
    try:
        review = chapter_store.review()
        return {
            "success": True,
            "progress": review["progress"],
            "recommendations": review["recommendations"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取复习数据失败: {str(e)}")


@app.post("/api/student/check-answer")
async def check_student_answer_backend(request: CheckAnswerRequest):
    """Use KG-backed exercise evidence for lightweight answer checking."""
    try:
        user_answer = request.answer.strip()
        expected_answer = (request.correct_answer or "").strip()
        evidence = _get_exercise_evidence(
            request.chapter_id,
            {
                "id": request.chapter_id,
                "title": request.chapter_id,
                "content": request.question,
            },
        )
        learning_plan = build_learning_plan(
            query=f"{request.question}\n{user_answer}",
            evidence=evidence,
            learner_intent="feedback",
            learning_level="beginner",
            task="feedback",
            chapter_data={"id": request.chapter_id, "title": request.chapter_id, "content": request.question},
        )

        if expected_answer:
            is_correct = user_answer.upper() == expected_answer.upper()
            score = 1.0 if is_correct else 0.0
            if is_correct:
                feedback = "回答正确，且题目答案有图谱约束来源。"
                explanation = request.explanation or "答案与题目标准答案一致。"
            else:
                feedback = "答案暂不正确。先回到图谱证据定位相关概念，再重新判断。"
                first_evidence = (learning_plan.get("evidence") or [{}])[0]
                hint = first_evidence.get("content") or first_evidence.get("label") or "当前题目相关图谱证据"
                explanation = f"提示：请对照依据[{first_evidence.get('index', 1)}] {hint[:180]}"
        else:
            evidence_text = "\n".join(str(item.get("content") or "") for item in learning_plan.get("evidence") or [])
            is_correct = bool(user_answer and user_answer.lower() in evidence_text.lower())
            score = 0.7 if is_correct else 0.0
            feedback = (
                "答案能在当前图谱证据中找到直接支撑。"
                if is_correct
                else "当前图谱依据不足，无法确认该答案正确。请补充题目标准答案或相关图谱证据。"
            )
            explanation = (
                "判定依据来自当前图谱检索结果。"
                if is_correct
                else "系统不会用常识猜测答案；需要图谱证据或题目标准答案。"
            )

        return {
            "success": True,
            "is_correct": is_correct,
            "correctness_score": score,
            "feedback": feedback,
            "explanation": explanation,
            "correct_answer": "",
            "learning_plan": learning_plan,
            "consistency_report": _safe_consistency_report(
                f"{feedback}\n{explanation}",
                learning_plan,
                task="feedback",
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Check answer failed: {str(e)}")


@app.post("/api/student/question-legacy")
async def student_ask_question(request: QuestionRequest):
    """
    学生提问

    基于知识图谱回答学生问题（不依赖MCP时返回基础回答）
    """
    try:
        return await answer_with_retrieval(request.question, request.api_key, timeout_seconds=35)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回答问题失败: {str(e)}")


@app.get("/api/student/review-legacy")
async def get_student_review_data():
    """
    获取复习数据

    返回学生的学习进度和复习推荐
    """
    try:
        # 模拟学习进度和推荐（不依赖MCP）
        recommendations = [
            {
                "type": "需要复习",
                "content": "建议复习第一章的线性代数基础概念"
            },
            {
                "type": "学习建议",
                "content": "多做第二章向量空间的练习题巩固知识点"
            },
            {
                "type": "拓展学习",
                "content": "可以尝试学习线性变换的相关进阶内容"
            }
        ]

        return {
            "success": True,
            "progress": {
                "total_chapters": 4,
                "learned_chapters": 0,
                "progress_percentage": 0
            },
            "recommendations": recommendations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取复习数据失败: {str(e)}")


@app.post("/api/student/check-answer-legacy")
async def check_student_answer(request: CheckAnswerRequest):
    """
    检查学生答案

    使用简单判断方式检查答案的正确性（不依赖MCP和Claude）
    """
    try:
        return await check_student_answer_backend(request)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查答案失败: {str(e)}")


# ==================== 知识路径推荐API接口 ====================

class LearningPathRequest(BaseModel):
    """学习路径推荐请求"""
    chapter_id: str = Field(..., description="当前章节ID")
    student_id: Optional[str] = Field(None, description="学生ID")
    learned_chapters: Optional[List[str]] = Field(default=None, description="已学习的章节列表")


class GetPrerequisitesRequest(BaseModel):
    """获取前置知识请求"""
    chapter_id: str = Field(..., description="章节ID")
    max_depth: int = Field(default=3, description="最大深度")


class GetFollowUpRequest(BaseModel):
    """获取后置知识请求"""
    chapter_id: str = Field(..., description="章节ID")
    max_depth: int = Field(default=3, description="最大深度")


@app.post("/api/student/learning-path")
async def get_learning_path(request: LearningPathRequest):
    """
    获取学习路径推荐

    基于知识图谱和学生已学内容，推荐最佳学习路径
    """
    try:
        # 获取知识图谱数据
        graph_data = await call_mcp_tool("read_graph", {})
        import json
        graph = json.loads(graph_data) if isinstance(graph_data, str) else graph_data

        # 获取当前章节的前置知识
        prerequisites = await call_mcp_tool(
            "get_prerequisites",
            {"node_id": request.chapter_id, "max_depth": 3}
        )
        prerequisites_data = json.loads(prerequisites) if isinstance(prerequisites, str) else prerequisites

        # 获取当前章节的后置知识
        follow_up = await call_mcp_tool(
            "get_follow_up",
            {"node_id": request.chapter_id, "max_depth": 3}
        )
        follow_up_data = json.loads(follow_up) if isinstance(follow_up, str) else follow_up

        # 构建学习路径推荐
        learned = request.learned_chapters or []

        # 分析前置知识
        unlearned_prerequisites = []
        learned_prerequisites = []

        if isinstance(prerequisites_data, list):
            for prereq in prerequisites_data:
                prereq_id = prereq.get("node_id")
                if prereq_id and prereq_id not in learned:
                    unlearned_prerequisites.append({
                        "node_id": prereq_id,
                        "node": prereq.get("node", {}),
                        "depth": prereq.get("depth", 0),
                        "status": "未学习"
                    })
                elif prereq_id:
                    learned_prerequisites.append({
                        "node_id": prereq_id,
                        "node": prereq.get("node", {}),
                        "depth": prereq.get("depth", 0),
                        "status": "已学习"
                    })

        # 分析后置知识（推荐下一步学习）
        recommended_next = []
        if isinstance(follow_up_data, list):
            for follow in follow_up_data:
                node_id = follow.get("node_id")
                if node_id and node_id not in learned:
                    recommended_next.append({
                        "node_id": node_id,
                        "node": follow.get("node", {}),
                        "depth": follow.get("depth", 0),
                        "status": "推荐学习"
                    })

        return {
            "success": True,
            "current_chapter": request.chapter_id,
            "learning_path": {
                "prerequisites": {
                    "learned": learned_prerequisites,
                    "unlearned": unlearned_prerequisites,
                    "status": "ready" if len(unlearned_prerequisites) == 0 else "need_prerequisites"
                },
                "current": {
                    "node_id": request.chapter_id,
                    "status": "learning"
                },
                "follow_up": {
                    "recommended": recommended_next[:5],  # 推荐前5个
                    "total": len(recommended_next)
                }
            },
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取学习路径失败: {str(e)}")


@app.get("/api/student/prerequisites")
async def get_student_prerequisites(chapter_id: str, max_depth: int = 3):
    """
    获取章节的前置知识

    返回学习该章节前需要掌握的知识点
    """
    try:
        prerequisites = await call_mcp_tool(
            "get_prerequisites",
            {"node_id": chapter_id, "max_depth": max_depth}
        )

        import json
        prereq_data = json.loads(prerequisites) if isinstance(prerequisites, str) else prerequisites

        return {
            "success": True,
            "chapter_id": chapter_id,
            "prerequisites": prereq_data,
            "retrieved_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取前置知识失败: {str(e)}")


@app.get("/api/student/follow-up")
async def get_student_follow_up(chapter_id: str, max_depth: int = 3):
    """
    获取章节的后置知识

    返回学习该章节后可以继续学习的内容
    """
    try:
        follow_up = await call_mcp_tool(
            "get_follow_up",
            {"node_id": chapter_id, "max_depth": max_depth}
        )

        import json
        follow_up_data = json.loads(follow_up) if isinstance(follow_up, str) else follow_up

        return {
            "success": True,
            "chapter_id": chapter_id,
            "follow_up": follow_up_data,
            "retrieved_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取后置知识失败: {str(e)}")


# ==================== 生命周期管理 ====================

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    print("教育模式API服务器启动...")
    print("正在初始化MCP客户端...")
    await get_mcp_client()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    print("教育模式API服务器关闭...")
    await close_mcp_client()


# ==================== 主函数 ====================

def run_server(host: str = get_bind_host("EDUCATION_API_BIND_HOST"), port: int = DEFAULT_EDUCATION_API_PORT):
    """
    运行API服务器

    Args:
        host: 监听地址
        port: 监听端口
    """
    print(f"启动教育模式API服务器: http://{host}:{port}")
    print("API文档: http://{}:{}/docs".format(host, port))
    bind_host = host or get_bind_host("EDUCATION_API_BIND_HOST")
    uvicorn.run(app, host=bind_host, port=port)


if __name__ == "__main__":
    run_server(port=get_env_int("EDUCATION_API_PORT", DEFAULT_EDUCATION_API_PORT))
