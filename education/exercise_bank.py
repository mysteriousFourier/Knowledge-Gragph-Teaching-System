"""Exercise bank management utilities."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from KGTS.education.exercise_text_utils import (
    _compact_question_text,
    _normalize_exercise_options,
    _strip_option_letter,
)


def _normalize_exercise_bank(payload: Any) -> List[Dict[str, Any]]:
    if not payload:
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("exercises") or [payload]
    else:
        return []
    result: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        options = _normalize_exercise_options(item.get("options"))
        if not options or len(options) < 2:
            continue
        correct = _normalize_correct_answer(item.get("correct_answer") or item.get("answer"))
        result.append({
            "id": str(item.get("id") or ""),
            "question": question,
            "options": options,
            "correct_answer": correct,
            "explanation": str(item.get("explanation") or ""),
            "learning_plan": item.get("learning_plan"),
        })
    return result


def _normalize_correct_answer(value: Any) -> str:
    if isinstance(value, int):
        return chr(65 + value) if 0 <= value < 26 else str(value)
    text = str(value or "").strip()
    if not text:
        return ""
    match = text[:1].upper()
    return match if "A" <= match <= "Z" else text


def _exercise_signature(exercise: Dict[str, Any]) -> str:
    question = _compact_question_text(str((exercise or {}).get("question") or ""))
    options = _normalize_exercise_options((exercise or {}).get("options"))
    option_stubs = [_strip_option_letter(o)[:40].lower() for o in options[:4]]
    return hashlib.md5((question + "||" + "||".join(option_stubs)).encode()).hexdigest()[:12]


def _exercise_feedback_map(chapter: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not chapter or not isinstance(chapter, dict):
        return {}
    return dict(chapter.get("exercise_feedback") or {})


def _exercise_feedback_for_item(
    exercise: Dict[str, Any],
    feedback: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    sig = _exercise_signature(exercise)
    if sig in feedback:
        return feedback[sig]
    eid = str(exercise.get("id") or "")
    if eid and eid in feedback:
        return feedback[eid]
    return None


def _exercise_option_feedback_key(exercise: Dict[str, Any], option: Any, index: int) -> str:
    sig = _exercise_signature(exercise)
    key = chr(65 + index) if 0 <= index < 4 else str(index)
    return f"{sig}__opt_{key}"


def _attach_exercise_feedback(
    bank: List[Dict[str, Any]],
    feedback: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result = []
    for exercise in bank:
        exercise = dict(exercise)
        item_feedback = _exercise_feedback_for_item(exercise, feedback)
        if item_feedback:
            exercise["teacher_rating"] = item_feedback.get("rating") or ""
            exercise["teacher_note"] = item_feedback.get("note") or ""
        result.append(exercise)
    return result


def _filter_downvoted_exercises(
    bank: List[Dict[str, Any]],
    feedback: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    result = []
    for exercise in bank:
        item_feedback = _exercise_feedback_for_item(exercise, feedback)
        if item_feedback and str(item_feedback.get("rating") or "").lower() == "down":
            continue
        result.append(exercise)
    return result


def _same_exercise_target(
    item: Dict[str, Any],
    exercise: Dict[str, Any],
    feedback_key: str = "",
) -> bool:
    if str(item.get("id") or "") == str(exercise.get("id") or ""):
        return True
    if _exercise_signature(item) == _exercise_signature(exercise):
        return True
    if feedback_key and _exercise_signature(item) == feedback_key:
        return True
    return False


def _remove_exercise_from_bank(
    bank: List[Dict[str, Any]],
    exercise: Dict[str, Any],
    feedback_key: str = "",
) -> List[Dict[str, Any]]:
    return [item for item in bank if not _same_exercise_target(item, exercise, feedback_key)]


def _merge_all_exercise_banks(*banks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for bank in banks:
        for item in bank:
            sig = _exercise_signature(item)
            if sig not in seen:
                seen.add(sig)
                merged.append(item)
    return merged


def _exercise_feedback_summary(feedback: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    up = down = 0
    for record in (feedback or {}).values():
        if not isinstance(record, dict):
            continue
        rating = str(record.get("rating") or "").lower()
        if rating == "up":
            up += 1
        elif rating == "down":
            down += 1
    return {"exercise_up": up, "exercise_down": down}


def _build_exercise_feedback_guidance(feedback: Dict[str, Dict[str, Any]]) -> str:
    if not feedback:
        return ""
    lines = []
    for key, record in feedback.items():
        if not isinstance(record, dict):
            continue
        rating = str(record.get("rating") or "").lower()
        if rating not in {"up", "down"}:
            continue
        question = str(record.get("question") or "")[:80]
        note = str(record.get("note") or "")
        scope = str(record.get("scope") or "exercise")
        if scope == "option":
            option_key = str(record.get("option_key") or "")
            option_text = str(record.get("option_text") or "")[:60]
            lines.append(f"- [{rating}] 选项 {option_key}「{option_text}」(题目: {question}) {note}")
        else:
            lines.append(f"- [{rating}] 题目: {question} {note}")
    return "\n".join(lines[:20])


def _extract_json_object_text(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        return text[first:last + 1]
    return text


def _replace_option_in_exercise(exercise: Dict[str, Any], option_index: int, replacement_text: Any) -> Dict[str, Any]:
    exercise = dict(exercise)
    options = list(_normalize_exercise_options(exercise.get("options")))
    while len(options) <= option_index:
        options.append("")
    options[option_index] = f"{chr(65 + option_index)}. {replacement_text}"
    exercise["options"] = options
    return exercise


def _replace_exercise_in_bank(
    bank: List[Dict[str, Any]],
    exercise: Dict[str, Any],
    updated_exercise: Dict[str, Any],
    feedback_key: str = "",
) -> List[Dict[str, Any]]:
    result = []
    for item in bank:
        if _same_exercise_target(item, exercise, feedback_key):
            result.append(updated_exercise)
        else:
            result.append(item)
    return result


def _option_compare_key(value: Any) -> str:
    from KGTS.education.exercise_text_utils import _compact_learning_text, _strip_option_letter
    return _compact_learning_text(_strip_option_letter(value), char_limit=130, word_limit=28).lower()


def _same_question_option_history(
    feedback: Dict[str, Dict[str, Any]],
    question: str,
) -> List[str]:
    target = _compact_question_text(question).lower()
    result: List[str] = []
    for record in (feedback or {}).values():
        if not isinstance(record, dict):
            continue
        if str(record.get("scope") or "") != "option":
            continue
        rec_question = _compact_question_text(str(record.get("question") or "")).lower()
        if rec_question and rec_question != target:
            continue
        option_text = str(record.get("option_text") or "")
        if option_text:
            result.append(option_text)
    return result
