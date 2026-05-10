"""Formula-related utilities for exercises."""
from __future__ import annotations

import re
from typing import Any, List

from KGTS.education.exercise_text_utils import (
    _clean_exercise_text,
    _compact_learning_text,
    _contains_latex_math,
    _is_mostly_english,
    _normalize_math_text,
    _strip_option_letter,
    _strip_reference_markers,
)


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


def _is_pure_formula_text(value: Any) -> bool:
    text = _strip_reference_markers(value).strip()
    if not text:
        return False
    formulas = _extract_formula_candidates(text)
    if not formulas:
        return False
    remainder = text
    for formula in formulas:
        remainder = remainder.replace(formula, " ")
    remainder = re.sub(r"\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+?\$", " ", remainder)
    remainder = re.sub(r"[\s,.;:，。；：()（）\[\]【】]+", "", remainder)
    return len(remainder) < 8


def _extract_formula_candidates(value: Any) -> List[str]:
    raw_text = str(value or "")
    text = _strip_reference_markers(raw_text)
    patterns = [
        r"\$\$([\s\S]+?)\$\$",
        r"\\\[([\s\S]+?)\\\]",
        r"\\\(([\s\S]+?)\\\)",
        r"\$([^$\n]+?)\$",
        r"([A-Za-zΑ-Ωα-ω][A-Za-z0-9Α-Ωα-ω_{}^\\]*\s*=\s*[^。；;\n]+)",
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
        ("+", "-"), ("-", "+"), ("\\sum", "\\prod"), ("\\prod", "\\sum"),
        ("^2", ""), ("_t", "_{t+1}"),
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
        variants.append(f"{lhs} = 1")
        variants.append(f"{lhs} = {lhs}")
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


def _split_latex_fraction(formula: str) -> tuple[str, str] | None:
    match = re.search(r"\\frac\{(.+)\}\{(.+)\}", str(formula or ""))
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _latex_option_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "$" in text or re.search(r"\\\(|\\\[|\\begin\{", text):
        return text
    stripped = _strip_option_letter(text)
    if _is_pure_formula_text(stripped):
        return f"${stripped}$"
    if _looks_like_formula_text(stripped) and not re.search(r"[\u4e00-\u9fff]", stripped) and len(stripped.split()) <= 10:
        return f"${text}$"
    return re.sub(
        r"(?<![$A-Za-z])([A-Za-zΑ-Ωα-ω][A-Za-z0-9Α-Ωα-ω_{}^\\]*(?:\s*[+\-*/]\s*[A-Za-z0-9Α-Ωα-ω_{}^\\]+)?\s*(?:[<>]=?|≤|≥|=)\s*[A-Za-z0-9Α-Ωα-ω_{}^\\]+)(?![$A-Za-z])",
        lambda match: f"${match.group(1).strip()}$",
        text,
    )


def _option_length_score(value: Any) -> int:
    text = _strip_option_letter(value)
    text = re.sub(r"\$+", "", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[\s{}_^]+", " ", text).strip()
    if not text:
        return 0
    if _is_mostly_english(text):
        return max(len(text.split()) * 4, len(text) // 2)
    return len(text)


def _correct_option_length_outlier(options: List[str], correct_answer: Any) -> bool:
    from KGTS.education.exercise_text_utils import _normalize_correct_answer

    answer = _normalize_correct_answer(correct_answer)
    if not re.match(r"^[A-D]$", answer):
        return False
    index = ord(answer) - 65
    if index < 0 or index >= len(options):
        return False
    stripped = [_strip_option_letter(option) for option in options]
    if sum(1 for option in stripped if _looks_like_formula_text(option)) >= 3:
        return False
    lengths = [_option_length_score(option) for option in stripped]
    correct_length = lengths[index]
    other_lengths = [length for pos, length in enumerate(lengths) if pos != index and length > 0]
    if not other_lengths or correct_length <= 0:
        return False
    other_lengths.sort()
    median_other = other_lengths[len(other_lengths) // 2]
    max_other = max(other_lengths)
    return correct_length >= 42 and correct_length > max(max_other + 24, median_other * 1.75)
