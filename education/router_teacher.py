from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from KGTS.models.education import (
    GenerateExercisesRequest,
    TeacherExerciseFeedbackRequest,
    TeacherRegenerateExercisesRequest,
    TeacherRegenerateOptionRequest,
)
from KGTS.models.auth import TeacherLoginRequest
from KGTS.core.bridge import chapter_store
from KGTS.education.kg_constraints import build_kg_grounded_exercise
from KGTS.config import get_auth_config, load_root_env
from KGTS.education.exercise_helpers import (
    _attach_exercise_feedback,
    _compact_learning_text,
    _exercise_feedback_map,
    _exercise_feedback_summary,
    _exercise_option_feedback_key,
    _exercise_signature,
    _filter_downvoted_exercises,
    _find_exercise_for_feedback,
    _format_options,
    _generate_replacement_option_text,
    _get_exercise_evidence,
    _local_replacement_option,
    _merge_all_exercise_banks,
    _merge_exercise_banks,
    _normalize_correct_answer,
    _normalize_exercise_bank,
    _normalize_exercise_options,
    _option_compare_key,
    _remove_exercise_from_bank,
    _replace_exercise_in_bank,
    _replace_option_in_exercise,
    _same_exercise_target,
    _same_question_option_history,
    _strip_option_letter,
    _target_exercise_count,
)
from KGTS.education.auth_helpers import verify_login_credentials
from KGTS.education.router_student import generate_exercises

load_root_env()

router = APIRouter(prefix="/api", tags=["teacher"])


@router.post("/teacher/login")
async def teacher_login(request: TeacherLoginRequest):
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
        return {"success": False, "error": "用户名或密码错误"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")


@router.get("/education/teacher/exercise-bank")
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
                _normalize_exercise_bank([build_kg_grounded_exercise(
                    chapter_id=chapter_id,
                    chapter_title=chapter.get("title") or chapter_id,
                    chapter_content=chapter.get("content") or "",
                    evidence=evidence,
                )]),
                feedback,
            )
            if refresh:
                continue_target = max(len(base_bank) + target_count, target_count)
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


@router.post("/education/teacher/regenerate-exercises")
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
            chapter_title=request.chapter_title or chapter.get("title") or request.chapter_id,
            chapter_content=request.chapter_content or chapter.get("content") or chapter.get("lecture_content") or "",
            count=request.count,
            api_key=request.api_key,
            model=request.model,
            force_regenerate=True,
        )
    )
    if isinstance(payload, dict) and payload.get("success"):
        latest_chapter = chapter_store.get_chapter(request.chapter_id) or chapter
        feedback = _exercise_feedback_map(latest_chapter)
        payload_bank = _normalize_exercise_bank(payload.get("exercise_bank") or payload.get("exercise"))
        persisted_candidate_bank = _normalize_exercise_bank(latest_chapter.get("exercise_bank") or latest_chapter.get("exercises"))
        generated_bank = _filter_downvoted_exercises(
            _merge_all_exercise_banks(payload_bank, persisted_candidate_bank),
            feedback,
        )
        retained_bank = _filter_downvoted_exercises(retained_bank, feedback)
        approved_bank = _filter_downvoted_exercises(approved_bank, feedback)
        batch_count = _target_exercise_count(request.count)
        new_candidates = [
            item
            for item in generated_bank
            if not any(_same_exercise_target(item, retained_item) for retained_item in retained_bank)
        ]
        continue_target = max(len(retained_bank) + batch_count, batch_count)
        exercise_bank = _merge_exercise_banks(retained_bank, new_candidates, continue_target)
        added_count = max(0, len(exercise_bank) - len(retained_bank))
        latest_chapter = chapter_store.save_exercise_bank(chapter_id=request.chapter_id, exercises=exercise_bank)
        feedback = _exercise_feedback_map(latest_chapter)
        payload["exercise_bank"] = _attach_exercise_feedback(exercise_bank, feedback)
        payload["approved_exercise_bank"] = _attach_exercise_feedback(approved_bank, feedback)
        payload["chapter"] = latest_chapter
        payload["feedback_summary"] = _exercise_feedback_summary(feedback)
        payload["continued"] = True
        payload["retained_count"] = len(retained_bank)
        payload["generated_count"] = len(generated_bank)
        payload["added_count"] = added_count
        if added_count == 0:
            payload["warning"] = "当前章节没有生成新的可用题目，可能已达到题库上限或候选题都被教师反馈过滤。"
    return payload


