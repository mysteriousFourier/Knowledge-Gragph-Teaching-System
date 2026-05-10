from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from KGTS.models.education import (
    CheckAnswerRequest,
    GenerateExercisesRequest,
    GenerateReviewRequest,
    MarkChapterRequest,
    QuestionRequest,
    ResetProgressRequest,
)
from KGTS.models.auth import LoginRequest, StudentLoginRequest
from KGTS.core.mcp_client import call_mcp_tool
from KGTS.core.bridge import (
    build_frontend_graph,
    build_rag_context,
    chapter_store,
)
from KGTS.education.claude_api import DeepSeekAPIClient, get_deepseek_model
from KGTS.education.kg_constraints import (
    KG_CONSTRAINED_SYSTEM_PROMPT,
    build_kg_grounded_exercise,
    build_learning_plan,
    check_generation_consistency,
    evidence_from_graph,
    evidence_from_rag,
    expand_formula_references,
    format_evidence,
)
from KGTS.config import get_auth_config, load_root_env
from KGTS.education.exercise_helpers import (
    _build_exercise_feedback_guidance,
    _build_local_exercise_bank,
    _build_local_exercise_response,
    _exercise_feedback_for_item,
    _exercise_feedback_map,
    _exercise_feedback_summary,
    _filter_downvoted_exercises,
    _get_exercise_evidence,
    _merge_all_exercise_banks,
    _merge_exercise_banks,
    _normalize_exercise_bank,
    _target_exercise_count,
)
from KGTS.education.auth_helpers import verify_login_credentials
from KGTS.education.qa_helpers import (
    _build_plan_from_graph,
    _build_question_fallback_response,
    _safe_consistency_report,
    answer_with_retrieval,
)

load_root_env()

router = APIRouter(prefix="/api", tags=["student"])
logger = logging.getLogger(__name__)


def _sample_student_exercises(bank: List[Dict[str, Any]], count: int = 10) -> List[Dict[str, Any]]:
    normalized = _normalize_exercise_bank(bank)
    if len(normalized) <= count:
        sampled = list(normalized)
        random.shuffle(sampled)
        return sampled
    return random.sample(normalized, count)


def _exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _local_exercise_warning(request: GenerateExercisesRequest, exc: Exception) -> str:
    return (
        f"AI 题库暂不可用，已生成 {_target_exercise_count(request.count)} "
        f"道本地材料题供测试使用。原因：{_exception_message(exc)}"
    )


def _build_local_supplemental_exercises(
    *,
    request: GenerateExercisesRequest,
    chapter_title: str,
    chapter_content: str,
    evidence: List[Dict[str, Any]],
    feedback: Dict[str, Dict[str, Any]],
    target_count: int,
) -> List[Dict[str, Any]]:
    return _filter_downvoted_exercises(
        _normalize_exercise_bank(_build_local_exercise_bank(
            chapter_id=request.chapter_id,
            chapter_title=chapter_title,
            chapter_content=chapter_content,
            evidence=evidence,
            count=target_count,
        )),
        feedback,
    )


