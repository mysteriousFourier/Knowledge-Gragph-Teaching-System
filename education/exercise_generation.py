"""Exercise generation logic."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from KGTS.education.claude_api import DeepSeekAPIClient, get_deepseek_model
from KGTS.education.exercise_bank import (
    _exercise_feedback_map,
    _extract_json_object_text,
    _filter_downvoted_exercises,
    _merge_all_exercise_banks,
    _exercise_feedback_for_item,
    _normalize_exercise_bank,
)
from KGTS.education.exercise_formula_utils import (
    _extract_formula_candidates,
    _formula_distractors,
    _is_pure_formula_text,
    _latex_option_text,
    _looks_like_formula_text,
    _looks_like_short_math_part,
)
from KGTS.education.exercise_text_utils import (
    _clean_exercise_text,
    _compact_learning_text,
    _compact_question_text,
    _format_options,
    _is_generic_fact_label,
    _is_mostly_english,
    _is_teaching_scaffold_text,
    _normalize_correct_answer,
    _normalize_exercise_options,
    _strip_english_discourse_prefix,
    _strip_markdown_label,
    _strip_option_letter,
)
from KGTS.education.exercise_quality import (
    _exercise_option_token_set,
    _has_reused_option_set,
    _is_bad_exercise_question,
    _is_low_quality_exercise,
    _is_placeholder_exercise,
    _merge_exercise_banks,
)
from KGTS.education.kg_constraints import (
    build_learning_plan,
    evidence_from_graph,
    expand_formula_references,
)
from KGTS.models.education import GenerateExercisesRequest, TeacherRegenerateOptionRequest


def _get_exercise_evidence(chapter_id: str, chapter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    from KGTS.core.bridge import build_frontend_graph

    try:
        graph_data = build_frontend_graph()
    except Exception:
        graph_data = None
    chapter_data = chapter or {"id": chapter_id, "title": chapter_id, "content": ""}
    return evidence_from_graph(
        graph_data,
        query=str((chapter_data or {}).get("title") or chapter_id),
        chapter_data=chapter_data,
        limit=10,
    )


def _exercise_language(*values: Any) -> str:
    joined = " ".join(str(value or "") for value in values)
    return "en" if _is_mostly_english(joined) else "zh"


def _clean_focus_text(value: Any, fallback: Any = "") -> str:
    text = _compact_learning_text(value, char_limit=54, word_limit=8)
    text = re.sub(r"^(the|a|an)\s+", "", text, flags=re.I).strip()
    text = re.sub(r"^(这个|该|这种|这一)\s*", "", text).strip()
    if not text or _is_generic_fact_label(text):
        text = _compact_learning_text(fallback, char_limit=54, word_limit=8)
    return text


def _exercise_focus(content: Any, fallback: Any = "") -> str:
    text = _clean_exercise_text(_strip_markdown_label(content), limit=160)
    if _is_mostly_english(text):
        text = _strip_english_discourse_prefix(text)
        lowered = f" {text.lower()} "
        cut = None
        for marker in [
            " is ", " are ", " can ", " may ", " means ", " refers to ",
            " computes ", " updates ", " controls ", " depends on ",
            " changes ", " applies ", " uses ", " represents ", " describes ",
        ]:
            position = lowered.find(marker)
            if 0 < position < 80:
                cut = position
                break
        focus = text[:cut].strip() if cut else " ".join(text.split()[:5])
        focus = re.sub(r"\b(then|therefore|thus|can|may)$", "", focus, flags=re.I).strip()
        focus = _clean_focus_text(focus, fallback) or "this concept"
        return _compact_learning_text(focus, char_limit=48, word_limit=7)

    focus = re.split(r"[，。；:：]|是|指|可以|用于|由|通过|控制|可能|能够|需要|包含", text, maxsplit=1)[0].strip()
    focus = _clean_focus_text(focus, fallback) or "这个知识点"
    return _compact_learning_text(focus, char_limit=28, word_limit=7)


def _is_formula_source(source: Dict[str, Any]) -> bool:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    source_type = str(source.get("type") or source.get("node_type") or metadata.get("type") or "").lower()
    label = str(source.get("label") or metadata.get("label") or source.get("id") or "")
    content = str(source.get("content") or "")
    if source_type in {"formula", "equation", "math"}:
        return True
    if re.search(r"^\s*(formula|equation|eq\.|公式)\b|公式\s*\d+", label, flags=re.I):
        return True
    return _is_pure_formula_text(content)


def _source_quality_score(source: Dict[str, Any]) -> int:
    content = str(source.get("content") or "")
    label = str(source.get("label") or "")
    source_type = str(source.get("type") or "").lower()
    score = 0
    if source.get("source") == "chapter":
        score += 4
    if source_type in {"chapter_content", "concept", "proposition", "definition", "theorem"}:
        score += 3
    if len(content) >= 45:
        score += 2
    if re.search(r"\b(is|means|requires|controls|relates|computes|updates|selection|fitness|variance|inheritance)\b|是|需要|控制|用于|选择|适应性|方差|遗传", content, flags=re.I):
        score += 2
    if _is_formula_source(source):
        score -= 8
    if "chapter_" in f"{label} {content}".lower() or "chapter::" in f"{label} {content}".lower():
        score -= 5
    return score


def _balanced_option_candidates(answer: str, candidates: List[str], *, kind: str, limit: int = 3) -> List[str]:
    answer_length = _option_length_score(answer)
    unique: List[str] = []
    seen: set[str] = {str(answer or "").lower()}
    for item in candidates:
        clean = _compact_learning_text(item, char_limit=96, word_limit=20)
        if not clean or clean.lower() in seen:
            continue
        if kind == "formula" and not _looks_like_formula_text(clean):
            continue
        if kind == "formula_part" and not _looks_like_short_math_part(clean):
            continue
        if kind not in {"formula", "formula_part"} and _looks_like_formula_text(clean):
            continue
        seen.add(clean.lower())
        unique.append(clean)

    if kind in {"formula", "formula_part"}:
        return unique[:limit]

    def score(text: str) -> tuple[int, int]:
        length = _option_length_score(text)
        return (abs(length - answer_length), length)

    near = [
        text for text in unique
        if answer_length <= 0 or _option_length_score(text) >= max(8, int(answer_length * 0.45))
    ]
    return sorted(near or unique, key=score)[:limit]


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


def _generic_wrong_options(language: str, kind: str) -> List[str]:
    if kind == "formula":
        return ["\\Delta z = 0", "\\bar{w} = 1", "Cov(w,z) = 0", "E(z) = 0"]
    if kind == "formula_part":
        return ["\\bar{w}", "\\Delta z", "Cov(w,z)", "E(z)", "p_i"]
    if language == "en":
        return [
            "all individuals have the same fitness value",
            "the notation changes without biological meaning",
            "selection works without inherited variation",
            "the trait stays fixed across generations",
            "random drift fully determines the fitness change",
        ]
    return [
        "表示所有个体的适应性完全相同",
        "只是符号记法改变，没有生物学含义",
        "说明选择过程不需要遗传变异",
        "表示性状在代际之间保持不变",
        "认为变化完全由随机漂变决定",
    ]


def _fallback_balanced_distractors(answer: str, language: str, kind: str) -> List[str]:
    if kind == "formula":
        return _formula_distractors(answer) + _generic_wrong_options(language, "formula")
    if kind == "formula_part":
        return _generic_wrong_options(language, "formula_part")
    if language == "en":
        return [
            "treats the relation as random change only",
            "assumes all individuals have identical values",
            "removes the condition stated in the material",
            "confuses notation change with biological mechanism",
            "reverses the direction of the stated relation",
        ]
    return [
        "把该关系理解成完全随机变化",
        "认为所有个体的相关变量相同",
        "忽略材料中明确给出的条件",
        "把符号变化误当作机制变化",
        "颠倒了材料中说明的因果关系",
    ]


def _complete_option_set(answer: str, selected: List[str], *, language: str, kind: str) -> List[str]:
    result: List[str] = []
    seen: set[str] = {str(answer or "").lower()}
    for item in selected + _fallback_balanced_distractors(answer, language, kind):
        clean = _compact_learning_text(item, char_limit=96, word_limit=20)
        if not clean or clean.lower() in seen:
            continue
        if kind == "formula" and not _looks_like_formula_text(clean):
            continue
        if kind == "formula_part" and not _looks_like_short_math_part(clean):
            continue
        if kind not in {"formula", "formula_part"} and _is_pure_formula_text(clean):
            continue
        seen.add(clean.lower())
        result.append(clean)
        if len(result) >= 3:
            break
    return result


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
        if "？" in clean or "?" in clean or clean.startswith(("“", '"')):
            return
        if re.match(r"^(理解|掌握|能够|能夠|了解|熟悉|学会|学习).{4,80}$", clean):
            return
        if re.search(r"\[\[|see_formula|see_table", clean, flags=re.I):
            return
        if not re.search(
            r"[:：=<>Δ]|是|等于|需要|用于|控制|可以|进化|选择|方差|适应性|协方差|遗传|收益|成本|defined|means|equals|requires|controls|relates|fitness|variance|selection|evolution",
            clean,
            flags=re.I,
        ):
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


def _split_learning_sentences(value: Any) -> List[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_parts = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    sentences: List[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        clean = _clean_exercise_text(_strip_markdown_label(part), limit=320)
        if _is_mostly_english(clean):
            clean = _strip_english_discourse_prefix(clean)
        if len(clean) < 6:
            continue
        if _is_mostly_english(clean) and re.match(r"^(is there|what|which|why|how)\b", clean, flags=re.I):
            continue
        if re.search(r"\b(?:left|right)\)\s+the\b|\bfigure\s+\d+", clean, flags=re.I):
            continue
        if _is_teaching_scaffold_text(clean) or clean.lower() in seen:
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
    distractors: Optional[List[str]] = None,
) -> None:
    clean_question = _compact_question_text(question, char_limit=90, word_limit=32)
    clean_answer = _compact_learning_text(answer, char_limit=130, word_limit=28)
    if not clean_question or not clean_answer:
        return
    combined = f"{clean_question} {clean_answer}"
    if _is_teaching_scaffold_text(clean_question) or _is_teaching_scaffold_text(clean_answer):
        return
    if _is_bad_exercise_question(clean_question):
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
    item = {
        "_key": key,
        "question": clean_question,
        "answer": clean_answer,
        "source": source,
        "evidence_text": _compact_learning_text(evidence_text, char_limit=150, word_limit=32),
        "language": language,
        "kind": kind,
    }
    if distractors:
        item["distractors"] = distractors
    facts.append(item)


def _extract_english_facts(sentence: str, source: Dict[str, Any], facts: List[Dict[str, Any]], fallback_subject: str = "") -> None:
    if _is_teaching_scaffold_text(sentence):
        return
    sentence = _strip_english_discourse_prefix(sentence)
    formulas = _extract_formula_candidates(sentence)
    label = _compact_learning_text(source.get("label"), char_limit=54, word_limit=8)
    if formulas and _is_formula_source(source):
        subject = _exercise_focus(sentence, fallback_subject or label or "the concept")
        if not _is_generic_fact_label(subject):
            _add_exercise_fact(
                facts,
                question=f"Which formula defines {subject}?",
                answer=formulas[0],
                source=source,
                evidence_text=sentence,
                language="en",
                kind="formula",
                distractors=_formula_distractors(formulas[0]),
            )

    defined = re.search(r"^(.{2,80}?)\s+(?:is\s+defined\s+as|is)\s+(.+?)(?:\.|$)", sentence, flags=re.I)
    if defined:
        subject = _compact_learning_text(_strip_english_discourse_prefix(defined.group(1)), char_limit=54, word_limit=8)
        answer = _compact_learning_text(defined.group(2), char_limit=130, word_limit=28)
        if not _is_generic_fact_label(subject):
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
        subject = _compact_learning_text(_strip_english_discourse_prefix(re.sub(r"\bthen$", "", match.group(1).strip(), flags=re.I)), char_limit=54, word_limit=8)
        if subject.lower() in {"it", "this", "that", "they", "these", "those"}:
            subject = _compact_learning_text(fallback_subject, char_limit=54, word_limit=8) or _exercise_focus(sentence, "the concept")
        if _is_generic_fact_label(subject):
            continue
        obj = _compact_learning_text(match.group(2), char_limit=80, word_limit=16)
        extra = _compact_learning_text(match.group(3) if match.lastindex and match.lastindex >= 3 else "", char_limit=120, word_limit=24)
        answer = f"{obj} to {extra}" if "relates" in pattern and extra else (extra if "converts" in pattern else obj)
        question = direct_template.format(subject=re.sub(r"^(The|A|An)\b", lambda m: m.group(1).lower(), subject), object=obj)
        _add_exercise_fact(facts, question=question, answer=answer, source=source, evidence_text=sentence, language="en", kind="relation")
        if extra and extra_template:
            _add_exercise_fact(facts, question=extra_template.format(subject=subject, object=obj), answer=extra, source=source, evidence_text=sentence, language="en", kind="relation")


def _extract_chinese_facts(sentence: str, source: Dict[str, Any], facts: List[Dict[str, Any]]) -> None:
    if _is_teaching_scaffold_text(sentence):
        return
    formulas = _extract_formula_candidates(sentence)
    if formulas and _is_formula_source(source):
        subject = _exercise_focus(sentence, source.get("label") or "该概念")
        if not _is_generic_fact_label(subject):
            _add_exercise_fact(
                facts,
                question=f"材料中“{subject}”的公式是什么？",
                answer=formulas[0],
                source=source,
                evidence_text=sentence,
                language="zh",
                kind="formula",
                distractors=_formula_distractors(formulas[0]),
            )

    colon = re.search(r"^([^：:]{2,40})[：:]\s*(.+)$", sentence)
    if colon:
        subject = _compact_learning_text(colon.group(1), char_limit=36, word_limit=8)
        answer = _compact_learning_text(colon.group(2), char_limit=130, word_limit=28)
        source_label = _compact_learning_text(source.get("label") or "", char_limit=36, word_limit=8)
        if _is_generic_fact_label(subject) and source_label and not _is_generic_fact_label(source_label):
            subject = source_label
        if not _is_generic_fact_label(subject):
            question = f"材料中“{subject}”表达了什么关系？" if (_extract_formula_candidates(answer) or re.search(r"[=><]|Δ|Cov|E\(", answer)) else f"材料中“{subject}”的表述是什么？"
            _add_exercise_fact(facts, question=question, answer=answer, source=source, evidence_text=sentence, language="zh", kind="definition")
            return

    through = re.search(r"^(.{1,42}?)通过(.+?)(?:来(.+?))?(?:。|$)", sentence)
    if through:
        subject = _compact_learning_text(through.group(1), char_limit=36, word_limit=8)
        method = _compact_learning_text(through.group(2), char_limit=120, word_limit=24)
        purpose = _compact_learning_text(through.group(3) or "", char_limit=120, word_limit=24)
        _add_exercise_fact(facts, question=f"材料中“{subject}”主要通过什么方式起作用？", answer=method, source=source, evidence_text=sentence, language="zh", kind="relation")
        if purpose:
            _add_exercise_fact(facts, question=f"材料中“{subject}”这样做的目的是什么？", answer=purpose, source=source, evidence_text=sentence, language="zh", kind="relation")

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
        if not _is_generic_fact_label(subject):
            _add_exercise_fact(facts, question=template.format(subject=subject), answer=answer, source=source, evidence_text=sentence, language="zh", kind="relation")


def _chapter_template_facts(chapter_title: str, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    haystack = " ".join(
        [
            str(chapter_title or ""),
            *(str(item.get("label") or "") + " " + str(item.get("content") or "") for item in sources[:12] if isinstance(item, dict)),
        ]
    ).lower()
    if not re.search(r"natural selection|自然选择|hamilton|fisher|price equation|robertson|price|selection|fitness|variance", haystack):
        return []
    source = next((item for item in sources if isinstance(item, dict)), {})

    def fact(question: str, answer: str, distractors: List[str], evidence_text: str) -> Dict[str, Any]:
        return {
            "_key": f"{question}\n{answer}".lower(),
            "question": question,
            "answer": answer,
            "distractors": distractors,
            "source": source,
            "evidence_text": evidence_text,
            "language": "zh",
            "kind": "conceptual",
        }

    return [
        fact("如果种群中的适应性方差更大，费希尔基本定理意味着什么？", "平均适应性上升的潜力更大。", ["适应性方差会阻止平均适应性变化。", "遗传变异变得无关紧要。", "定理只描述随机漂变的速度。"], "Fisher's theorem relates change in mean fitness to additive genetic variance in fitness."),
        fact("价格方程把性状的进化变化拆分为哪两类来源？", "选择造成的协方差项，以及传递偏差项。", ["突变率项，以及样本数量修正项。", "随机漂变项，以及环境温度项。", "亲缘系数项，以及群体大小项。"], "The Price equation decomposes evolutionary change into selection and transmission components."),
        fact("Robertson-Price identity 中，选择差通常由哪种关系刻画？", "trait 与 fitness 之间的 covariance。", ["trait 与章节标题之间的字符串相似度。", "fitness 与页面格式之间的排版关系。", "offspring count 与文件名之间的关系。"], "Robertson-Price identity expresses selection with covariance between trait and fitness."),
        fact("为什么 variance 是自然选择定理中的关键量？", "它表示个体差异，选择需要可区分的变异。", ["它保证所有个体没有任何差异。", "它把所有选择效应都变成随机噪声。", "它只表示公式编号发生变化。"], "Selection requires variation; variance summarizes differences among individuals."),
        fact("parent-offspring regression 在选择前后为什么可能变化？", "selection 会改变配偶或基因型组合的分布。", ["selection 不会改变任何群体分布。", "regression 只由章节标题决定。", "offspring phenotype 与 parent phenotype 永远无关。"], "Parent-offspring regression can change after selection because the population composition changes."),
    ]


def _conceptual_fact_variants(facts: List[Dict[str, Any]], target_count: int) -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = []
    used_questions: set[str] = set()

    def add_variant(base: Dict[str, Any], question: str, answer: str, distractors: Optional[List[str]] = None) -> None:
        clean_question = _compact_question_text(question, char_limit=90, word_limit=32)
        clean_answer = _compact_learning_text(answer, char_limit=96, word_limit=20)
        if not clean_question or not clean_answer or clean_question.lower() in used_questions:
            return
        used_questions.add(clean_question.lower())
        item = dict(base)
        item["question"] = clean_question
        item["answer"] = clean_answer
        item["kind"] = "conceptual"
        if distractors:
            item["distractors"] = [_compact_learning_text(option, char_limit=96, word_limit=20) for option in distractors if _compact_learning_text(option, char_limit=96, word_limit=20)]
        variants.append(item)

    for fact in facts:
        combined = f"{fact.get('question') or ''} {fact.get('answer') or ''}".lower()
        question_text = str(fact.get("question") or "")
        answer_text = str(fact.get("answer") or "")
        if "费希尔" in question_text or "fisher" in combined:
            add_variant(fact, "如果种群中的适应性方差更大，费希尔基本定理意味着什么？", "平均适应性上升的潜力更大。", ["适应性方差会阻止平均适应性变化。", "遗传变异变得无关紧要。", "定理只描述随机漂变的速度。"])
        elif "价格方程" in question_text or "price equation" in combined:
            add_variant(fact, "价格方程把性状的进化变化拆分为哪两类来源？", "选择造成的协方差项，以及传递偏差项。", ["突变率项，以及样本数量修正项。", "随机漂变项，以及环境温度项。", "亲缘系数项，以及群体大小项。"])
        elif "自然选择" in question_text and "变异" in answer_text:
            add_variant(fact, "为什么没有变异时自然选择难以产生进化改变？", "缺少可被选择区分的性状差异。", ["选择会直接创造新的遗传差异。", "所有个体会自动产生相同后代。", "适应性差异会被方差完全抵消。"])
        elif "方差" in question_text:
            add_variant(fact, "在本章语境下，方差为什么重要？", "它提供可被选择区分的个体差异。", ["它保证所有个体适应性完全相同。", "它只表示符号单位的变化。", "它会让遗传变异不再影响选择。"])

    for fact in facts:
        question = _friendly_fact_question(fact)
        key = question.lower()
        if key in used_questions:
            continue
        used_questions.add(key)
        item = dict(fact)
        item["question"] = question
        variants.append(item)
        if len(variants) >= max(target_count, 8):
            break

    return variants[:target_count]


def _extract_exercise_facts(source_evidence: List[Dict[str, Any]], target_count: int, chapter_title: str = "") -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    template_facts = _chapter_template_facts(chapter_title, source_evidence)
    scan_limit = max(target_count * 4, 16)
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
            if len(facts) >= scan_limit:
                break
        if len(facts) >= scan_limit:
            break

    concept_facts = [
        fact for fact in facts
        if str(fact.get("kind") or "").lower() not in {"formula", "formula_part"}
        and not _is_bad_exercise_question(fact.get("question"))
    ]
    return _conceptual_fact_variants(template_facts + concept_facts, target_count)


def _build_fact_options(fact: Dict[str, Any], facts: List[Dict[str, Any]], exercise_index: int) -> tuple[List[str], str]:
    answer = _compact_learning_text(fact.get("answer"), char_limit=96, word_limit=20)
    language = fact.get("language") or "zh"
    kind = fact.get("kind") or "concept"
    priority_candidates: List[str] = []
    secondary_candidates: List[str] = []

    if kind == "formula":
        priority_candidates.extend(_formula_distractors(answer))
    specific_distractors = fact.get("distractors")
    if isinstance(specific_distractors, list):
        priority_candidates.extend(str(item) for item in specific_distractors)

    other_answers: List[str] = []
    for other in facts:
        other_kind = str(other.get("kind") or "concept")
        other_answer = _compact_learning_text(other.get("answer"), char_limit=96, word_limit=20)
        if not other_answer or other_answer.lower() == answer.lower():
            continue
        if kind == "formula" and not _looks_like_formula_text(other_answer):
            continue
        if kind == "formula_part" and not _looks_like_short_math_part(other_answer):
            continue
        if kind not in {"formula", "formula_part"} and other_kind in {"formula", "formula_part"}:
            continue
        other_answers.append(other_answer)

    if other_answers:
        rotation = (exercise_index - 1) % len(other_answers)
        secondary_candidates.extend(other_answers[rotation:] + other_answers[:rotation])
    secondary_candidates.extend(_generic_wrong_options(language, kind))

    selected = _balanced_option_candidates(answer, priority_candidates, kind=kind, limit=3)
    if len(selected) < 3:
        selected_seen = {answer.lower(), *(item.lower() for item in selected)}
        selected.extend(
            item
            for item in _balanced_option_candidates(answer, secondary_candidates, kind=kind, limit=6)
            if item.lower() not in selected_seen
        )
        selected = selected[:3]
    selected = _complete_option_set(answer, selected, language=language, kind=kind)
    unique: List[str] = [answer] + selected
    if len(unique) < 4:
        raise ValueError("题库生成失败：没有足够的有效选项")
    correct_slot = (exercise_index - 1) % 4
    correct_text = unique.pop(0)
    unique.insert(correct_slot, correct_text)
    letters = ["A", "B", "C", "D"]
    return [f"{letters[index]}. {_latex_option_text(text)}" for index, text in enumerate(unique[:4])], letters[correct_slot]


def _friendly_fact_question(fact: Dict[str, Any]) -> str:
    question = _compact_question_text(fact.get("question"), char_limit=90, word_limit=32)
    answer = _compact_learning_text(fact.get("answer"), char_limit=130, word_limit=28)
    language = fact.get("language") or "zh"
    kind = str(fact.get("kind") or "concept").lower()
    subject_match = re.search(r"[“\"]([^”\"]{2,60})[”\"]", question)
    subject = _compact_learning_text(subject_match.group(1) if subject_match else "", char_limit=44, word_limit=8)
    if language == "en":
        if subject and kind == "relation":
            return f"What role does {subject} play in the chapter's argument?"
        if subject:
            return f"Which option best explains {subject}?"
        return question
    if subject:
        if kind == "relation" or re.search(r"需要|控制|用于|解释|导致|通过", question):
            if "需要" in question:
                return f"为什么“{subject}”是该选择过程中的关键条件？"
            return f"下列哪项最准确说明“{subject}”在本章中的作用？"
        if re.search(r"[=<>≤≥]|适应性方差|选择效应|传递偏差|关系", answer):
            return f"下列哪项最准确概括“{subject}”表达的关系？"
        return f"关于“{subject}”，哪项说法最准确？"
    return question


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
    evidence_text = fact.get("evidence_text") or fact.get("answer") or ""
    return {
        "id": f"ex_{re.sub(r'[^a-zA-Z0-9_-]+', '_', chapter_id or 'chapter')}_{exercise_index}",
        "question": _friendly_fact_question(fact) or "下列哪项正确？",
        "options": options,
        "correct_answer": correct_answer,
        "explanation": f"答案依据材料：“{evidence_text}”。",
        "source_evidence": evidence,
        "learning_plan": plan,
    }


def _exercise_distractor_pool(sources: List[Dict[str, Any]], current_index: int, chapter_title: str) -> List[str]:
    pool: List[str] = []
    language = _exercise_language(chapter_title, " ".join(str(item.get("content") or "") for item in sources[:3]))
    for index, item in enumerate(sources):
        if index == current_index:
            continue
        raw = _clean_exercise_text(item.get("content") or item.get("label"), limit=240)
        _, answer, _ = _derive_question_and_answer(raw, chapter_title=chapter_title, label=str(item.get("label") or ""), language=language, exercise_index=index + 1)
        content = _compact_learning_text(answer or raw, char_limit=112, word_limit=22)
        if content:
            pool.append(content)
    pool.extend(_generic_wrong_options(language, "concept"))
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
    formula_source = _is_formula_source({"label": label, "content": raw_content, "type": ""})
    if formulas and formula_source and not _is_generic_fact_label(focus):
        formula = formulas[(exercise_index - 1) % len(formulas)]
        if language == "en":
            return f"Which formula is stated for {focus}?", formula, _formula_distractors(formula)
        return f"材料中给出的“{focus}”公式是什么？", formula, _formula_distractors(formula)

    text = _clean_exercise_text(raw_content, limit=260)
    if language == "en":
        text = _strip_english_discourse_prefix(text)
        for pattern, template in [
            (r"^(.{2,80}?)\s+controls\s+(.+?)(?:\.|$)", "What does {subject} control?"),
            (r"^(.{2,80}?)\s+is\s+(.+?)(?:\.|$)", "What is {subject}?"),
            (r"^(.{2,80}?)\s+means\s+(.+?)(?:\.|$)", "What does {subject} mean?"),
        ]:
            match = re.search(pattern, text, flags=re.I)
            if match:
                subject = _compact_learning_text(match.group(1), char_limit=48, word_limit=8)
                answer = _compact_learning_text(match.group(2), char_limit=120, word_limit=24)
                if subject and answer:
                    return template.format(subject=subject), answer, []
        if _is_generic_fact_label(focus):
            focus = _compact_learning_text(label or chapter_title, char_limit=48, word_limit=8)
        return f"What does the material say about {focus}?", _compact_learning_text(text, char_limit=96, word_limit=20), []

    for pattern, template in [
        (r"^(.{1,40}?)控制(.+?)(?:。|$)", "材料中“{subject}”控制什么？"),
        (r"^(.{1,40}?)用于(.+?)(?:。|$)", "材料中“{subject}”用于什么？"),
        (r"^(.{1,40}?)是(.+?)(?:。|$)", "材料中“{subject}”是什么？"),
    ]:
        match = re.search(pattern, text)
        if match:
            subject = _compact_learning_text(match.group(1), char_limit=32, word_limit=8)
            answer = _compact_learning_text(match.group(2), char_limit=120, word_limit=24)
            if subject and answer:
                return template.format(subject=subject), answer, []
    return f"材料中关于“{focus}”的核心说法是什么？", _compact_learning_text(text, char_limit=120, word_limit=24), []


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
    question, correct_text, specific_distractors = _derive_question_and_answer(raw_content, chapter_title=chapter_title, label=label, language=language, exercise_index=exercise_index)
    distractors = _exercise_distractor_pool(all_sources, source_index, chapter_title)
    correct_text = _compact_learning_text(correct_text or content, char_limit=96, word_limit=20)
    options = [correct_text]
    is_formula_question = _looks_like_formula_text(options[0]) and re.search(r"formula|equation|公式", question, flags=re.I)
    extra_kind = "formula" if is_formula_question else "concept"
    options.extend(_balanced_option_candidates(correct_text, specific_distractors + distractors + _generic_wrong_options(language, extra_kind), kind=extra_kind, limit=3))
    options = _complete_option_set(correct_text, options[1:], language=language, kind=extra_kind)
    options = [correct_text] + options
    if len(options) < 4:
        raise ValueError("题库生成失败：没有足够的有效选项")
    correct_slot = (exercise_index - 1) % 4
    correct_option = options.pop(0)
    options.insert(correct_slot, correct_option)
    letters = ["A", "B", "C", "D"]
    formatted_options = [f"{letters[index]}. {_latex_option_text(text)}" for index, text in enumerate(options[:4])]
    plan = build_learning_plan(query=chapter_title or label, evidence=[source], learner_intent="practice", task="practice", chapter_data={"id": chapter_id, "title": chapter_title, "content": chapter_content})
    return {
        "id": f"ex_{re.sub(r'[^a-zA-Z0-9_-]+', '_', chapter_id or 'chapter')}_{exercise_index}",
        "question": _compact_question_text(question),
        "options": formatted_options,
        "correct_answer": letters[correct_slot],
        "explanation": f"正确选项对应原文要点：“{content}”。",
        "source_evidence": [source],
        "learning_plan": plan,
    }


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

    normalized_sources: List[Dict[str, Any]] = []
    for index, item in enumerate(source_evidence, start=1):
        if not isinstance(item, dict):
            continue
        content = _compact_learning_text(item.get("content") or item.get("label"), char_limit=120, word_limit=24)
        if not content:
            continue
        if _is_teaching_scaffold_text(content) or re.search(r"\[\[|see_formula|see_table", content, flags=re.I):
            continue
        if _is_generic_fact_label(content):
            continue
        normalized = dict(item)
        normalized["index"] = normalized.get("index") or index
        normalized["label"] = _compact_learning_text(normalized.get("label") or chapter_title or f"知识点 {index}", char_limit=48, word_limit=8)
        normalized["content"] = content
        normalized.setdefault("source", "graph")
        normalized_sources.append(normalized)

    if not normalized_sources:
        raise ValueError("题库生成失败：没有可用于组题的有效知识点")
    normalized_sources.sort(key=_source_quality_score, reverse=True)
    non_formula_sources = [source for source in normalized_sources if not _is_formula_source(source)]
    if non_formula_sources:
        normalized_sources = non_formula_sources + [source for source in normalized_sources if _is_formula_source(source)]

    facts = _extract_exercise_facts(normalized_sources, max(target_count * 2, 8), chapter_title)
    bank: List[Dict[str, Any]] = []
    if facts:
        seen_option_sets: List[set[str]] = []
        for index, fact in enumerate(facts, start=1):
            try:
                exercise = _build_fact_choice_exercise(
                    chapter_id=chapter_id,
                    chapter_title=chapter_title,
                    chapter_content=chapter_content,
                    fact=fact,
                    facts=facts,
                    exercise_index=index,
                )
            except ValueError:
                continue
            option_tokens = _exercise_option_token_set(exercise)
            if not _is_placeholder_exercise(exercise, exercise.get("question") or "", exercise.get("options") or []) and not _is_low_quality_exercise(exercise) and not _has_reused_option_set(option_tokens, seen_option_sets):
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
        try:
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
            if not _is_low_quality_exercise(exercise) and not _has_reused_option_set(option_tokens, seen_option_sets):
                bank.append(exercise)
                if option_tokens:
                    seen_option_sets.append(option_tokens)
        except ValueError:
            pass
        attempts += 1
    if not bank:
        raise ValueError("题库生成失败：没有生成可读且有效的练习题")
    return bank[:target_count]


def _build_local_exercise_response(
    request: GenerateExercisesRequest,
    *,
    graph_data: Optional[Dict[str, Any]] = None,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    from KGTS.core.bridge import chapter_store
    from KGTS.education.qa_helpers import _safe_consistency_report

    chapter_content = expand_formula_references(request.chapter_content)
    chapter_payload = {
        "id": request.chapter_id,
        "title": request.chapter_title,
        "content": chapter_content,
    }
    if isinstance(graph_data, dict):
        chapter_payload["graph_data"] = graph_data

    evidence = _get_exercise_evidence(request.chapter_id, chapter_payload)
    target_count = _target_exercise_count(request.count)
    existing_chapter = chapter_store.get_chapter(request.chapter_id)
    feedback = _exercise_feedback_map(existing_chapter)
    approved_bank = _filter_downvoted_exercises(
        _normalize_exercise_bank((existing_chapter or {}).get("approved_exercise_bank")),
        feedback,
    )
    generation_count = min(10, max(target_count * 2, target_count + _exercise_feedback_summary(feedback)["exercise_down"]))
    exercise_bank = _filter_downvoted_exercises(
        _build_local_exercise_bank(
            chapter_id=request.chapter_id,
            chapter_title=request.chapter_title,
            chapter_content=chapter_content,
            evidence=evidence,
            count=generation_count,
        ),
        feedback,
    )
    pinned_bank = [
        item
        for item in _normalize_exercise_bank((existing_chapter or {}).get("exercise_bank") or (existing_chapter or {}).get("exercises") if existing_chapter else [])
        if str((_exercise_feedback_for_item(item, feedback) or {}).get("rating") or "").lower() == "up"
    ]
    if approved_bank:
        pinned_bank = _merge_exercise_banks(approved_bank, pinned_bank, target_count)
    if pinned_bank:
        exercise_bank = _merge_exercise_banks(pinned_bank, exercise_bank, target_count)
    if not exercise_bank:
        exercise_bank = _filter_downvoted_exercises(
            _normalize_exercise_bank(existing_chapter.get("exercise_bank") or existing_chapter.get("exercises") if existing_chapter else []),
            feedback,
        )
    if not exercise_bank:
        raise ValueError("No exercises remain after teacher feedback filtering")
    if len(exercise_bank) < target_count and generation_count < 10:
        expanded_bank = _filter_downvoted_exercises(
            _build_local_exercise_bank(
                chapter_id=request.chapter_id,
                chapter_title=request.chapter_title,
                chapter_content=chapter_content,
                evidence=evidence,
                count=10,
            ),
            feedback,
        )
        exercise_bank = _merge_exercise_banks(exercise_bank, expanded_bank, target_count)
    if len(exercise_bank) < target_count:
        warning = (warning + " " if warning else "") + f"Only {len(exercise_bank)} / {target_count} usable exercises remain after teacher feedback filtering."
    saved_chapter = chapter_store.save_exercise_bank(
        chapter_id=request.chapter_id,
        exercises=exercise_bank,
    )
    response_bank = exercise_bank[:target_count] if len(exercise_bank) > target_count else exercise_bank
    first_exercise = response_bank[0]
    learning_plan = first_exercise.get("learning_plan") or build_learning_plan(
        query=request.chapter_title or request.chapter_id,
        evidence=evidence,
        task="practice",
        chapter_data=chapter_payload,
    )
    payload = {
        "success": True,
        "exercise": first_exercise,
        "exercise_bank": response_bank,
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


def _target_exercise_count(count: int = 5) -> int:
    return max(3, min(max(int(count or 5), 1), 10))


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


async def _generate_replacement_option_text(
    *,
    request: TeacherRegenerateOptionRequest,
    exercise: Dict[str, Any],
    option_index: int,
    option_text: str,
    chapter: Dict[str, Any],
    forbidden_options: Optional[List[str]] = None,
) -> tuple[str, str]:
    options = _format_options(_normalize_exercise_options(exercise.get("options")))
    correct_answer = _normalize_correct_answer(request.correct_answer or exercise.get("correct_answer") or exercise.get("answer"))
    option_key = chr(65 + option_index)
    is_correct = option_key == correct_answer
    existing_options = "\n".join(options)
    forbidden_text = "\n".join(
        "- " + _strip_option_letter(option)
        for option in (forbidden_options or [])
        if _strip_option_letter(option)
    )
    chapter_context = _compact_learning_text(
        (chapter or {}).get("content") or (chapter or {}).get("lecture_content") or "",
        char_limit=900,
        word_limit=160,
    )
    prompt = f"""
