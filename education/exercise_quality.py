"""Quality-check utilities for exercises."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from KGTS.education.exercise_formula_utils import (
    _correct_option_length_outlier,
    _looks_like_formula_text,
)
from KGTS.education.exercise_text_utils import (
    _clean_exercise_text,
    _compact_learning_text,
    _compact_question_text,
    _is_generic_fact_label,
    _is_teaching_scaffold_text,
    _normalize_exercise_options,
    _strip_markdown_label,
    _strip_option_letter,
    _strip_reference_markers,
)


def _is_placeholder_exercise(item: Dict[str, Any], question: str, options: List[str]) -> bool:
    text = " ".join([str(item.get("id") or ""), question, " ".join(options)])
    placeholder_markers = [
        "sample", "示例", "测试", "选项一", "选项二", "选项三", "选项四",
        "learningplan", "current evidence", "graph evidence",
        "knowledge graph constraint", "知识图谱约束", "图谱证据", "当前证据",
        "当前图谱依据不足", "当前图谱是否有足够证据",
        "which statement best matches this source passage",
        "which statement is directly stated in the material",
        "which option is correct", "what is this",
        "what is the key point about", "what does the source say about",
        "directly stated in the material", "source passage",
        "formatting detail", "random value unrelated",
        "chapter title rather than", "see_formula", "see_table",
        "[[formula", "[[table", "[[see_formula", "[[see_table",
        "最符合这段材料", "最符合当前证据", "材料直接表达", "下列哪项正确",
        "课堂导入", "授课文案", "教学目标", "启发提问", "教学要点",
        "小组讨论", "课后思考", "只是排版格式", "随机数值",
        "章节标题本身", "kg_gap",
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


def _is_bad_exercise_question(question: Any) -> bool:
    text = str(question or "").strip()
    lowered = text.lower()
    if not text:
        return True
    if "chapter_" in lowered or "chapter::" in lowered or "[[" in text or "see_formula" in lowered:
        return True
    if re.search(r"\bwhat is the key point about\b|\bwhat does the material say about\s+(thus|therefore|hence|then)\b", lowered):
        return True
    if re.search(r"\bwhat\s+(?:is|can|does)\s+(?:is there|the critical insight from equation|\(left\)|\(right\))", lowered):
        return True
    if re.search(r"\b(which formula defines|which formula is stated for)\s+(the\s+)?(chapter|first|second|third|fourth|fifth|\d+)", lowered):
        return True
    if re.search(r"哪个公式定义了|哪个公式.*(第?[一二三四五六七八九十]+个|chapter)|公式.*chapter_", text, flags=re.I):
        return True
    return False


def _is_low_quality_exercise(item: Dict[str, Any]) -> bool:
    question = item.get("question") if isinstance(item, dict) else ""
    if _is_bad_exercise_question(question):
        return True
    options = _normalize_exercise_options((item or {}).get("options"))
    clean_options = [
        _compact_learning_text(_strip_option_letter(option), char_limit=130, word_limit=28).lower()
        for option in options
    ]
    clean_options = [option for option in clean_options if option]
    if len(clean_options) != 4 or len(set(clean_options)) != 4:
        return True
    formula_options = sum(1 for option in clean_options if _looks_like_formula_text(option))
    if formula_options >= 3 and not re.search(r"formula|equation|公式|方程", str(question), flags=re.I):
        return True
    if _correct_option_length_outlier(options, (item or {}).get("correct_answer") or (item or {}).get("answer")):
        return True
    return False


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
        if _is_low_quality_exercise(item):
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
    return False