@router.post("/education/teacher/regenerate-option")
async def regenerate_teacher_option(request: TeacherRegenerateOptionRequest):
    rating = str(request.rating or "down").strip().lower()
    if rating not in {"down", "clear", "none", "neutral"}:
        raise HTTPException(status_code=400, detail="option regeneration only supports down or clear")
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
        exercise = {
            "id": request.exercise_id,
            "question": request.question,
            "options": _format_options(_normalize_exercise_options(request.options or [])),
            "correct_answer": request.correct_answer or "",
        }
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    options = _format_options(_normalize_exercise_options(exercise.get("options") or request.options or []))
    requested_key = str(request.option_key or "").strip().upper()
    if not re.match(r"^[A-D]$", requested_key):
        raise HTTPException(status_code=400, detail="option_key must be A, B, C, or D")
    option_index = ord(requested_key) - 65
    if option_index < 0 or option_index >= len(options[:4]):
        raise HTTPException(status_code=404, detail="Option not found")

    exercise = dict(exercise)
    exercise["options"] = options
    if request.correct_answer and not exercise.get("correct_answer"):
        exercise["correct_answer"] = request.correct_answer
    old_option = options[option_index]
    parent_feedback_key = str(request.feedback_key or "").strip() or _exercise_signature(exercise)
    option_feedback_key = str(request.option_feedback_key or "").strip() or _exercise_option_feedback_key(exercise, old_option, option_index)

    saved_chapter = chapter_store.save_exercise_feedback(
        chapter_id=store_chapter_id,
        feedback_key=option_feedback_key,
        rating="down" if rating == "down" else rating,
        exercise_id=str(exercise.get("id") or request.exercise_id),
        question=str(exercise.get("question") or request.question or ""),
        scope="option",
        option_key=requested_key,
        option_text=_strip_option_letter(old_option),
        parent_feedback_key=parent_feedback_key,
        note=request.note,
    )
    feedback_after_save = _exercise_feedback_map(saved_chapter)
    forbidden_options = _same_question_option_history(feedback_after_save, exercise.get("question") or request.question or "")
    forbidden_options.extend(options)

    if rating != "down":
        feedback = feedback_after_save
        return {
            "success": True,
            "chapter_id": store_chapter_id,
            "scope": "option",
            "option_key": requested_key,
            "teacher_rating": "",
            "exercise_bank": _attach_exercise_feedback(_filter_downvoted_exercises(exercise_bank, feedback), feedback),
            "approved_exercise_bank": _attach_exercise_feedback(_filter_downvoted_exercises(approved_bank, feedback), feedback),
            "feedback_summary": _exercise_feedback_summary(feedback),
        }

    replacement_text, replacement_source = await _generate_replacement_option_text(
        request=request,
        exercise=exercise,
        option_index=option_index,
        option_text=old_option,
        chapter=saved_chapter,
        forbidden_options=forbidden_options,
    )
    existing_other_options = {_option_compare_key(option) for index, option in enumerate(options) if index != option_index}
    existing_other_options.update(_option_compare_key(option) for option in forbidden_options)
    existing_other_options.discard("")
    replacement_clean = _compact_learning_text(_strip_option_letter(replacement_text), char_limit=96, word_limit=20)
    if not replacement_clean or _option_compare_key(replacement_clean) in existing_other_options:
        replacement_clean = _local_replacement_option(
            question=str(exercise.get("question") or request.question or ""),
            old_option=old_option,
            options=options,
            correct_answer=_normalize_correct_answer(request.correct_answer or exercise.get("correct_answer") or exercise.get("answer")),
            option_key=requested_key,
            forbidden_options=forbidden_options,
        )
        replacement_source = "local"

    updated_exercise = _replace_option_in_exercise(exercise, option_index, replacement_clean)
    latest_chapter = chapter_store.get_chapter(store_chapter_id) or saved_chapter
    current_bank = _normalize_exercise_bank(latest_chapter.get("exercise_bank") or latest_chapter.get("exercises"))
    current_approved_bank = _normalize_exercise_bank(latest_chapter.get("approved_exercise_bank"))
    approved_match = any(_same_exercise_target(item, exercise, parent_feedback_key) for item in current_approved_bank)
    updated_bank = _replace_exercise_in_bank(current_bank, exercise, updated_exercise, parent_feedback_key)
    latest_chapter = chapter_store.save_exercise_bank(chapter_id=store_chapter_id, exercises=updated_bank)
    if approved_match:
        latest_chapter = chapter_store.save_approved_exercise(
            chapter_id=store_chapter_id,
            exercise=updated_exercise,
            feedback_key=parent_feedback_key,
            approved=True,
        )

    feedback = _exercise_feedback_map(latest_chapter)
    exercise_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank(latest_chapter.get("exercise_bank") or latest_chapter.get("exercises")),
        feedback,
    )
    approved_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank(latest_chapter.get("approved_exercise_bank")),
        feedback,
    )
    return {
        "success": True,
        "chapter_id": store_chapter_id,
        "scope": "option",
        "option_key": requested_key,
        "old_option": old_option,
        "replacement_option": updated_exercise["options"][option_index],
        "replacement_source": replacement_source,
        "exercise_bank": _attach_exercise_feedback(exercise_bank, feedback),
        "approved_exercise_bank": _attach_exercise_feedback(approved_bank, feedback),
        "feedback_summary": _exercise_feedback_summary(feedback),
    }


@router.post("/education/teacher/exercise-feedback")
async def save_teacher_exercise_feedback(request: TeacherExerciseFeedbackRequest):
    rating = str(request.rating or "").strip().lower()
    legacy_feedback = str(request.feedback or "").strip().lower()
    if not rating and legacy_feedback:
        rating = {"like": "up", "dislike": "down"}.get(legacy_feedback, legacy_feedback)
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


@router.get("/education/teacher/exercise-feedback-export")
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