请只重写一道选择题中的一个选项，保持题干、正确答案字母和其它选项不变。

题干：
{exercise.get("question") or request.question or ""}

当前四个选项：
{existing_options}

需要替换的选项：{option_key}. {_strip_option_letter(option_text)}
正确答案字母：{correct_answer or "未标注"}
该选项是否为正确选项：{"是" if is_correct else "否"}

章节上下文：
{chapter_context}

要求：
1. 只输出新的 {option_key} 选项文本，不要输出 A./B./C./D. 前缀。
2. 如果被替换的是错误选项，新选项必须仍然是错误但合理的干扰项，不能和正确答案等价。
3. 如果被替换的是正确选项，只改写表达方式，不改变其正确含义。
4. 新选项要和其它选项长度、风格、类型接近；公式题就给公式型选项。
5. 不要复用当前四个选项中的任何一个。
6. 也不要使用下面这些同题历史坏选项或已生成替换项：
{forbidden_text or "- 无"}
7. 返回合法 JSON：{{"option":"新选项文本"}}
"""
    try:
        client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=request.model or get_deepseek_model("pro"),
        )
        response = await client._call_deepseek(
            prompt,
            max_tokens=500,
            system_prompt="You rewrite exactly one multiple-choice option. Return compact valid JSON only.",
            read_timeout_seconds=45.0,
        )
        payload = json.loads(_extract_json_object_text(response))
        candidate = _strip_option_letter(payload.get("option") if isinstance(payload, dict) else "")
        source = "deepseek"
    except Exception:
        candidate = _local_replacement_option(
            question=str(exercise.get("question") or request.question or ""),
            old_option=option_text,
            options=options,
            correct_answer=correct_answer,
            option_key=option_key,
            forbidden_options=forbidden_options,
        )
        source = "local"
    return candidate, source


def _normalize_correct_answer(value: Any) -> str:
    if isinstance(value, int):
        return chr(65 + value) if 0 <= value < 26 else str(value)
    text = str(value or "").strip()
    if not text:
        return ""
    match = text[:1].upper()
    return match if "A" <= match <= "Z" else text


def _local_replacement_option(
    *,
    question: str,
    old_option: str,
    options: List[str],
    correct_answer: str,
    option_key: str,
    forbidden_options: Optional[List[str]] = None,
) -> str:
    clean = _strip_option_letter(old_option)
    if _looks_like_formula_text(clean):
        distractors = _formula_distractors(clean)
        forbidden = {_option_compare_key(o) for o in (forbidden_options or [])}
        for d in distractors:
            if _option_compare_key(d) not in forbidden:
                return d
    return f"Alternative option for {clean[:30]}"


def _option_compare_key(value: Any) -> str:
    return _compact_learning_text(_strip_option_letter(value), char_limit=130, word_limit=28).lower()


def _find_exercise_for_feedback(
    bank: List[Dict[str, Any]],
    exercise_id: str,
    question: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    from KGTS.education.exercise_text_utils import _compact_question_text

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


def _exercise_signature(exercise: Dict[str, Any]) -> str:
    from KGTS.education.exercise_text_utils import _compact_question_text, _normalize_exercise_options, _strip_option_letter
    import hashlib

    question = _compact_question_text(str((exercise or {}).get("question") or ""))
    options = _normalize_exercise_options((exercise or {}).get("options"))
    option_stubs = [_strip_option_letter(o)[:40].lower() for o in options[:4]]
    return hashlib.md5((question + "||" + "||".join(option_stubs)).encode()).hexdigest()[:12]