@router.post("/student/login")
async def student_login(request: StudentLoginRequest):
    try:
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
                "message": "登录成功",
            }
        return {"success": False, "error": "用户名或密码错误"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")


@router.get("/student/chapter")
async def get_student_chapter(chapter_id: str):
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
            "notes": "授课文案暂无",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节内容失败: {str(e)}")


@router.post("/student/mark-chapter")
async def mark_chapter_as_learned(request: MarkChapterRequest):
    try:
        status = (request.status or "learned").strip().lower()
        result = chapter_store.mark_chapter_status(
            request.chapter_id,
            request.student_id or "student_001",
            status,
        )
        messages = {
            "learned": "章节已标记为已学完",
            "reviewing": "章节已放回复习队列",
            "forgotten": "章节已标记为需要重新学习",
            "reset": "章节进度已重置",
        }
        return {
            "success": True,
            "message": messages.get(status, "章节进度已更新"),
            "chapter_id": request.chapter_id,
            "marked_at": result.get("updated_at") or result.get("learned_at"),
            "student_id": result["student_id"],
            "progress": result.get("progress"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标记章节失败: {str(e)}")


@router.get("/student/progress")
async def get_student_progress(student_id: str = "student_001"):
    try:
        return {
            "success": True,
            **chapter_store.progress(student_id),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取学习进度失败: {str(e)}")


@router.post("/student/reset-progress")
async def reset_student_progress(request: ResetProgressRequest):
    try:
        result = chapter_store.reset_progress(
            student_id=request.student_id or "student_001",
            chapter_id=request.chapter_id,
        )
        return {
            "success": True,
            "message": "学习进度已重置",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置学习进度失败: {str(e)}")


@router.post("/student/generate-exercises")
async def generate_exercises(request: GenerateExercisesRequest):
    graph_data = None
    try:
        target_count = _target_exercise_count(request.count)
        cached_chapter = chapter_store.get_chapter(request.chapter_id)
        effective_title = str(request.chapter_title or (cached_chapter or {}).get("title") or request.chapter_id).strip()
        raw_chapter_content = (
            request.chapter_content
            or (cached_chapter or {}).get("content")
            or (cached_chapter or {}).get("lecture_content")
            or ""
        )
        request.chapter_title = effective_title
        request.chapter_content = raw_chapter_content
        chapter_content = expand_formula_references(raw_chapter_content)
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
        cached_bank = _filter_downvoted_exercises(raw_cached_bank, feedback)
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

        try:
            graph_data = await call_mcp_tool("read_graph")
            if isinstance(graph_data, dict):
                graph_data = build_frontend_graph(graph_data)
        except Exception:
            try:
                graph_data = build_frontend_graph()
            except Exception:
                graph_data = None
        chapter_data = {
            "id": request.chapter_id,
            "title": effective_title,
            "content": chapter_content,
        }
        evidence = evidence_from_graph(
            graph_data if isinstance(graph_data, dict) else None,
            query=f"{effective_title}\n{chapter_content[:800]}",
            chapter_data=chapter_data,
            limit=8,
        )
        learning_plan = _build_plan_from_graph(
            query=effective_title,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            task="exercise",
            chapter_data=chapter_data,
        )
        if not learning_plan.get("evidence"):
            return _build_local_exercise_response(
                request,
                graph_data=graph_data if isinstance(graph_data, dict) else None,
                warning="当前图谱证据不足，已基于章节材料预创建本地题库；请补充章节相关图谱证据以提升可追溯性。",
            )

        claude_client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=request.model or get_deepseek_model("pro"),
        )
        exercise_data = await claude_client.generate_exercises(
            effective_title,
            chapter_content,
            request.count,
            graph_data,
            feedback_guidance=_build_exercise_feedback_guidance(feedback),
        )
        exercise_bank = _filter_downvoted_exercises(_normalize_exercise_bank(exercise_data), feedback)
        if len(exercise_bank) < target_count:
            supplemental_bank = _build_local_supplemental_exercises(
                request=request,
                chapter_title=effective_title,
                chapter_content=chapter_content,
                evidence=evidence,
                feedback=feedback,
                target_count=target_count,
            )
            exercise_bank = _merge_exercise_banks(exercise_bank, supplemental_bank, target_count)
            if len(exercise_bank) < target_count:
                exercise_bank = _merge_all_exercise_banks(exercise_bank, supplemental_bank)[:target_count]
        if not exercise_bank:
            raise ValueError("DeepSeek 返回的题库格式不可用，且本地图谱补题失败")
        if pinned_bank:
            merged_bank = _merge_exercise_banks(pinned_bank, exercise_bank, target_count)
            if len(merged_bank) < target_count:
                merged_bank = _merge_all_exercise_banks(merged_bank, pinned_bank, exercise_bank)[:target_count]
            exercise_bank = merged_bank
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
            "generated_at": datetime.now().isoformat(),
        }

    except ValueError as e:
        logger.warning("Exercise generation fell back to local KG bank: %s", _exception_message(e))
        return _build_local_exercise_response(
            request,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            warning=_local_exercise_warning(request, e),
        )
    except Exception as e:
        try:
            logger.warning("Exercise generation fell back to local KG bank: %s", _exception_message(e))
            return _build_local_exercise_response(
                request,
                graph_data=graph_data if isinstance(graph_data, dict) else None,
                warning=_local_exercise_warning(request, e),
            )
        except Exception as fallback_error:
            raise HTTPException(status_code=500, detail=f"生成练习题失败: {fallback_error}")


@router.get("/student/exercises")
async def get_student_exercises(chapter_id: str):
    try:
        target_count = 10
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
            served_bank = _sample_student_exercises(approved_bank, target_count)
            return {
                "success": True,
                "chapter_id": chapter_id,
                "exercise": served_bank[0],
                "exercise_bank": served_bank,
                "approved_exercise_bank": approved_bank,
                "feedback_summary": _exercise_feedback_summary(feedback),
                "approved": True,
                "cached": True,
            }
        raw_cached_bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
        cached_bank = _filter_downvoted_exercises(raw_cached_bank, feedback)
        if cached_bank and len(cached_bank) >= target_count:
            full_bank = _merge_all_exercise_banks(approved_bank, cached_bank) if approved_bank else cached_bank
            served_bank = _sample_student_exercises(full_bank, target_count)
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
        generated_bank = _filter_downvoted_exercises(
            _normalize_exercise_bank([build_kg_grounded_exercise(
                chapter_id=chapter_id,
                chapter_title=chapter.get("title") or chapter_id,
                chapter_content=chapter.get("content") or "",
                evidence=evidence,
            )]),
            feedback,
        )
        exercise_bank = _merge_all_exercise_banks(approved_bank, cached_bank, generated_bank)
        if not exercise_bank:
            raise ValueError("No exercises remain after teacher feedback filtering")
        saved_chapter = chapter_store.save_exercise_bank(
            chapter_id=chapter_id,
            exercises=exercise_bank,
        )
        served_bank = _sample_student_exercises(exercise_bank, target_count)
        first_exercise = served_bank[0]

        return {
            "success": True,
            "chapter_id": chapter_id,
            "exercise": first_exercise,
            "exercise_bank": served_bank,
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


@router.post("/student/check-answer")
async def check_student_answer_backend(request: CheckAnswerRequest):
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

        progress_update = chapter_store.record_practice_result(
            request.chapter_id,
            is_correct=is_correct,
            student_id="student_001",
        )

        return {
            "success": True,
            "is_correct": is_correct,
            "correct": is_correct,
            "correctness_score": score,
            "feedback": feedback,
            "explanation": explanation,
            "correct_answer": "",
            "progress": progress_update.get("progress"),
            "learning_plan": learning_plan,
            "consistency_report": _safe_consistency_report(
                f"{feedback}\n{explanation}",
                learning_plan,
                task="feedback",
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Check answer failed: {str(e)}")


@router.post("/student/question")
async def student_ask_question_backend(request: QuestionRequest):
    try:
        query_parts = [request.question]
        if request.chapter_id:
            query_parts.append(f"chapter_id: {request.chapter_id}")
        if request.context:
            query_parts.append(str(request.context)[:1600])
        return await answer_with_retrieval("\n\n".join(query_parts), request.api_key, timeout_seconds=35)
    except Exception as e:
        return _build_question_fallback_response(
            request.question,
            model=get_deepseek_model("flash"),
            warning=f"问答服务异常，已使用本地图谱检索回答：{e}",
        )


@router.post("/student/generate-review")
async def generate_student_review(request: GenerateReviewRequest):
    graph_data: Optional[Dict[str, Any]] = None
    try:
        chapter = chapter_store.get_chapter(request.chapter_id)
        if not chapter:
            return _build_local_review_response(
                request,
                chapter={"id": request.chapter_id, "title": request.chapter_id, "content": ""},
                graph_data=None,
                warning="未找到章节，已基于可用图谱证据生成兜底复习内容。",
            )

        try:
            graph_data = await call_mcp_tool("read_graph")
            if isinstance(graph_data, dict):
                graph_data = build_frontend_graph(graph_data)
        except Exception:
            try:
                graph_data = build_frontend_graph()
            except Exception:
                graph_data = None

        chapter_content = expand_formula_references(chapter.get("lecture_content") or chapter.get("content") or "")
        chapter_data = {
            "id": chapter.get("id") or request.chapter_id,
            "title": chapter.get("title") or request.chapter_id,
            "content": chapter_content,
        }
        evidence = evidence_from_graph(
            graph_data if isinstance(graph_data, dict) else None,
            query=f"{chapter_data['title']}\n{chapter_content[:1200]}",
            chapter_data=chapter_data,
            limit=10,
        )
        if chapter_content.strip():
            evidence = [
                {
                    "index": 1,
                    "id": "chapter_content",
                    "label": chapter_data["title"],
                    "type": "chapter_content",
                    "content": chapter_content[:1200],
                    "source": "chapter",
                },
                *[item for item in evidence if item.get("id") != "chapter_content"],
            ]
        learning_plan = build_learning_plan(
            query=chapter_data["title"],
            evidence=evidence,
            learner_intent="practice",
            learning_level="beginner",
            task="review",
            chapter_data=chapter_data,
        )

        try:
            client = DeepSeekAPIClient(
                api_key=request.api_key,
                model=request.model or get_deepseek_model("pro"),
            )
            review_content = expand_formula_references(
                await client._call_deepseek(
                    _build_review_prompt(chapter_data, learning_plan, request.count),
                    max_tokens=3600,
                    system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT,
                    read_timeout_seconds=60.0,
                ),
                expand_labels=True,
            )
            exercise_bank = _filter_downvoted_exercises(
                _normalize_exercise_bank(
                    await client.generate_exercises(
                        chapter_data["title"],
                        chapter_content,
                        request.count,
                        graph_data if isinstance(graph_data, dict) else None,
                    )
                ),
                _exercise_feedback_map(chapter),
            )
            if not exercise_bank:
                raise ValueError("复习题生成结果为空")
            return {
                "success": True,
                "chapter_id": chapter_data["id"],
                "review_content": review_content,
                "exercise_bank": exercise_bank,
                "learning_plan": learning_plan,
                "consistency_report": check_generation_consistency(
                    f"{review_content}\n{exercise_bank}",
                    learning_plan,
                    task="review",
                ),
                "model": client.model,
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            return _build_local_review_response(
                request,
                chapter=chapter_data,
                graph_data=graph_data if isinstance(graph_data, dict) else None,
                learning_plan=learning_plan,
                warning=f"AI 复习生成不可用，已使用图谱证据生成本地兜底内容：{exc}",
            )
    except Exception as e:
        return _build_local_review_response(
            request,
            chapter={"id": request.chapter_id, "title": request.chapter_id, "content": ""},
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            warning=f"复习生成失败，已使用本地兜底内容：{e}",
        )


@router.get("/student/review")
async def get_student_review_data_backend(chapter_id: Optional[str] = None, student_id: str = "student_001"):
    try:
        review = chapter_store.review(student_id=student_id, chapter_id=chapter_id)
        return {
            "success": True,
            "progress": review["progress"],
            "recommendations": review["recommendations"],
            "queue": review.get("queue", []),
            "chapter": review.get("chapter"),
            "path": review.get("path", []),
            "nodes": review.get("nodes", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取复习数据失败: {str(e)}")


def _build_review_prompt(chapter: Dict[str, Any], learning_plan: Dict[str, Any], count: int) -> str:
    title = str(chapter.get("title") or chapter.get("id") or "当前章节")
    content = str(chapter.get("content") or "")
    return f"""请为学生生成一份章节复习讲义。

章节：{title}

章节内容：
{content[:2200]}

可参考证据：
{format_evidence(learning_plan.get("evidence") or [])}

要求：
1. 输出 Markdown，包含：核心概念回顾、公式/符号说明、易错点、复习顺序、练习建议。
2. 如有公式，使用 LaTeX：$...$ 或 $$...$$。
3. 优先使用章节内容和证据，不要输出 LearningPlan 或内部检查说明。
4. 保留英文术语、变量名和公式原文。
5. 末尾给出 {max(1, count)} 条简短自测提示，但不要泄露完整答案。"""


def _build_local_review_response(
    request: GenerateReviewRequest,
    *,
    chapter: Dict[str, Any],
    graph_data: Optional[Dict[str, Any]],
    learning_plan: Optional[Dict[str, Any]] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    chapter_content = expand_formula_references(chapter.get("content") or "")
    chapter_data = {
        "id": chapter.get("id") or request.chapter_id,
        "title": chapter.get("title") or request.chapter_id,
        "content": chapter_content,
    }
    if learning_plan is None:
        evidence = evidence_from_graph(
            graph_data,
            query=f"{chapter_data['title']}\n{chapter_content[:1000]}",
            chapter_data=chapter_data,
            limit=8,
        )
        if chapter_content.strip():
            evidence = [
                {
                    "index": 1,
                    "id": "chapter_content",
                    "label": chapter_data["title"],
                    "type": "chapter_content",
                    "content": chapter_content[:1000],
                    "source": "chapter",
                },
                *evidence,
            ]
        learning_plan = build_learning_plan(
            query=chapter_data["title"],
            evidence=evidence,
            learner_intent="practice",
            learning_level="beginner",
            task="review",
            chapter_data=chapter_data,
        )

    evidence_items = learning_plan.get("evidence") or []
    evidence_lines = [
        f"- **{item.get('label') or item.get('id')}**：{str(item.get('content') or '')[:180]}"
        for item in evidence_items[:6]
    ]
    if not evidence_lines:
        evidence_lines = ["- 当前章节图谱证据不足，请先补充章节内容或导入图谱。"]

    review_content = "\n\n".join(
        [
            f"# {chapter_data['title']} 复习讲义",
            "## 核心证据",
            "\n".join(evidence_lines),
            "## 复习顺序",
            "1. 先通读章节中的定义、公式和变量说明。\n2. 对照上方证据复述每个概念的含义。\n3. 再做复习题，遇到不确定处回到原文或图谱节点。",
            "## 易错提醒",
            "不要把图谱中没有出现的关系当作课程结论；公式题要同时说明变量含义和适用条件。",
        ]
    )
    exercise_count = max(1, min(int(request.count or 5), 10))
    exercise_bank = []
    for index in range(exercise_count):
        exercise_bank.append(
            build_kg_grounded_exercise(
                chapter_id=str(chapter_data["id"]),
                chapter_title=str(chapter_data["title"]),
                chapter_content=chapter_content,
                evidence=evidence_items[index:] or evidence_items,
            )
        )

    return {
        "success": True,
        "chapter_id": chapter_data["id"],
        "review_content": review_content,
        "exercise_bank": _normalize_exercise_bank(exercise_bank),
        "learning_plan": learning_plan,
        "consistency_report": _safe_consistency_report(
            f"{review_content}\n{exercise_bank}",
            learning_plan,
            task="review",
        ),
        "generated_at": datetime.now().isoformat(),
        "warning": warning,
    }


@router.post("/student/question-legacy")
async def student_ask_question(request: QuestionRequest):
    try:
        return await answer_with_retrieval(request.question, request.api_key, timeout_seconds=35)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回答问题失败: {str(e)}")


@router.get("/student/review-legacy")
async def get_student_review_data():
    try:
        recommendations = [
            {"type": "需要复习", "content": "建议复习第一章的线性代数基础概念"},
            {"type": "学习建议", "content": "多做第二章向量空间的练习题巩固知识点"},
            {"type": "拓展学习", "content": "可以尝试学习线性变换的相关进阶内容"},
        ]
        return {
            "success": True,
            "progress": {"total_chapters": 4, "learned_chapters": 0, "progress_percentage": 0},
            "recommendations": recommendations,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取复习数据失败: {str(e)}")


@router.post("/student/check-answer-legacy")
async def check_student_answer(request: CheckAnswerRequest):
    try:
        return await check_student_answer_backend(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查答案失败: {str(e)}")


class LearningPathRequest(LoginRequest.__class__.__bases__[0]):
    chapter_id: str = ""
    student_id: Optional[str] = None
    learned_chapters: Optional[List[str]] = None


@router.post("/student/learning-path")
async def get_learning_path(chapter_id: str = "", student_id: Optional[str] = None, learned_chapters: Optional[List[str]] = None):
    try:
        graph_data = await call_mcp_tool("read_graph", {})
        graph = json.loads(graph_data) if isinstance(graph_data, str) else graph_data

        prerequisites = await call_mcp_tool(
            "get_prerequisites",
            {"node_id": chapter_id, "max_depth": 3},
        )
        prerequisites_data = json.loads(prerequisites) if isinstance(prerequisites, str) else prerequisites

        follow_up = await call_mcp_tool(
            "get_follow_up",
            {"node_id": chapter_id, "max_depth": 3},
        )
        follow_up_data = json.loads(follow_up) if isinstance(follow_up, str) else follow_up

        learned = learned_chapters or []

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
                        "status": "未学习",
                    })
                elif prereq_id:
                    learned_prerequisites.append({
                        "node_id": prereq_id,
                        "node": prereq.get("node", {}),
                        "depth": prereq.get("depth", 0),
                        "status": "已学习",
                    })

        recommended_next = []
        if isinstance(follow_up_data, list):
            for follow in follow_up_data:
                node_id = follow.get("node_id")
                if node_id and node_id not in learned:
                    recommended_next.append({
                        "node_id": node_id,
                        "node": follow.get("node", {}),
                        "depth": follow.get("depth", 0),
                        "status": "推荐学习",
                    })

        return {
            "success": True,
            "current_chapter": chapter_id,
            "learning_path": {
                "prerequisites": {
                    "learned": learned_prerequisites,
                    "unlearned": unlearned_prerequisites,
                    "status": "ready" if len(unlearned_prerequisites) == 0 else "need_prerequisites",
                },
                "current": {"node_id": chapter_id, "status": "learning"},
                "follow_up": {
                    "recommended": recommended_next[:5],
                    "total": len(recommended_next),
                },
            },
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取学习路径失败: {str(e)}")


@router.get("/student/prerequisites")
async def get_student_prerequisites(chapter_id: str, max_depth: int = 3):
    try:
        prerequisites = await call_mcp_tool(
            "get_prerequisites",
            {"node_id": chapter_id, "max_depth": max_depth},
        )
        prereq_data = json.loads(prerequisites) if isinstance(prerequisites, str) else prerequisites
        return {
            "success": True,
            "chapter_id": chapter_id,
            "prerequisites": prereq_data,
            "retrieved_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取前置知识失败: {str(e)}")


@router.get("/student/follow-up")
async def get_student_follow_up(chapter_id: str, max_depth: int = 3):
    try:
        follow_up = await call_mcp_tool(
            "get_follow_up",
            {"node_id": chapter_id, "max_depth": max_depth},
        )
        follow_up_data = json.loads(follow_up) if isinstance(follow_up, str) else follow_up
        return {
            "success": True,
            "chapter_id": chapter_id,
            "follow_up": follow_up_data,
            "retrieved_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取后置知识失败: {str(e)}")
