"""
教育模式API服务器 - 为前端提供HTTP接口
集成MCP客户端和Claude API
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import asyncio
import hashlib
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
    expand_formula_references,
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

class TeacherExerciseFeedbackRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    exercise_id: str = Field(..., description="Exercise ID")
    rating: str = Field(..., description="up, down, or clear")
    question: Optional[str] = Field(None, description="Question text snapshot")
    note: Optional[str] = Field(None, description="Optional teacher note")
    scope: Optional[str] = Field("exercise", description="exercise or option")
    feedback_key: Optional[str] = Field(None, description="Stable exercise feedback key")
    option_key: Optional[str] = Field(None, description="Option letter for option feedback")
    option_text: Optional[str] = Field(None, description="Option text snapshot")
    option_feedback_key: Optional[str] = Field(None, description="Stable option feedback key")
    options: Optional[List[Any]] = Field(None, description="Exercise options snapshot")
    correct_answer: Optional[str] = Field(None, description="Correct answer snapshot")


class TeacherRegenerateExercisesRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    count: int = Field(5, description="Question count")
    force_regenerate: bool = Field(True, description="Force rebuild")


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


def _target_exercise_count(count: int = 5) -> int:
    return max(3, min(max(int(count or 5), 1), 10))


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
        "learningplan",
        "current evidence",
        "graph evidence",
        "knowledge graph constraint",
        "知识图谱约束",
        "图谱证据",
        "当前证据",
        "当前图谱依据不足",
        "当前图谱是否有足够证据",
        "which statement best matches this source passage",
        "which statement is directly stated in the material",
        "which option is correct",
        "what is this",
        "what is the key point about",
        "what does the source say about",
        "directly stated in the material",
        "source passage",
        "formatting detail",
        "random value unrelated",
        "chapter title rather than",
        "see_formula",
        "see_table",
        "[[formula",
        "[[table",
        "[[see_formula",
        "[[see_table",
        "最符合这段材料",
        "最符合当前证据",
        "材料直接表达",
        "下列哪项正确",
        "课堂导入",
        "授课文案",
        "教学目标",
        "启发提问",
        "教学要点",
        "小组讨论",
        "课后思考",
        "只是排版格式",
        "随机数值",
        "章节标题本身",
        "kg_gap",
    ]
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in placeholder_markers):
        return True
    if re.search(r"\bchapter\s+\d+\s*[:：].{0,80}(授课文案|lecture|###)", text, flags=re.I):
        return True
    if re.search(r"第[一二三四五六七八九十\d]+章[:：]", text):
        return True
    if re.search(r"^what\s+is\s+(this|it|that)\??$", question.strip(), flags=re.I):
        return True
    return False


def _strip_reference_markers(value: Any) -> str:
    raw_text = str(value or "")
    raw_text = re.sub(
        r"\b((?:Equation|Eq\.)\s+[0-9]+(?:\.[0-9]+[a-z]?))\s*\(\$[^)]*(?:\)|$)",
        r"\1",
        raw_text,
        flags=re.I,
    )
    text = expand_formula_references(raw_text, display=False, expand_labels=True)
    text = re.sub(r"\[\[(?:SEE_)?TABLE:[^\]]+\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[(?:TABLE|SEE_TABLE)[^\]]*\]\]", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _contains_latex_math(value: Any) -> bool:
    text = str(value or "")
    return bool(
        re.search(
            r"\$\$|\\\[|\\\(|\\begin\{|\\frac|\\sum|\\prod|\\bar|\\overline|\\sigma|\\beta|\\delta|\\Delta|\\left|\\right|\$[^$\n]+\$",
            text,
        )
    )


def _normalize_math_text(value: Any) -> str:
    text = _strip_reference_markers(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[#>*\-\s]+", "", text).strip()
    text = re.sub(r"^\d+[.)銆乚\s+", "", text).strip()
    return text


def _normalize_math_text(value: Any) -> str:
    text = _strip_reference_markers(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[#>*\-\s]+", "", text).strip()
    text = re.sub(r"^\d+[.)\s]+", "", text).strip()
    return text


def _clean_exercise_text(value: Any, limit: int = 180) -> str:
    text = _normalize_math_text(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[#>*\-\s]+", "", text).strip()
    text = re.sub(r"^\d+[.)、]\s+", "", text).strip()
    if _contains_latex_math(text):
        return text
    if len(text) > limit:
        text = text[:limit].rstrip("，。；;,. ") + "..."
    return text


def _clean_exercise_text(value: Any, limit: int = 180) -> str:
    text = _normalize_math_text(value)
    if _contains_latex_math(text):
        return text
    if len(text) > limit:
        text = text[:limit].rstrip("锛屻€傦紱;,. ") + "..."
    return text


def _clean_exercise_text(value: Any, limit: int = 180) -> str:
    text = _normalize_math_text(value)
    if _contains_latex_math(text):
        return text
    if len(text) > limit:
        text = text[:limit].rstrip(" ,.;:") + "..."
    return text


TEACHING_SCAFFOLD_MARKERS = [
    "授课文案",
    "教学目标",
    "课堂导入",
    "核心内容讲解",
    "启发提问",
    "教学要点",
    "课堂互动",
    "小组讨论",
    "引导问题",
    "总结与延伸",
    "核心要点回顾",
    "课后思考",
    "等待学生",
    "引导学生",
    "分钟",
]


GENERIC_FACT_LABELS = {
    "this",
    "that",
    "it",
    "they",
    "these",
    "those",
    "equation",
    "formula",
    "material",
    "the material",
    "source",
    "chapter",
    "定理表述",
    "关键概念",
    "数学形式",
    "教学要点",
    "核心要点",
    "核心要点回顾",
    "本节课",
    "材料",
    "这个",
    "该概念",
}


def _strip_markdown_label(value: Any) -> str:
    text = _strip_reference_markers(value)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text).strip()
    text = re.sub(r"^\*\*([^*：:]{1,32})\*\*\s*[：:]\s*", r"\1：", text)
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"^[-*+]\s+", "", text).strip()
    text = re.sub(r"^[（(].*?学生.*?[）)]$", "", text).strip()
    return text


def _is_teaching_scaffold_text(value: Any) -> bool:
    text = _strip_markdown_label(value)
    compact = re.sub(r"\s+", "", text).lower()
    if not compact:
        return True
    if re.fullmatch(r"(chapter|section)\s*\d+[:：]?.*", text, flags=re.I):
        return True
    if re.fullmatch(r"[一二三四五六七八九十]+[、.．].{0,18}", text):
        return True
    if any(marker.lower() in compact for marker in [item.lower() for item in TEACHING_SCAFFOLD_MARKERS]):
        if not re.search(r"[=><]|：|:|是|等于|需要|用于|控制|定义|means|defined|equals|requires", text, flags=re.I):
            return True
    if re.search(r"\[\[(?:SEE_)?TABLE:", str(value or ""), flags=re.I):
        return True
    return False


def _is_generic_fact_label(value: Any) -> bool:
    text = _clean_exercise_text(_strip_reference_markers(value), limit=80).strip(" ：:，,。.?!？").lower()
    if not text:
        return True
    if text in GENERIC_FACT_LABELS:
        return True
    if text.startswith("equation ") or text.startswith("formula "):
        return True
    if text.startswith("课堂") or text.startswith("教学") or text.startswith("启发"):
        return True
    return False


def _is_mostly_english(value: Any) -> bool:
    text = str(value or "")
    latin = len(re.findall(r"[A-Za-z]", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return latin > max(12, cjk * 2)


def _strip_option_letter(value: Any) -> str:
    return re.sub(r"^[A-D][\s.、)）:：-]+", "", str(value or "").strip(), flags=re.I)


def _compact_learning_text(value: Any, *, char_limit: int = 120, word_limit: int = 24) -> str:
    text = _clean_exercise_text(_strip_option_letter(value), limit=max(char_limit * 2, 120))
    if not text:
        return ""
    if _contains_latex_math(text):
        return text

    if _is_mostly_english(text):
        words = text.split()
        if len(words) > word_limit:
            text = " ".join(words[:word_limit]).rstrip(" ,.;:") + "..."
    elif len(text) > char_limit:
        text = text[:char_limit].rstrip("，。；;,. ") + "..."
    return text


def _compact_question_text(value: Any, *, char_limit: int = 72, word_limit: int = 24) -> str:
    text = _clean_exercise_text(value, limit=max(char_limit * 2, 120))
    if _contains_latex_math(text):
        return text
    if _is_mostly_english(text):
        words = text.split()
        if len(words) > word_limit:
            text = " ".join(words[:word_limit]).rstrip(" ,.;:") + "?"
    elif len(text) > char_limit:
        text = text[:char_limit].rstrip("，。；;,. ") + "？"
    return text


def _exercise_language(*values: Any) -> str:
    joined = " ".join(str(value or "") for value in values)
    return "en" if _is_mostly_english(joined) else "zh"


def _exercise_focus(content: Any, fallback: Any = "") -> str:
    text = _strip_markdown_label(content)
    text = _clean_exercise_text(text, limit=160)
    if _is_mostly_english(text):
        lowered = f" {text.lower()} "
        verb_markers = [
            " is ",
            " are ",
            " means ",
            " refers to ",
            " computes ",
            " updates ",
            " controls ",
            " applies ",
            " uses ",
            " represents ",
            " describes ",
        ]
        cut = None
        for marker in verb_markers:
            position = lowered.find(marker)
            if 0 < position < 80:
                cut = position
                break
        focus = text[:cut].strip() if cut else " ".join(text.split()[:5])
        focus = re.sub(r"\b(then|therefore|thus)$", "", focus, flags=re.I).strip()
        if _is_generic_fact_label(focus):
            focus = str(fallback or "").strip()
        return _compact_learning_text(focus or fallback or "this concept", char_limit=48, word_limit=7)

    focus = re.split(r"[，。；:：]|是|指|可以|用于|由|通过|控制|可能|能够|需要|包含", text, maxsplit=1)[0].strip()
    if _is_generic_fact_label(focus):
        focus = str(fallback or "").strip()
    return _compact_learning_text(focus or fallback or "这个知识点", char_limit=28, word_limit=7)


def _format_options(options: List[str]) -> List[str]:
    letters = ["A", "B", "C", "D"]
    compacted: List[str] = []
    for item in options:
        text = _compact_learning_text(item)
        if not text:
            continue
        compacted.append(_latex_option_text(text))
        if len(compacted) == 4:
            break
    return [f"{letters[index]}. {text}" for index, text in enumerate(compacted)]


def _latex_option_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "$" in text:
        return text
    if _looks_like_formula_text(_strip_option_letter(text)):
        return f"${text}$"
    return text


def _extract_formula_candidates(value: Any) -> List[str]:
    raw_text = str(value or "")
    text = _strip_reference_markers(raw_text)
    patterns = [
        r"\$\$([\s\S]+?)\$\$",
        r"\\\[([\s\S]+?)\\\]",
        r"\\\(([\s\S]+?)\\\)",
        r"\$([^$\n]+?)\$",
        r"([A-Za-zΑ-Ωα-ω][A-Za-z0-9Α-Ωα-ω_{}^\\]*\s*=\s*[^。；;,\n]+)",
    ]
    formulas: List[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            formula = _normalize_math_text(match.group(1))
            formula = re.sub(r"^[Aa]s\s*=\s*", "", formula).strip()
            formula = formula.rstrip("。.;；,， ")
            if formula.endswith("$"):
                formula = formula[:-1].rstrip()
            lhs = formula.split("=", 1)[0].strip().lower() if "=" in formula else ""
            if lhs in {"as", "is", "are", "defined as"}:
                continue
            if "[[" in formula or "]]" in formula:
                continue
            if len(formula) < 3 or formula.lower() in seen:
                continue
            seen.add(formula.lower())
            formulas.append(formula)
            if len(formulas) >= 4:
                return formulas
    return formulas


def _formula_distractors(formula: str) -> List[str]:
    base = str(formula or "").strip()
    variants = []
    fraction = _split_latex_fraction(base)
    if fraction:
        variants.append(
            re.sub(
                r"\\frac\{.+\}\{.+\}",
                lambda _match: f"\\frac{{{fraction[1]}}}{{{fraction[0]}}}",
                base,
                count=1,
            )
        )
    replacements = [
        ("+", "-"),
        ("-", "+"),
        ("\\sum", "\\prod"),
        ("\\prod", "\\sum"),
        ("^2", ""),
        ("_t", "_{t+1}"),
    ]
    for old, new in replacements:
        if old in base:
            variants.append(base.replace(old, new, 1))
    if "/" in base:
        parts = base.split("/", 1)
        variants.append(parts[1] + "/" + parts[0])
    if "=" in base:
        lhs, rhs = base.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()
        variants.append(f"{lhs.strip()} = 1")
        variants.append(f"{lhs.strip()} = {lhs.strip()}")
        if rhs:
            variants.append(f"{lhs} = 0")
            variants.append(f"{lhs} = -({rhs})")
            variants.append(f"{lhs} = {rhs} + 1")
            variants.append(f"{rhs} = {lhs}")
    else:
        variants.append(f"-({base})")
        variants.append(f"{base} + 1")
        variants.append("0")
    result: List[str] = []
    seen: set[str] = {base.lower()}
    for item in variants:
        clean = _compact_learning_text(item, char_limit=120, word_limit=24)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            result.append(clean)
        if len(result) >= 3:
            break
    return result


def _looks_like_formula_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(re.search(r"[=\\^_{}]|\\frac|\\sum|\\prod|\\Delta|\\bar|Cov|E\(|[A-Za-z]\s*[+\-*/]\s*[A-Za-z0-9]", text))


def _looks_like_short_math_part(value: Any) -> bool:
    text = _strip_option_letter(value).strip()
    if not text:
        return False
    if _looks_like_formula_text(text):
        return True
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_{}^\\]*(?:\s*,\s*[A-Za-z][A-Za-z0-9_{}^\\]*){0,3}", text))


def _derive_question_and_answer(
    raw_content: str,
    *,
    chapter_title: str,
    label: str,
    language: str,
    exercise_index: int,
) -> tuple[str, str, List[str]]:
    formulas = _extract_formula_candidates(raw_content)
    focus = _exercise_focus(raw_content, chapter_title or label)
    if formulas:
        formula = formulas[(exercise_index - 1) % len(formulas)]
        if language == "en":
            return f"Which formula is stated for {focus}?", formula, _formula_distractors(formula)
        return f"材料中给出的“{focus}”公式是什么？", formula, _formula_distractors(formula)

    text = _clean_exercise_text(raw_content, limit=260)
    if language == "en":
        computes = re.search(r"^(.{2,80}?)\s+computes\s+(.+?)(?:\s+by\s+(.+?))?(?:\.|$)", text, flags=re.I)
        if computes:
            subject = _compact_learning_text(computes.group(1), char_limit=48, word_limit=8)
            target = _compact_learning_text(computes.group(2), char_limit=120, word_limit=24)
            method = _compact_learning_text(computes.group(3) or "", char_limit=120, word_limit=24)
            if method and exercise_index % 2 == 0:
                return f"How does {subject} compute it?", method, []
            if subject and target:
                return f"What does {subject} compute?", target, []

        updates = re.search(r"^(.{2,80}?)\s+updates\s+(.+?)(?:\s+to\s+(.+?))?(?:\.|$)", text, flags=re.I)
        if updates:
            subject = _compact_learning_text(re.sub(r"\bthen$", "", updates.group(1).strip(), flags=re.I), char_limit=48, word_limit=8)
            target = _compact_learning_text(updates.group(2), char_limit=120, word_limit=24)
            purpose = _compact_learning_text(updates.group(3) or "", char_limit=120, word_limit=24)
            if purpose and exercise_index % 2 == 0:
                return f"Why does {subject} update {target}?", purpose, []
            if subject and target:
                return f"What does {subject} update?", target, []

        patterns = [
            (r"^(.{2,80}?)\s+controls\s+(.+?)(?:\.|$)", "What does {subject} control?"),
            (r"^(.{2,80}?)\s+is\s+(.+?)(?:\.|$)", "What is {subject}?"),
            (r"^(.{2,80}?)\s+means\s+(.+?)(?:\.|$)", "What does {subject} mean?"),
        ]
        for pattern, template in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                subject = _compact_learning_text(match.group(1), char_limit=48, word_limit=8)
                answer = _compact_learning_text(match.group(2), char_limit=120, word_limit=24)
                if subject and answer:
                    return template.format(subject=subject), answer, []
        return f"What is the key point about {focus}?", _compact_learning_text(text, char_limit=120, word_limit=24), []

    through = re.search(r"^(.{1,40}?)通过(.+?)(?:来(.+?))?(?:。|$)", text)
    if through:
        subject = _compact_learning_text(through.group(1), char_limit=32, word_limit=8)
        method = _compact_learning_text(through.group(2), char_limit=120, word_limit=24)
        purpose = _compact_learning_text(through.group(3) or "", char_limit=120, word_limit=24)
        if purpose and exercise_index % 2 == 0:
            return f"材料中“{subject}”这样做的目的是什么？", purpose, []
        if subject and method:
            return f"材料中“{subject}”主要通过什么方式起作用？", method, []

    zh_patterns = [
        (r"^(.{1,40}?)控制(.+?)(?:。|$)", "材料中“{subject}”控制什么？"),
        (r"^(.{1,40}?)用于(.+?)(?:。|$)", "材料中“{subject}”用于什么？"),
        (r"^(.{1,40}?)是(.+?)(?:。|$)", "材料中“{subject}”是什么？"),
    ]
    for pattern, template in zh_patterns:
        match = re.search(pattern, text)
        if match:
            subject = _compact_learning_text(match.group(1), char_limit=32, word_limit=8)
            answer = _compact_learning_text(match.group(2), char_limit=120, word_limit=24)
            if subject and answer:
                return template.format(subject=subject), answer, []
    return f"材料中关于“{focus}”的核心说法是什么？", _compact_learning_text(text, char_limit=120, word_limit=24), []


def _merge_exercise_banks(primary: List[Dict[str, Any]], supplemental: List[Dict[str, Any]], target_count: int) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    seen_option_sets: List[set[str]] = []
    for item in list(primary or []) + list(supplemental or []):
        question = str((item or {}).get("question") or "").strip()
        options = _normalize_exercise_options((item or {}).get("options"))
        key = (question + "\n" + "\n".join(options)).lower()
        option_tokens = _exercise_option_token_set(item)
        if not question or not options or key in seen:
            continue
        if _has_reused_option_set(option_tokens, seen_option_sets):
            continue
        seen.add(key)
        if option_tokens:
            seen_option_sets.append(option_tokens)
        merged.append(item)
        if len(merged) >= target_count:
            break
    return merged


def _exercise_option_token_set(exercise: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for option in _normalize_exercise_options((exercise or {}).get("options"))[:4]:
        token = _compact_learning_text(_strip_option_letter(option), char_limit=130, word_limit=28).lower()
        if token:
            tokens.add(token)
    return tokens


def _has_reused_option_set(option_tokens: set[str], seen_option_sets: List[set[str]]) -> bool:
    if len(option_tokens) < 4:
        return False
    for existing in seen_option_sets:
        if option_tokens == existing:
            return True
        if len(option_tokens & existing) >= 3:
            return True
    return False


def _split_learning_sentences(value: Any) -> List[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_parts = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    sentences: List[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        clean = _strip_markdown_label(part)
        clean = _clean_exercise_text(clean, limit=320)
        if len(clean) < 6:
            continue
        if _is_teaching_scaffold_text(clean):
            continue
        if clean.lower() in seen:
            continue
        seen.add(clean.lower())
        sentences.append(clean)
    return sentences


def _add_exercise_fact(
    facts: List[Dict[str, Any]],
    *,
    question: str,
    answer: str,
    source: Dict[str, Any],
    evidence_text: str,
    language: str,
    kind: str = "concept",
) -> None:
    clean_question = _compact_question_text(question, char_limit=90, word_limit=32)
    clean_answer = _compact_learning_text(answer, char_limit=130, word_limit=28)
    if not clean_question or not clean_answer:
        return
    combined = f"{clean_question} {clean_answer}"
    if _is_teaching_scaffold_text(clean_question) or _is_teaching_scaffold_text(clean_answer):
        return
    if re.search(r"\[\[|see_formula|see_table", combined, flags=re.I):
        return
    if re.search(r"directly stated in the material|which statement|what is this|what is the key point", clean_question, flags=re.I):
        return
    if clean_answer.lower() in {"it", "this", "that", "the concept", "这个概念", "该概念"}:
        return
    if _is_generic_fact_label(clean_answer):
        return
    key = f"{clean_question}\n{clean_answer}".lower()
    if any(item.get("_key") == key for item in facts):
        return
    facts.append(
        {
            "_key": key,
            "question": clean_question,
            "answer": clean_answer,
            "source": source,
            "evidence_text": _compact_learning_text(evidence_text, char_limit=150, word_limit=32),
            "language": language,
            "kind": kind,
        }
    )


def _split_latex_fraction(formula: str) -> tuple[str, str] | None:
    match = re.search(r"\\frac\{(.+)\}\{(.+)\}", str(formula or ""))
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _extract_english_facts(sentence: str, source: Dict[str, Any], facts: List[Dict[str, Any]], fallback_subject: str = "") -> None:
    if _is_teaching_scaffold_text(sentence):
        return
    formulas = _extract_formula_candidates(sentence)
    label = _compact_learning_text(source.get("label"), char_limit=54, word_limit=8)

    defined = re.search(r"^(.{2,80}?)\s+(?:is\s+defined\s+as|is)\s+(.+?)(?:\.|$)", sentence, flags=re.I)
    if formulas:
        subject = _exercise_focus(sentence, fallback_subject or label or "the concept")
        if _is_generic_fact_label(subject):
            return
        _add_exercise_fact(
            facts,
            question=f"Which formula defines {subject}?",
            answer=formulas[0],
            source=source,
            evidence_text=sentence,
            language="en",
            kind="formula",
        )
        fraction = _split_latex_fraction(formulas[0])
        if fraction:
            _add_exercise_fact(
                facts,
                question=f"What is the numerator in the {subject} formula?",
                answer=fraction[0],
                source=source,
                evidence_text=sentence,
                language="en",
                kind="formula_part",
            )
            _add_exercise_fact(
                facts,
                question=f"What is the denominator in the {subject} formula?",
                answer=fraction[1],
                source=source,
                evidence_text=sentence,
                language="en",
                kind="formula_part",
            )
    elif defined:
        subject = _compact_learning_text(defined.group(1), char_limit=54, word_limit=8)
        answer = _compact_learning_text(defined.group(2), char_limit=130, word_limit=28)
        if _is_generic_fact_label(subject):
            return
        _add_exercise_fact(
            facts,
            question=f"What is {subject}?",
            answer=answer,
            source=source,
            evidence_text=sentence,
            language="en",
            kind="definition",
        )

    patterns = [
        (r"^(.{2,80}?)\s+computes\s+(.+?)(?:\s+by\s+(.+?))?(?:\.|$)", "What does {subject} compute?", "How does {subject} compute it?"),
        (r"^(.{2,80}?)\s+updates\s+(.+?)(?:\s+to\s+(.+?))?(?:\.|$)", "What does {subject} update?", "Why does {subject} update {object}?"),
        (r"^(.{2,80}?)\s+controls\s+(.+?)(?:\.|$)", "What does {subject} control?", ""),
        (r"^(.{2,80}?)\s+converts\s+(.+?)\s+into\s+(.+?)(?:\.|$)", "What does {subject} convert {object} into?", ""),
        (r"^(.{2,80}?)\s+relates\s+(.+?)\s+to\s+(.+?)(?:\.|$)", "What does {subject} relate?", ""),
        (r"^(.{2,80}?)\s+sums?\s+to\s+(.+?)(?:\.|$)", "What do {subject} sum to?", ""),
    ]
    for pattern, direct_template, extra_template in patterns:
        match = re.search(pattern, sentence, flags=re.I)
        if not match:
            continue
        subject = _compact_learning_text(re.sub(r"\bthen$", "", match.group(1).strip(), flags=re.I), char_limit=54, word_limit=8)
        if subject.lower() in {"it", "this", "that", "they", "these", "those"}:
            subject = _compact_learning_text(fallback_subject, char_limit=54, word_limit=8) or _exercise_focus(sentence, "the concept")
        if _is_generic_fact_label(subject):
            continue
        obj = _compact_learning_text(match.group(2), char_limit=80, word_limit=16)
        extra = _compact_learning_text(match.group(3) if match.lastindex and match.lastindex >= 3 else "", char_limit=120, word_limit=24)
        if "relates" in pattern and extra:
            answer = f"{obj} to {extra}"
        else:
            answer = extra if "converts" in pattern else obj
        subject_for_question = re.sub(
            r"^(The|A|An)\b",
            lambda item: item.group(1).lower(),
            subject,
        )
        question = direct_template.format(subject=subject_for_question, object=obj)
        _add_exercise_fact(
            facts,
            question=question,
            answer=answer,
            source=source,
            evidence_text=sentence,
            language="en",
            kind="relation",
        )
        if extra and extra_template:
            extra_question = extra_template.format(subject=subject, object=obj)
            _add_exercise_fact(
                facts,
                question=extra_question,
                answer=extra,
                source=source,
                evidence_text=sentence,
                language="en",
                kind="relation",
            )


def _extract_chinese_facts(sentence: str, source: Dict[str, Any], facts: List[Dict[str, Any]]) -> None:
    if _is_teaching_scaffold_text(sentence):
        return
    formulas = _extract_formula_candidates(sentence)
    if formulas:
        subject = _exercise_focus(sentence, source.get("label") or "该概念")
        if _is_generic_fact_label(subject):
            return
        _add_exercise_fact(
            facts,
            question=f"材料中“{subject}”的公式是什么？",
            answer=formulas[0],
            source=source,
            evidence_text=sentence,
            language="zh",
            kind="formula",
        )

    colon = re.search(r"^([^：:]{2,40})[：:]\s*(.+)$", sentence)
    if colon:
        subject = _compact_learning_text(colon.group(1), char_limit=36, word_limit=8)
        answer = _compact_learning_text(colon.group(2), char_limit=130, word_limit=28)
        source_label = _compact_learning_text(source.get("label") or "", char_limit=36, word_limit=8)
        if _is_generic_fact_label(subject) and source_label and not _is_generic_fact_label(source_label):
            subject = source_label
        if not _is_generic_fact_label(subject):
            question = f"材料中“{subject}”的表述是什么？"
            if _extract_formula_candidates(answer) or re.search(r"[=><]|Δ|Cov|E\(", answer):
                question = f"材料中“{subject}”的公式是什么？"
            _add_exercise_fact(
                facts,
                question=question,
                answer=answer,
                source=source,
                evidence_text=sentence,
                language="zh",
                kind="definition",
            )
            return

    through = re.search(r"^(.{1,42}?)通过(.+?)(?:来(.+?))?(?:。|$)", sentence)
    if through:
        subject = _compact_learning_text(through.group(1), char_limit=36, word_limit=8)
        method = _compact_learning_text(through.group(2), char_limit=120, word_limit=24)
        purpose = _compact_learning_text(through.group(3) or "", char_limit=120, word_limit=24)
        _add_exercise_fact(
            facts,
            question=f"材料中“{subject}”主要通过什么方式起作用？",
            answer=method,
            source=source,
            evidence_text=sentence,
            language="zh",
            kind="relation",
        )
        if purpose:
            _add_exercise_fact(
                facts,
                question=f"材料中“{subject}”这样做的目的是什么？",
                answer=purpose,
                source=source,
                evidence_text=sentence,
                language="zh",
                kind="relation",
            )

    patterns = [
        (r"^(.{1,42}?)控制(.+?)(?:。|$)", "材料中“{subject}”控制什么？"),
        (r"^(.{1,42}?)用于(.+?)(?:。|$)", "材料中“{subject}”用于什么？"),
        (r"^(.{1,42}?)是(.+?)(?:。|$)", "材料中“{subject}”是什么？"),
        (r"^(.{1,42}?)等于(.+?)(?:。|$)", "材料中“{subject}”等于什么？"),
        (r"^(.{1,42}?)需要(.+?)(?:。|$)", "材料中“{subject}”需要什么？"),
        (r"^(.{1,42}?)解释了(.+?)(?:。|$)", "材料中“{subject}”解释了什么？"),
        (r"^(.{1,42}?)可能导致(.+?)(?:。|$)", "材料中“{subject}”可能导致什么？"),
    ]
    for pattern, template in patterns:
        match = re.search(pattern, sentence)
        if not match:
            continue
        subject = _compact_learning_text(match.group(1), char_limit=36, word_limit=8)
        answer = _compact_learning_text(match.group(2), char_limit=120, word_limit=24)
        if _is_generic_fact_label(subject):
            continue
        _add_exercise_fact(
            facts,
            question=template.format(subject=subject),
            answer=answer,
            source=source,
            evidence_text=sentence,
            language="zh",
            kind="relation",
        )


def _extract_exercise_facts(source_evidence: List[Dict[str, Any]], target_count: int, chapter_title: str = "") -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    for source in source_evidence:
        if not isinstance(source, dict):
            continue
        content = source.get("content") or source.get("label") or ""
        language = _exercise_language(source.get("label"), content)
        for sentence in _split_learning_sentences(content):
            if language == "en":
                _extract_english_facts(sentence, source, facts, chapter_title)
            else:
                _extract_chinese_facts(sentence, source, facts)
            if len(facts) >= max(target_count, 6):
                break
        if len(facts) >= max(target_count, 6):
            break

    return facts[:target_count]


def _generic_wrong_options(language: str, kind: str) -> List[str]:
    if kind == "formula":
        return ["\\Delta z = 0", "\\bar{w} = 1", "Cov(w,z) = 0", "E(z) = 0"]
    if kind == "formula_part":
        return ["\\bar{w}", "\\Delta z", "Cov(w,z)", "E(z)", "p_i"]
    if language == "en":
        if kind == "formula":
            return ["p_i = 1", "p_i = z_i", "p_i = e^{z_i}"]
        return [
            "equal outcomes for every individual",
            "a notation change with no biological effect",
            "selection without inherited variation",
            "a fixed trait that cannot change across generations",
            "random drift with no relation to fitness",
        ]
    if kind == "formula":
        return ["p_i = 1", "x = x", "结果恒为 0", "Δz = 0"]
    return [
        "表示所有个体适应性完全相同",
        "只是符号变化而没有生物学含义",
        "说明选择不需要遗传变异",
        "表示性状在代际间不会改变",
        "仅由随机漂变决定且与适应性无关",
    ]


def _build_fact_options(fact: Dict[str, Any], facts: List[Dict[str, Any]], exercise_index: int) -> tuple[List[str], str]:
    answer = _compact_learning_text(fact.get("answer"), char_limit=130, word_limit=28)
    language = fact.get("language") or "zh"
    kind = fact.get("kind") or "concept"
    candidates: List[str] = [answer]

    if kind == "formula":
        candidates.extend(_formula_distractors(answer))

    for other in facts:
        other_kind = str(other.get("kind") or "concept")
        other_answer = _compact_learning_text(other.get("answer"), char_limit=130, word_limit=28)
        if not other_answer or other_answer.lower() == answer.lower():
            continue
        if kind == "formula" and not _looks_like_formula_text(other_answer):
            continue
        if kind == "formula_part" and not _looks_like_short_math_part(other_answer):
            continue
        if kind not in {"formula", "formula_part"} and other_kind in {"formula", "formula_part"}:
            continue
        candidates.append(other_answer)

    candidates.extend(_generic_wrong_options(language, kind))

    unique: List[str] = []
    seen: set[str] = set()
    for item in candidates:
        clean = _compact_learning_text(item, char_limit=130, word_limit=28)
        if not clean or clean.lower() in seen:
            continue
        if kind == "formula" and not _looks_like_formula_text(clean):
            continue
        if kind == "formula_part" and not _looks_like_short_math_part(clean):
            continue
        seen.add(clean.lower())
        unique.append(clean)
        if len(unique) >= 4:
            break

    if len(unique) < 4:
        raise ValueError("题库生成失败：没有足够的有效选项")

    correct_slot = (exercise_index - 1) % 4
    correct_text = unique.pop(0)
    unique.insert(correct_slot, correct_text)
    letters = ["A", "B", "C", "D"]
    return [f"{letters[index]}. {_latex_option_text(text)}" for index, text in enumerate(unique)], letters[correct_slot]


def _build_fact_choice_exercise(
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_content: str,
    fact: Dict[str, Any],
    facts: List[Dict[str, Any]],
    exercise_index: int,
) -> Dict[str, Any]:
    options, correct_answer = _build_fact_options(fact, facts, exercise_index)
    source = fact.get("source") if isinstance(fact.get("source"), dict) else {}
    evidence = [source] if source else []
    plan = build_learning_plan(
        query=chapter_title or fact.get("question") or chapter_id,
        evidence=evidence,
        learner_intent="practice",
        task="practice",
        chapter_data={"id": chapter_id, "title": chapter_title, "content": chapter_content},
    )
    language = fact.get("language") or "zh"
    evidence_text = fact.get("evidence_text") or fact.get("answer") or ""
    explanation = (
        f'The answer is supported by: "{evidence_text}"'
        if language == "en"
        else f"答案依据材料：“{evidence_text}”。"
    )
    return {
        "id": f"ex_{re.sub(r'[^a-zA-Z0-9_-]+', '_', chapter_id or 'chapter')}_{exercise_index}",
        "question": fact.get("question") or ("Which option is correct?" if language == "en" else "下列哪项正确？"),
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "source_evidence": evidence,
        "learning_plan": plan,
    }


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

    candidates: List[str] = []
    seen: set[str] = set()
    current_topic = ""

    def add_candidate(value: Any) -> None:
        clean = _clean_exercise_text(_strip_markdown_label(value), limit=190)
        if len(clean) < 8 or clean in seen:
            return
        if _is_teaching_scaffold_text(clean):
            return
        if re.search(r"同学们|等待学生|引导学生|想象|假设|为什么|请用|如果|会怎么|怎么说|思考片刻|今天我们要学习|达尔文说", clean):
            return
        if "？" in clean or "?" in clean:
            return
        if clean.startswith("“") or clean.startswith('"'):
            return
        if re.match(r"^(理解|掌握|能够|能夠|了解|熟悉|学会|学习).{4,80}$", clean):
            return
        if re.search(r"\[\[|see_formula|see_table", clean, flags=re.I):
            return
        knowledge_cue = re.search(
            r"[:：=<>Δ]|是|等于|需要|用于|控制|可以|进化|选择|方差|适应性|协方差|遗传|收益|成本|defined|means|equals|requires|controls|relates|fitness|variance|selection|evolution",
            clean,
            flags=re.I,
        )
        if not knowledge_cue:
            return
        seen.add(clean)
        candidates.append(clean)

    for raw_line in content.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        heading_match = re.match(r"^\s{0,3}#{1,6}\s*(.+)$", raw_line)
        if heading_match:
            heading = _clean_exercise_text(heading_match.group(1), limit=80)
            heading = re.sub(r"^\d+[.)、]\s*", "", heading).strip()
            heading = re.sub(r"[（(]\d+\s*分钟[）)]", "", heading).strip()
            if heading and not _is_teaching_scaffold_text(heading):
                current_topic = heading
            continue

        line = _strip_markdown_label(raw_line)
        if not line or _is_teaching_scaffold_text(line):
            continue
        colon_match = re.match(r"^([^：:]{1,24})[：:]\s*(.+)$", line)
        if colon_match:
            label = _compact_learning_text(colon_match.group(1), char_limit=24, word_limit=6)
            value = colon_match.group(2).strip()
            if _is_generic_fact_label(label) and current_topic:
                prefix = f"{current_topic}数学形式" if "数学" in label else current_topic
                line = f"{prefix}：{value}"
        add_candidate(line)

        for part in re.split(r"(?<=[。！？.!?])\s+|[；;]", line):
            part = part.strip()
            if part and part != line:
                add_candidate(part)
        if len(candidates) >= limit:
            break

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
    language = _exercise_language(chapter_title, " ".join(str(item.get("content") or "") for item in sources[:3]))
    for index, item in enumerate(sources):
        if index == current_index:
            continue
        raw = _clean_exercise_text(item.get("content") or item.get("label"), limit=240)
        _, answer, _ = _derive_question_and_answer(
            raw,
            chapter_title=chapter_title,
            label=str(item.get("label") or ""),
            language=language,
            exercise_index=index + 1,
        )
        content = _compact_learning_text(answer or raw, char_limit=112, word_limit=22)
        if content:
            pool.append(content)

    if language == "en":
        pool.extend(
            [
                "equal outcomes for every individual",
                "selection without inherited variation",
                "a fixed trait that cannot change across generations",
            ]
        )
    else:
        pool.extend(
            [
                "表示所有个体适应性完全相同。",
                "说明选择不需要遗传变异。",
                "表示性状在代际间不会改变。",
            ]
        )

    result: List[str] = []
    seen: set[str] = set()
    for item in pool:
        clean = _compact_learning_text(item, char_limit=112, word_limit=22)
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
    label = _compact_learning_text(source.get("label") or chapter_title or f"知识点 {exercise_index}", char_limit=48, word_limit=8)
    raw_content = _clean_exercise_text(source.get("content") or label, limit=280)
    content = _compact_learning_text(raw_content, char_limit=120, word_limit=24)
    if not raw_content or not content:
        raise ValueError("题库生成失败：章节内容和图谱证据为空，无法生成可靠练习题")

    language = _exercise_language(chapter_title, label, raw_content)
    question, correct_text, specific_distractors = _derive_question_and_answer(
        raw_content,
        chapter_title=chapter_title,
        label=label,
        language=language,
        exercise_index=exercise_index,
    )
    distractors = _exercise_distractor_pool(all_sources, source_index, chapter_title)
    options = [correct_text or content]
    is_formula_question = _looks_like_formula_text(options[0]) and re.search(r"formula|公式", question, flags=re.I)
    option_seen = {_compact_learning_text(options[0]).lower()}
    extra_kind = "formula" if is_formula_question else "concept"
    for distractor in specific_distractors + distractors + _generic_wrong_options(language, extra_kind):
        compact = _compact_learning_text(distractor)
        if compact and compact.lower() not in option_seen:
            if is_formula_question and not _looks_like_formula_text(compact):
                continue
            if not is_formula_question and _looks_like_formula_text(compact):
                continue
            option_seen.add(compact.lower())
            options.append(compact)
        if len(options) == 4:
            break
    while len(options) < 4:
        if is_formula_question:
            fillers = _generic_wrong_options(language, "formula")
        elif language == "en":
            fillers = [
                "equal outcomes for every individual",
                "selection without inherited variation",
                "a fixed trait that cannot change across generations",
            ]
        else:
            fillers = [
                "表示所有个体适应性完全相同。",
                "说明选择不需要遗传变异。",
                "表示性状在代际间不会改变。",
            ]
        filler = fillers[(len(options) - 1) % len(fillers)]
        if filler.lower() not in option_seen:
            option_seen.add(filler.lower())
            options.append(filler)
        else:
            options.append(f"{filler} ({len(options) + 1})")

    options = options[:4]
    correct_slot = (exercise_index - 1) % len(options)
    if correct_slot:
        correct_option = options.pop(0)
        options.insert(correct_slot, correct_option)

    letters = ["A", "B", "C", "D"]
    formatted_options = _format_options(options)
    correct_answer = letters[correct_slot]
    if len(formatted_options) < 4:
        raise ValueError("题库生成失败：没有足够的有效选项")
    evidence = [source]
    plan = build_learning_plan(
        query=chapter_title or label,
        evidence=evidence,
        learner_intent="practice",
        task="practice",
        chapter_data={"id": chapter_id, "title": chapter_title, "content": chapter_content},
    )
    if language == "en":
        explanation = f'The correct choice is supported by the source wording: "{content}"'
    else:
        explanation = f"正确选项对应原文要点：“{content}”。"
    return {
        "id": f"ex_{re.sub(r'[^a-zA-Z0-9_-]+', '_', chapter_id or 'chapter')}_{exercise_index}",
        "question": _compact_question_text(question),
        "options": formatted_options,
        "correct_answer": correct_answer,
        "explanation": explanation,
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
    seen_option_sets: List[set[str]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        question = _compact_question_text(item.get("question") or item.get("stem") or item.get("prompt") or item.get("title") or "")
        raw_options = _normalize_exercise_options(item.get("options") or item.get("choices") or item.get("answers"))
        options = _format_options(raw_options)
        if not question or not options:
            continue
        if len(options) != 4:
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
        option_tokens = _exercise_option_token_set(exercise)
        if _has_reused_option_set(option_tokens, seen_option_sets):
            continue
        if option_tokens:
            seen_option_sets.append(option_tokens)
        bank.append(exercise)
    return bank


def _exercise_signature(exercise: Dict[str, Any]) -> str:
    question = _compact_question_text(str((exercise or {}).get("question") or ""))
    options = _format_options(
        _normalize_exercise_options(
            (exercise or {}).get("options")
            or (exercise or {}).get("choices")
            or (exercise or {}).get("answers")
        )
    )
    answer = _normalize_correct_answer(
        (exercise or {}).get("correct_answer")
        or (exercise or {}).get("answer")
        or (exercise or {}).get("correct")
        or (exercise or {}).get("correct_option")
    )
    payload = "\n".join([question.lower(), answer.lower(), *[str(option).lower() for option in options]])
    return "sig_" + hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _exercise_feedback_map(chapter: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    feedback = (chapter or {}).get("exercise_feedback")
    if not isinstance(feedback, dict):
        return {}
    return {
        str(key): value
        for key, value in feedback.items()
        if isinstance(value, dict)
    }


def _exercise_feedback_for_item(
    exercise: Dict[str, Any],
    feedback: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    signature = _exercise_signature(exercise)
    exercise_id = str((exercise or {}).get("id") or "")
    return feedback.get(signature) or (feedback.get(exercise_id) if exercise_id else None)


def _exercise_option_feedback_key(exercise: Dict[str, Any], option: Any, index: int) -> str:
    parent_key = _exercise_signature(exercise)
    option_key = chr(65 + index)
    option_text = _compact_learning_text(_strip_option_letter(option), char_limit=160, word_limit=36)
    digest = hashlib.sha1(option_text.lower().encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{parent_key}::option::{option_key}::{digest}"


def _exercise_option_feedback_for_item(
    exercise: Dict[str, Any],
    option: Any,
    index: int,
    feedback: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    key = _exercise_option_feedback_key(exercise, option, index)
    if key in feedback:
        return feedback[key]
    parent_key = _exercise_signature(exercise)
    option_key = chr(65 + index)
    option_text = _compact_learning_text(_strip_option_letter(option), char_limit=160, word_limit=36)
    for record in feedback.values():
        if not isinstance(record, dict) or str(record.get("scope") or "").lower() != "option":
            continue
        if str(record.get("parent_feedback_key") or "") != parent_key:
            continue
        if str(record.get("option_key") or "").upper() == option_key:
            return record
        if option_text and _compact_learning_text(record.get("option_text"), char_limit=160, word_limit=36).lower() == option_text.lower():
            return record
    return None


def _attach_exercise_feedback(
    exercises: List[Dict[str, Any]],
    feedback: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for exercise in exercises:
        item = dict(exercise)
        signature = _exercise_signature(item)
        item["feedback_key"] = signature
        record = _exercise_feedback_for_item(item, feedback)
        if record:
            item["teacher_rating"] = str(record.get("rating") or "").lower()
            item["teacher_feedback"] = record
        else:
            item["teacher_rating"] = ""
        option_feedback: Dict[str, Dict[str, Any]] = {}
        options = _normalize_exercise_options(item.get("options"))
        for index, option in enumerate(options[:4]):
            option_key = chr(65 + index)
            option_record = _exercise_option_feedback_for_item(item, option, index, feedback)
            option_feedback[option_key] = {
                "feedback_key": _exercise_option_feedback_key(item, option, index),
                "rating": str((option_record or {}).get("rating") or "").lower(),
                "option_text": _strip_option_letter(option),
            }
            if option_record:
                option_feedback[option_key]["teacher_feedback"] = option_record
        item["option_feedback"] = option_feedback
        annotated.append(item)
    return annotated


def _filter_downvoted_exercises(
    exercises: List[Dict[str, Any]],
    feedback: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for exercise in exercises:
        record = _exercise_feedback_for_item(exercise, feedback)
        if str((record or {}).get("rating") or "").lower() == "down":
            continue
        filtered.append(exercise)
    return filtered


def _same_exercise_target(
    item: Dict[str, Any],
    target: Dict[str, Any],
    feedback_key: str = "",
) -> bool:
    if not isinstance(item, dict):
        return False
    item_keys = {
        str(item.get("approval_key") or ""),
        str(item.get("feedback_key") or ""),
        str(item.get("id") or ""),
        _exercise_signature(item),
    }
    target_keys = {
        str(target.get("approval_key") or ""),
        str(target.get("feedback_key") or ""),
        str(target.get("id") or ""),
        _exercise_signature(target),
        str(feedback_key or ""),
    }
    if any(key and key in target_keys for key in item_keys):
        return True
    item_question = _compact_question_text(item.get("question") or "")
    target_question = _compact_question_text(target.get("question") or "")
    return bool(item_question and target_question and item_question == target_question)


def _remove_exercise_from_bank(
    exercises: List[Dict[str, Any]],
    target: Dict[str, Any],
    feedback_key: str = "",
) -> List[Dict[str, Any]]:
    return [
        item for item in exercises
        if isinstance(item, dict) and not _same_exercise_target(item, target, feedback_key)
    ]


def _merge_all_exercise_banks(*banks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = sum(len(bank or []) for bank in banks)
    merged: List[Dict[str, Any]] = []
    for bank in banks:
        merged = _merge_exercise_banks(merged, bank or [], max(total, len(merged), 1))
    return merged


def _exercise_feedback_summary(feedback: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    exercise_up = 0
    exercise_down = 0
    option_up = 0
    option_down = 0
    for record in feedback.values():
        rating = str(record.get("rating") or "").lower()
        scope = str(record.get("scope") or "exercise").lower()
        if rating == "up":
            if scope == "option":
                option_up += 1
            else:
                exercise_up += 1
        elif rating == "down":
            if scope == "option":
                option_down += 1
            else:
                exercise_down += 1
    return {
        "up": exercise_up,
        "down": exercise_down,
        "exercise_up": exercise_up,
        "exercise_down": exercise_down,
        "option_up": option_up,
        "option_down": option_down,
    }


def _build_exercise_feedback_guidance(feedback: Dict[str, Dict[str, Any]]) -> str:
    good_questions: List[str] = []
    bad_questions: List[str] = []
    good_options: List[str] = []
    bad_options: List[str] = []
    for record in feedback.values():
        if not isinstance(record, dict):
            continue
        rating = str(record.get("rating") or "").lower()
        scope = str(record.get("scope") or "exercise").lower()
        if rating not in {"up", "down"}:
            continue
        if scope == "option":
            text = _compact_learning_text(record.get("option_text"), char_limit=120, word_limit=24)
            if not text:
                continue
            (good_options if rating == "up" else bad_options).append(text)
        else:
            text = _compact_question_text(record.get("question"), char_limit=90, word_limit=28)
            if not text:
                continue
            (good_questions if rating == "up" else bad_questions).append(text)

    lines: List[str] = []
    if good_questions:
        lines.append("教师点赞的题型方向：" + "；".join(good_questions[:4]))
    if bad_questions:
        lines.append("教师点踩的题型必须避免：" + "；".join(bad_questions[:4]))
    if good_options:
        lines.append("教师点赞的选项特征：短、明确、直接考察知识；示例：" + "；".join(good_options[:4]))
    if bad_options:
        lines.append("教师点踩的选项必须避免：过长、像原文整段、教学脚手架或无关干扰；示例：" + "；".join(bad_options[:4]))
    return "\n".join(lines)


def _find_exercise_for_feedback(
    bank: List[Dict[str, Any]],
    exercise_id: str,
    question: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    target_id = str(exercise_id or "")
    target_question = _compact_question_text(question or "")
    for exercise in bank:
        if str(exercise.get("id") or "") == target_id:
            return exercise
        if _exercise_signature(exercise) == target_id:
            return exercise
    if target_question:
        for exercise in bank:
            if _compact_question_text(str(exercise.get("question") or "")) == target_question:
                return exercise
        return {"id": target_id, "question": target_question, "options": [], "correct_answer": ""}
    return None


def _build_local_exercise_response(
    request: GenerateExercisesRequest,
    *,
    graph_data: Optional[Dict[str, Any]] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    chapter_content = expand_formula_references(request.chapter_content)
    chapter_payload = {
        "id": request.chapter_id,
        "title": request.chapter_title,
        "content": chapter_content,
    }
    if isinstance(graph_data, dict):
        chapter_payload["graph_data"] = graph_data

    evidence = _get_exercise_evidence(request.chapter_id, chapter_payload)
    exercise_bank = _build_local_exercise_bank(
        chapter_id=request.chapter_id,
        chapter_title=request.chapter_title,
        chapter_content=chapter_content,
        evidence=evidence,
        count=request.count,
    )
    existing_chapter = chapter_store.get_chapter(request.chapter_id)
    feedback = _exercise_feedback_map(existing_chapter)
    approved_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank((existing_chapter or {}).get("approved_exercise_bank")),
        feedback,
    )
    pinned_bank = [
        item
        for item in _normalize_exercise_bank((existing_chapter or {}).get("exercise_bank") or (existing_chapter or {}).get("exercises"))
        if str((_exercise_feedback_for_item(item, feedback) or {}).get("rating") or "").lower() == "up"
    ]
    if approved_bank:
        pinned_bank = _merge_exercise_banks(approved_bank, pinned_bank, _target_exercise_count(request.count))
    exercise_bank = _filter_downvoted_exercises(exercise_bank, feedback)
    if pinned_bank:
        exercise_bank = _merge_exercise_banks(pinned_bank, exercise_bank, _target_exercise_count(request.count))
    target_count = _target_exercise_count(request.count)
    if not exercise_bank:
        raise ValueError("No exercises remain after teacher feedback filtering")
    if len(exercise_bank) < target_count:
        warning = (warning + " " if warning else "") + f"Only {len(exercise_bank)} / {target_count} usable exercises remain after teacher feedback filtering."
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
        "approved_exercise_bank": approved_bank,
        "chapter": saved_chapter,
        "learning_plan": learning_plan,
        "consistency_report": _safe_consistency_report(str(exercise_bank), learning_plan, task="practice"),
        "feedback_summary": _exercise_feedback_summary(feedback),
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
    chapter_content = expand_formula_references(chapter_content)
    target_count = _target_exercise_count(count)
    content_evidence = _chapter_content_evidence(
        chapter_id=chapter_id,
        chapter_title=chapter_title,
        chapter_content=chapter_content,
        limit=max(target_count * 4, 12),
    )
    source_evidence = content_evidence + (evidence or [])
    if not source_evidence:
        raise ValueError("题库生成失败：章节内容和图谱证据为空，无法生成可靠练习题")

    normalized_sources = []
    for index, item in enumerate(source_evidence, start=1):
        if not isinstance(item, dict):
            continue
        content = _compact_learning_text(item.get("content") or item.get("label"), char_limit=120, word_limit=24)
        if not content:
            continue
        if _is_teaching_scaffold_text(content) or re.search(r"\[\[|see_formula|see_table", content, flags=re.I):
            continue
        normalized = dict(item)
        normalized["index"] = normalized.get("index") or index
        normalized["label"] = _compact_learning_text(normalized.get("label") or chapter_title or f"知识点 {index}", char_limit=48, word_limit=8)
        normalized["content"] = content
        normalized.setdefault("source", "graph")
        normalized_sources.append(normalized)

    if not normalized_sources:
        raise ValueError("题库生成失败：没有可用于组题的有效知识点")

    facts = _extract_exercise_facts(normalized_sources, max(target_count * 2, 8), chapter_title)
    bank: List[Dict[str, Any]] = []
    if facts:
        seen_option_sets: List[set[str]] = []
        for index, fact in enumerate(facts, start=1):
            exercise = _build_fact_choice_exercise(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                fact=fact,
                facts=facts,
                exercise_index=index,
            )
            option_tokens = _exercise_option_token_set(exercise)
            if not _is_placeholder_exercise(exercise, exercise.get("question") or "", exercise.get("options") or []) and not _has_reused_option_set(option_tokens, seen_option_sets):
                bank.append(exercise)
                if option_tokens:
                    seen_option_sets.append(option_tokens)
            if len(bank) >= target_count:
                break
        if len(bank) >= target_count:
            return bank

    seen_option_sets = [_exercise_option_token_set(item) for item in bank]
    source_count = len(normalized_sources)
    attempts = 0
    while len(bank) < target_count and attempts < max(target_count * 4, source_count * 2):
        item = normalized_sources[attempts % source_count]
        exercise = _build_local_choice_exercise(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            chapter_content=chapter_content,
            source=item,
            all_sources=normalized_sources,
            source_index=attempts % source_count,
            exercise_index=attempts + 1,
        )
        option_tokens = _exercise_option_token_set(exercise)
        if not _has_reused_option_set(option_tokens, seen_option_sets):
            bank.append(exercise)
            if option_tokens:
                seen_option_sets.append(option_tokens)
        attempts += 1
    if len(bank) < target_count:
        for index in range(len(bank) + 1, target_count + 1):
            item = normalized_sources[(index - 1) % source_count]
            bank.append(
                _build_local_choice_exercise(
                    chapter_id=chapter_id,
                    chapter_title=chapter_title,
                    chapter_content=chapter_content,
                    source=item,
                    all_sources=normalized_sources,
                    source_index=(index - 1) % source_count,
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
        chapter_content = expand_formula_references(request.chapter_content)
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
            "content": chapter_content,
        }
        learning_plan = _build_plan_from_graph(
            query=request.chapter_title,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            task="lecture",
            chapter_data=chapter_data,
        )
        if not learning_plan.get("evidence"):
            rag = build_rag_context(f"{request.chapter_title}\n{chapter_content[:800]}", limit=6)
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
        approved_bank = _normalize_exercise_bank(chapter.get("approved_exercise_bank"))
        chapter = dict(chapter)
        chapter["exercise_bank"] = cleaned_bank
        chapter["approved_exercise_bank"] = approved_bank
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
        target_count = _target_exercise_count(request.count)
        chapter_content = expand_formula_references(request.chapter_content)
        cached_chapter = chapter_store.get_chapter(request.chapter_id)
        feedback = _exercise_feedback_map(cached_chapter)
        approved_bank = _filter_downvoted_exercises(
            _normalize_exercise_bank((cached_chapter or {}).get("approved_exercise_bank")),
            feedback,
        )
        if approved_bank and len(approved_bank) >= target_count and not request.force_regenerate:
            return {
                "success": True,
                "exercise": approved_bank[0],
                "exercise_bank": approved_bank,
                "approved_exercise_bank": approved_bank,
                "approved": True,
                "cached": True,
                "feedback_summary": _exercise_feedback_summary(feedback),
                "generated_at": (cached_chapter or {}).get("updated_at") or datetime.now().isoformat(),
            }
        raw_cached_bank = _normalize_exercise_bank((cached_chapter or {}).get("exercise_bank") or (cached_chapter or {}).get("exercises"))
        pinned_bank = [
            item
            for item in raw_cached_bank
            if str((_exercise_feedback_for_item(item, feedback) or {}).get("rating") or "").lower() == "up"
        ]
        if approved_bank:
            pinned_bank = _merge_exercise_banks(approved_bank, pinned_bank, target_count)
        cached_bank = _filter_downvoted_exercises(
            raw_cached_bank,
            feedback,
        )
        if cached_bank and len(cached_bank) >= target_count and not request.force_regenerate:
            served_bank = _merge_exercise_banks(approved_bank, cached_bank, max(target_count, len(cached_bank))) if approved_bank else cached_bank
            return {
                "success": True,
                "exercise": served_bank[0],
                "exercise_bank": served_bank,
                "approved_exercise_bank": approved_bank,
                "cached": True,
                "review_pending": True,
                "feedback_summary": _exercise_feedback_summary(feedback),
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
            "content": chapter_content,
        }
        evidence = evidence_from_graph(
            graph_data if isinstance(graph_data, dict) else None,
            query=f"{request.chapter_title}\n{chapter_content[:800]}",
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
                chapter_content,
                request.count,
                graph_data,
                feedback_guidance=_build_exercise_feedback_guidance(feedback),
            ),
            timeout=exercise_timeout,
        )
        exercise_bank = _filter_downvoted_exercises(_normalize_exercise_bank(exercise_data), feedback)
        if not exercise_bank:
            raise ValueError("DeepSeek 返回的题库格式不可用")
        if len(exercise_bank) < target_count:
            supplemental_bank = _filter_downvoted_exercises(
                _build_local_exercise_bank(
                    chapter_id=request.chapter_id,
                    chapter_title=request.chapter_title,
                    chapter_content=chapter_content,
                    evidence=evidence,
                    count=target_count,
                ),
                feedback,
            )
            exercise_bank = _merge_exercise_banks(exercise_bank, supplemental_bank, target_count)
        if pinned_bank:
            exercise_bank = _merge_exercise_banks(pinned_bank, exercise_bank, target_count)
        if len(exercise_bank) < target_count:
            raise ValueError(f"题库数量不足：仅生成 {len(exercise_bank)} / {target_count} 题")
        saved_chapter = chapter_store.save_exercise_bank(
            chapter_id=request.chapter_id,
            exercises=exercise_bank,
        )

        return {
            "success": True,
            "exercise": exercise_bank[0],
            "exercise_bank": exercise_bank,
            "approved_exercise_bank": approved_bank,
            "chapter": saved_chapter,
            "model": claude_client.model,
            "review_pending": True,
            "learning_plan": learning_plan,
            "feedback_summary": _exercise_feedback_summary(feedback),
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
        target_count = _target_exercise_count(5)
        chapter = chapter_store.get_chapter(chapter_id) or {
            "id": chapter_id,
            "title": chapter_id.replace("_", " "),
            "content": "",
        }
        feedback = _exercise_feedback_map(chapter)
        approved_bank = _filter_downvoted_exercises(
            _normalize_exercise_bank(chapter.get("approved_exercise_bank")),
            feedback,
        )
        if approved_bank and len(approved_bank) >= target_count:
            return {
                "success": True,
                "chapter_id": chapter_id,
                "exercise": approved_bank[0],
                "exercise_bank": approved_bank,
                "approved_exercise_bank": approved_bank,
                "feedback_summary": _exercise_feedback_summary(feedback),
                "approved": True,
                "cached": True,
            }
        raw_cached_bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
        pinned_bank = [
            item
            for item in raw_cached_bank
            if str((_exercise_feedback_for_item(item, feedback) or {}).get("rating") or "").lower() == "up"
        ]
        cached_bank = _filter_downvoted_exercises(
            raw_cached_bank,
            feedback,
        )
        if cached_bank and len(cached_bank) >= target_count:
            served_bank = _merge_exercise_banks(approved_bank, cached_bank, max(target_count, len(cached_bank))) if approved_bank else cached_bank
            return {
                "success": True,
                "chapter_id": chapter_id,
                "exercise": served_bank[0],
                "exercise_bank": served_bank,
                "approved_exercise_bank": approved_bank,
                "feedback_summary": _exercise_feedback_summary(feedback),
                "cached": True,
                "review_pending": True,
            }

        evidence = _get_exercise_evidence(chapter_id, chapter)
        exercise_bank = _filter_downvoted_exercises(
            _build_local_exercise_bank(
                chapter_id=chapter_id,
                chapter_title=chapter.get("title") or chapter_id,
                chapter_content=chapter.get("content") or "",
                evidence=evidence,
                count=target_count,
            ),
            feedback,
        )
        if not exercise_bank:
            raise ValueError("No exercises remain after teacher feedback filtering")
        if approved_bank:
            exercise_bank = _merge_exercise_banks(approved_bank, exercise_bank, target_count)
        if pinned_bank:
            exercise_bank = _merge_exercise_banks(pinned_bank, exercise_bank, target_count)
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
            "approved_exercise_bank": approved_bank,
            "chapter": saved_chapter,
            "learning_plan": first_exercise.get("learning_plan"),
            "feedback_summary": _exercise_feedback_summary(feedback),
            "review_pending": True,
            "consistency_report": _safe_consistency_report(
                str(exercise_bank),
                first_exercise.get("learning_plan") or {},
                task="practice",
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取练习题失败: {str(e)}")


@app.get("/api/education/teacher/exercise-bank")
async def get_teacher_exercise_bank(chapter_id: str, refresh: bool = False):
    try:
        target_count = _target_exercise_count(5)
        chapter = chapter_store.get_chapter(chapter_id)
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        feedback = _exercise_feedback_map(chapter)
        approved_bank = _filter_downvoted_exercises(
            _normalize_exercise_bank(chapter.get("approved_exercise_bank")),
            feedback,
        )
        raw_exercise_bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
        exercise_bank = _filter_downvoted_exercises(raw_exercise_bank, feedback)
        if len(exercise_bank) != len(raw_exercise_bank):
            chapter = chapter_store.save_exercise_bank(chapter_id=chapter_id, exercises=exercise_bank)
        if approved_bank:
            exercise_bank = _merge_all_exercise_banks(approved_bank, exercise_bank)
        if refresh or len(exercise_bank) < target_count:
            base_bank = _merge_all_exercise_banks(approved_bank, exercise_bank)
            evidence = _get_exercise_evidence(chapter_id, chapter)
            generated_bank = _filter_downvoted_exercises(
                _build_local_exercise_bank(
                    chapter_id=chapter_id,
                    chapter_title=chapter.get("title") or chapter_id,
                    chapter_content=chapter.get("content") or "",
                    evidence=evidence,
                    count=target_count,
                ),
                feedback,
            )
            if refresh:
                continue_target = min(10, max(len(base_bank) + target_count, target_count))
                exercise_bank = _merge_exercise_banks(base_bank, generated_bank, continue_target)
            else:
                exercise_bank = _merge_exercise_banks(exercise_bank, generated_bank, target_count)
            chapter = chapter_store.save_exercise_bank(chapter_id=chapter_id, exercises=exercise_bank)

        feedback = _exercise_feedback_map(chapter)
        return {
            "success": True,
            "chapter_id": chapter_id,
            "chapter": chapter,
            "exercise_bank": _attach_exercise_feedback(exercise_bank, feedback),
            "approved_exercise_bank": _attach_exercise_feedback(approved_bank, feedback),
            "feedback_summary": _exercise_feedback_summary(feedback),
            "cached": not refresh,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Load teacher exercise bank failed: {e}")


@app.post("/api/education/teacher/regenerate-exercises")
async def regenerate_teacher_exercises(request: TeacherRegenerateExercisesRequest):
    chapter = chapter_store.get_chapter(request.chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    feedback = _exercise_feedback_map(chapter)
    existing_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises")),
        feedback,
    )
    approved_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank(chapter.get("approved_exercise_bank")),
        feedback,
    )
    retained_bank = _merge_all_exercise_banks(approved_bank, existing_bank)
    payload = await generate_exercises(
        GenerateExercisesRequest(
            chapter_id=request.chapter_id,
            chapter_title=chapter.get("title") or request.chapter_id,
            chapter_content=chapter.get("content") or "",
            count=request.count,
            force_regenerate=True,
        )
    )
    if isinstance(payload, dict) and payload.get("success"):
        latest_chapter = chapter_store.get_chapter(request.chapter_id) or chapter
        feedback = _exercise_feedback_map(latest_chapter)
        generated_bank = _filter_downvoted_exercises(
            _normalize_exercise_bank(payload.get("exercise_bank") or payload.get("exercise")),
            feedback,
        )
        approved_bank = _filter_downvoted_exercises(
            _normalize_exercise_bank(latest_chapter.get("approved_exercise_bank")),
            feedback,
        )
        retained_bank = _filter_downvoted_exercises(retained_bank, feedback)
        continue_target = min(10, max(len(retained_bank) + _target_exercise_count(request.count), _target_exercise_count(request.count)))
        exercise_bank = _merge_exercise_banks(retained_bank, generated_bank, continue_target)
        latest_chapter = chapter_store.save_exercise_bank(chapter_id=request.chapter_id, exercises=exercise_bank)
        feedback = _exercise_feedback_map(latest_chapter)
        payload["exercise_bank"] = _attach_exercise_feedback(exercise_bank, feedback)
        payload["approved_exercise_bank"] = _attach_exercise_feedback(approved_bank, feedback)
        payload["chapter"] = latest_chapter
        payload["feedback_summary"] = _exercise_feedback_summary(feedback)
        payload["continued"] = True
        payload["retained_count"] = len(retained_bank)
        payload["generated_count"] = len(generated_bank)
    return payload


@app.post("/api/education/teacher/exercise-feedback")
async def save_teacher_exercise_feedback(request: TeacherExerciseFeedbackRequest):
    rating = str(request.rating or "").strip().lower()
    if rating not in {"up", "down", "clear", "none", "neutral"}:
        raise HTTPException(status_code=400, detail="rating must be up, down, or clear")
    scope = str(request.scope or "exercise").strip().lower()
    if scope not in {"exercise", "option"}:
        raise HTTPException(status_code=400, detail="scope must be exercise or option")
    chapter = chapter_store.get_chapter(request.chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    store_chapter_id = str(chapter.get("id") or request.chapter_id)
    exercise_bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
    approved_bank = _normalize_exercise_bank(chapter.get("approved_exercise_bank"))
    searchable_bank = _merge_exercise_banks(exercise_bank, approved_bank, max(len(exercise_bank) + len(approved_bank), 1))
    exercise = _find_exercise_for_feedback(searchable_bank, request.exercise_id, request.question)
    if not exercise and request.feedback_key:
        exercise = _find_exercise_for_feedback(searchable_bank, request.feedback_key, request.question)
    if not exercise and request.question:
        snapshot_options = _format_options(_normalize_exercise_options(request.options or []))
        exercise = {
            "id": request.exercise_id,
            "question": request.question,
            "options": snapshot_options,
            "correct_answer": request.correct_answer or "",
        }
    if exercise and request.options and not _normalize_exercise_options(exercise.get("options")):
        exercise = dict(exercise)
        exercise["options"] = _format_options(_normalize_exercise_options(request.options))
        exercise["correct_answer"] = request.correct_answer or exercise.get("correct_answer") or ""
    elif exercise and request.correct_answer and not exercise.get("correct_answer"):
        exercise = dict(exercise)
        exercise["correct_answer"] = request.correct_answer
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    parent_feedback_key = str(request.feedback_key or "").strip() or _exercise_signature(exercise)
    feedback_key = parent_feedback_key
    option_key = ""
    option_text = ""
    if scope == "option":
        options = _normalize_exercise_options(exercise.get("options"))
        if not options and request.options:
            options = _format_options(_normalize_exercise_options(request.options))
        requested_key = str(request.option_key or "").strip().upper()
        option_index = -1
        if re.match(r"^[A-D]$", requested_key):
            option_index = ord(requested_key) - 65
        if option_index < 0 and request.option_text:
            requested_text = _compact_learning_text(_strip_option_letter(request.option_text), char_limit=160, word_limit=36).lower()
            for index, option in enumerate(options[:4]):
                current_text = _compact_learning_text(_strip_option_letter(option), char_limit=160, word_limit=36).lower()
                if current_text == requested_text:
                    option_index = index
                    break
        if option_index < 0 or option_index >= len(options[:4]):
            raise HTTPException(status_code=404, detail="Option not found")
        option_key = chr(65 + option_index)
        option_text = _strip_option_letter(options[option_index])
        feedback_key = str(request.option_feedback_key or "").strip() or _exercise_option_feedback_key(exercise, options[option_index], option_index)

    saved_chapter = chapter_store.save_exercise_feedback(
        chapter_id=store_chapter_id,
        feedback_key=feedback_key,
        rating=rating,
        exercise_id=str(exercise.get("id") or request.exercise_id),
        question=str(exercise.get("question") or request.question or ""),
        scope=scope,
        option_key=option_key,
        option_text=option_text,
        parent_feedback_key=parent_feedback_key if scope == "option" else "",
        note=request.note,
    )
    if scope == "exercise":
        saved_chapter = chapter_store.save_approved_exercise(
            chapter_id=store_chapter_id,
            exercise=exercise,
            feedback_key=parent_feedback_key,
            approved=rating == "up",
        )
        if rating == "down":
            current_bank = _normalize_exercise_bank(saved_chapter.get("exercise_bank") or saved_chapter.get("exercises"))
            current_bank = _remove_exercise_from_bank(current_bank, exercise, parent_feedback_key)
            saved_chapter = chapter_store.save_exercise_bank(
                chapter_id=store_chapter_id,
                exercises=current_bank,
            )
    feedback = _exercise_feedback_map(saved_chapter)
    exercise_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank(saved_chapter.get("exercise_bank") or saved_chapter.get("exercises")),
        feedback,
    )
    approved_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank(saved_chapter.get("approved_exercise_bank")),
        feedback,
    )
    return {
        "success": True,
        "chapter_id": store_chapter_id,
        "feedback_key": feedback_key,
        "scope": scope,
        "teacher_rating": "" if rating in {"clear", "none", "neutral"} else rating,
        "exercise_bank": _attach_exercise_feedback(exercise_bank, feedback),
        "approved_exercise_bank": _attach_exercise_feedback(approved_bank, feedback),
        "feedback_summary": _exercise_feedback_summary(feedback),
    }


@app.get("/api/education/teacher/exercise-feedback-export")
async def export_teacher_exercise_feedback(chapter_id: Optional[str] = None):
    try:
        chapters = [chapter_store.get_chapter(chapter_id)] if chapter_id else chapter_store.list_chapters()
        rows: List[Dict[str, Any]] = []
        for chapter in chapters:
            if not chapter:
                continue
            feedback = _exercise_feedback_map(chapter)
            if not feedback:
                continue
            bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
            bank_by_signature = {_exercise_signature(item): item for item in bank}
            for key, record in feedback.items():
                if not isinstance(record, dict):
                    continue
                parent_key = str(record.get("parent_feedback_key") or key)
                exercise = bank_by_signature.get(parent_key) or _find_exercise_for_feedback(
                    bank,
                    str(record.get("exercise_id") or ""),
                    str(record.get("question") or ""),
                ) or {}
                rows.append(
                    {
                        "chapter_id": chapter.get("id"),
                        "chapter_title": chapter.get("title"),
                        "feedback_key": key,
                        "scope": record.get("scope") or "exercise",
                        "rating": record.get("rating"),
                        "label": 1 if record.get("rating") == "up" else -1 if record.get("rating") == "down" else 0,
                        "question": exercise.get("question") or record.get("question"),
                        "options": exercise.get("options") or [],
                        "correct_answer": exercise.get("correct_answer") or exercise.get("answer") or "",
                        "option_key": record.get("option_key") or "",
                        "option_text": record.get("option_text") or "",
                        "updated_at": record.get("updated_at") or "",
                    }
                )
        return {"success": True, "count": len(rows), "records": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export exercise feedback failed: {e}")


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
