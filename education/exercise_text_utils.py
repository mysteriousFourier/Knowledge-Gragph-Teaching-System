"""Text-processing utilities for exercises."""
from __future__ import annotations

import re
from typing import Any, List

from KGTS.education.kg_constraints import expand_formula_references

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
    "thus",
    "therefore",
    "hence",
    "then",
    "however",
    "moreover",
    "consequently",
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

OPTION_PREFIX_RE = re.compile(r"^[A-D]\s*[.)\]\}\-:：、。．）]+\s*", re.I)
OPTION_KEY_RE = re.compile(r"^([A-D])(?:\s*[.)\]\}\-:：、。．）])?$", re.I)


def _strip_option_letter(value: Any) -> str:
    text = str(value or "").strip()
    previous = None
    while text and previous != text:
        previous = text
        text = OPTION_PREFIX_RE.sub("", text).strip()
    return text


def _normalize_option_key(value: Any) -> str:
    text = str(value or "").strip()
    match = OPTION_KEY_RE.match(text)
    return match.group(1).upper() if match else text


def _normalize_exercise_options(options: Any) -> List[str]:
    if isinstance(options, dict):
        normalized: List[str] = []
        for key, value in options.items():
            key_label = _normalize_option_key(key)
            value_text = _strip_option_letter(value)
            if not value_text:
                continue
            normalized.append(f"{key_label}. {value_text}" if key_label and len(key_label) <= 3 else value_text)
        return normalized

    if isinstance(options, list):
        normalized = []
        for item in options:
            if isinstance(item, dict):
                key_label = _normalize_option_key(item.get("key") or item.get("label") or item.get("id") or "")
                text = _strip_option_letter(item.get("text") or item.get("content") or item.get("value") or "")
                if text:
                    normalized.append(f"{key_label}. {text}" if key_label and len(key_label) <= 3 else text)
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
    text = re.sub(r"^\d+[.)、。\s]+", "", text).strip()
    return text


def _clean_exercise_text(value: Any, limit: int = 180) -> str:
    text = _normalize_math_text(value)
    if _contains_latex_math(text):
        return text
    if len(text) > limit:
        text = text[:limit].rstrip("，。；;,. ") + "..."
    return text


def _is_mostly_english(value: Any) -> bool:
    text = str(value or "")
    latin = len(re.findall(r"[A-Za-z]", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return latin > max(12, cjk * 2)


def _strip_english_discourse_prefix(value: Any) -> str:
    text = str(value or "").strip()
    pattern = r"^(?:thus|therefore|hence|then|however|moreover|consequently|in contrast|for example|for instance|to see this point)\b[\s,;:.-]*"
    previous = None
    while text and previous != text:
        previous = text
        text = re.sub(pattern, "", text, flags=re.I).strip()
    return text


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
    if re.fullmatch(r"[一二三四五六七八九十]+[、.-].{0,18}", text):
        return True
    if any(marker.lower() in compact for marker in TEACHING_SCAFFOLD_MARKERS):
        if not re.search(r"[=><]|：|:|是|等于|需要|用于|控制|定义|means|defined|equals|requires", text, flags=re.I):
            return True
    if re.search(r"\[\[(?:SEE_)?TABLE:", str(value or ""), flags=re.I):
        return True
    return False


def _is_generic_fact_label(value: Any) -> bool:
    text = _strip_english_discourse_prefix(_strip_reference_markers(value))
    text = _clean_exercise_text(text, limit=80).strip(" ，。；;,.!?！？()（）").lower()
    if not text:
        return True
    if "chapter_" in text or "chapter::" in text or text.startswith(("block::", "formula::", "equation::")):
        return True
    if re.fullmatch(r"(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(st|nd|rd|th)?|第?[一二三四五六七八九十]+个?)", text):
        return True
    if text in GENERIC_FACT_LABELS:
        return True
    if text.startswith("equation ") or text.startswith("formula "):
        return True
    if text.startswith("课堂") or text.startswith("教学") or text.startswith("启发"):
        return True
    return False


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


def _format_options(options: List[str], *, char_limit: int = 96, word_limit: int = 20) -> List[str]:
    from KGTS.education.exercise_formula_utils import _latex_option_text

    letters = ["A", "B", "C", "D"]
    compacted: List[str] = []
    for item in options:
        text = _compact_learning_text(item, char_limit=char_limit, word_limit=word_limit)
        if not text:
            continue
        compacted.append(_latex_option_text(text))
        if len(compacted) == 4:
            break
    return [f"{letters[index]}. {text}" for index, text in enumerate(compacted)]
