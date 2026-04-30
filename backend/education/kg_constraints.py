"""Knowledge-graph constraints for teaching generation.

This module adapts the GC-DPG idea in GC-DPG参考.md into a generic
KG-constrained learning pipeline:
1. build a LearningPlan from graph evidence,
2. generate only within the LearningPlan,
3. attach a lightweight consistency report.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence


KG_CONSTRAINED_SYSTEM_PROMPT = """你是一个受知识图谱约束的交互式学习助手。
必须先依据 LearningPlan 和图谱证据组织答案，再生成教学内容。
只能使用 LearningPlan 中允许的知识点、关系和证据；不要编造图谱中不存在的概念关系。
如果图谱证据不足，必须明确说明“当前图谱依据不足”，并指出还需要哪些知识证据。
如果学习者正在练习或请求提示，优先给提示和思路，不要一次性泄露完整答案。
输出要符合学习者当前水平，避免跳到未掌握的高级内容。"""


DEFAULT_CONSTRAINTS = [
    "只能使用 LearningPlan.allowed_concepts、LearningPlan.learning_intent_graph 和 evidence 中出现的知识。",
    "不要引入未被图谱证据支持的新概念、前置关系、因果关系或结论。",
    "如果证据不足，说明当前图谱依据不足，不要用常识补全。",
    "根据 learning_level 控制难度，初学者回答优先解释前置知识和关键定义。",
    "练习、批改和提示场景优先给分步提示，除非题目明确要求公布标准答案。",
]


INTENT_KEYWORDS = [
    ("feedback", ("批改", "评价", "判断", "答案", "得分", "哪里错", "对不对")),
    ("hint", ("提示", "hint", "思路", "下一步")),
    ("practice", ("练习", "习题", "做题", "题目", "practice")),
    ("quiz", ("测验", "quiz", "选择题", "填空题", "简答题")),
    ("example", ("例子", "举例", "example")),
    ("next_step", ("下一步", "推荐", "学习路径", "复习")),
    ("explain", ("解释", "讲解", "什么是", "为什么", "如何理解")),
]


SUPPORTED_RELATION_TYPES = {
    "contains",
    "related",
    "precedes",
    "prerequisite_of",
    "depends_on",
    "example_of",
    "exercise_of",
    "misconception_of",
}


def infer_learner_intent(text: str, default: str = "explain") -> str:
    normalized = (text or "").lower()
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword.lower() in normalized for keyword in keywords):
            return intent
    return default


def evidence_from_rag(items: Sequence[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    return [
        _normalize_evidence_item(item, index=index, default_source="retrieval")
        for index, item in enumerate(items[:limit], start=1)
    ]


def evidence_from_graph(
    graph_data: Optional[Dict[str, Any]],
    *,
    query: str = "",
    chapter_data: Optional[Dict[str, Any]] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not graph_data:
        return []

    nodes = graph_data.get("nodes") or []
    if not isinstance(nodes, list):
        return []

    query_text = " ".join(
        part
        for part in [
            query,
            str((chapter_data or {}).get("title") or ""),
            str((chapter_data or {}).get("content") or "")[:1200],
        ]
        if part
    )
    tokens = _tokenize(query_text)

    scored_nodes = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        label = _node_label(node)
        content = _node_content(node)
        node_text = f"{label} {content} {json.dumps(node.get('metadata') or {}, ensure_ascii=False)}"
        score = _overlap_score(tokens, node_text)
        if chapter_data and label and label in str(chapter_data.get("title") or ""):
            score += 5
        scored_nodes.append((score, index, node))

    scored_nodes.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    if tokens and any(score > 0 for score, _, _ in scored_nodes):
        selected = [node for score, _, node in scored_nodes if score > 0][:limit]
    else:
        selected = [node for _, _, node in scored_nodes[:limit]]

    return [
        _normalize_evidence_item(node, index=index, default_source="graph")
        for index, node in enumerate(selected, start=1)
    ]


def relation_evidence_from_graph(
    graph_data: Optional[Dict[str, Any]],
    evidence: Sequence[Dict[str, Any]],
    limit: int = 12,
) -> List[Dict[str, Any]]:
    if not graph_data or not evidence:
        return []

    relations = graph_data.get("relations") or graph_data.get("edges") or []
    if not isinstance(relations, list):
        return []

    evidence_ids = {str(item.get("id") or "") for item in evidence if item.get("id")}
    result: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for relation in relations:
        if not isinstance(relation, dict):
            continue
        source = str(relation.get("source_id") or relation.get("source") or relation.get("from") or "")
        target = str(relation.get("target_id") or relation.get("target") or relation.get("to") or "")
        relation_type = str(
            relation.get("relation_type") or relation.get("type") or relation.get("label") or "related"
        )
        if evidence_ids and source not in evidence_ids and target not in evidence_ids:
            continue
        if relation_type not in SUPPORTED_RELATION_TYPES and not relation_type:
            continue
        key = f"{source}:{relation_type}:{target}"
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "source": source,
                "target": target,
                "type": relation_type,
                "metadata": relation.get("metadata") or relation.get("properties") or {},
            }
        )
        if len(result) >= limit:
            break
    return result


def build_learning_plan(
    *,
    query: str,
    evidence: Sequence[Dict[str, Any]],
    relations: Optional[Sequence[Dict[str, Any]]] = None,
    learner_intent: Optional[str] = None,
    learning_level: str = "beginner",
    task: str = "qa",
    chapter_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_evidence = [
        _normalize_evidence_item(item, index=index, default_source="graph")
        for index, item in enumerate(evidence, start=1)
    ]
    allowed = _allowed_concepts(normalized_evidence)
    primary = allowed[0] if allowed else {}
    subject_name = (
        str((chapter_data or {}).get("title") or "").strip()
        or str(primary.get("name") or "").strip()
        or "未匹配到图谱主题"
    )
    subject_id = str((chapter_data or {}).get("id") or primary.get("id") or "").strip()
    intent = learner_intent or infer_learner_intent(query, default=_default_intent_for_task(task))
    learning_relations = list(relations or [])

    return {
        "subject": {
            "id": subject_id,
            "name": subject_name,
            "type": str(primary.get("type") or "topic"),
            "match_score": 1.0 if allowed else 0.0,
        },
        "learner_intent": intent,
        "learning_level": learning_level,
        "task": task,
        "allowed_concepts": allowed,
        "slots": _build_slots(normalized_evidence, learning_relations),
        "learning_intent_graph": {
            "nodes": [item["name"] for item in allowed],
            "edges": [
                {
                    "from": relation.get("source"),
                    "to": relation.get("target"),
                    "type": relation.get("type") or "related",
                }
                for relation in learning_relations
            ],
        },
        "evidence": normalized_evidence,
        "constraints": DEFAULT_CONSTRAINTS,
    }


def format_learning_plan(plan: Dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2)


def format_evidence(evidence: Sequence[Dict[str, Any]]) -> str:
    if not evidence:
        return "无可用图谱证据。"
    lines = []
    for item in evidence:
        source = item.get("source") or "graph"
        label = item.get("label") or item.get("id") or "context"
        node_type = item.get("type") or "context"
        content = _clip(str(item.get("content") or ""), 700)
        lines.append(f"[{item.get('index', '?')}] ({source}/{node_type}) {label}: {content}")
    return "\n".join(lines)


def build_constrained_generation_prompt(
    *,
    task_title: str,
    user_input: str,
    learning_plan: Dict[str, Any],
    requirements: Iterable[str],
    source_content: str = "",
) -> str:
    requirement_text = "\n".join(f"{index}. {item}" for index, item in enumerate(requirements, start=1))
    source_block = f"\n原始输入/章节内容：\n{source_content.strip()}\n" if source_content.strip() else ""
    return f"""请执行 KG-Constrained Interactive Learning Pipeline。

Phase 1: Learning Planning 已完成，必须遵守以下 LearningPlan：
{format_learning_plan(learning_plan)}

Phase 2: Constrained Teaching / Interaction Generation
任务：{task_title}
学习者输入：{user_input}
{source_block}
可用图谱证据：
{format_evidence(learning_plan.get("evidence") or [])}

生成要求：
{requirement_text}

Phase 3: Consistency & Pedagogy Checking
生成前自检：
- 是否只使用了 LearningPlan 中允许的知识点和关系。
- 是否避免了未授权的新概念和高级跳跃。
- 如果证据不足，是否明确说明“当前图谱依据不足”。
- 练习/批改/提示场景是否没有无条件泄露完整答案。

只输出最终内容，不要输出自检过程。"""


def check_generation_consistency(
    output: str,
    learning_plan: Dict[str, Any],
    *,
    task: str = "qa",
) -> Dict[str, Any]:
    evidence = learning_plan.get("evidence") or []
    allowed = learning_plan.get("allowed_concepts") or []
    output_text = output or ""
    output_lower = output_text.lower()

    matched = 0
    for concept in allowed:
        label = str(concept.get("name") or "").strip()
        if label and label.lower() in output_lower:
            matched += 1

    evidence_count = len(evidence)
    support_ratio = 0.0
    if evidence_count:
        support_ratio = matched / max(1, min(len(allowed), evidence_count))
        if matched == 0 and output_text.strip():
            support_ratio = 0.5

    insufficiency_acknowledged = "当前图谱依据不足" in output_text or "图谱依据不足" in output_text
    hint_policy_violated = (
        (learning_plan.get("learner_intent") in {"hint", "practice", "feedback"} or task in {"hint", "practice", "feedback"})
        and ("正确答案" in output_text or "标准答案" in output_text)
        and "除非" not in output_text
    )
    warnings: List[str] = []
    if not evidence_count and not insufficiency_acknowledged:
        warnings.append("输出没有可用图谱证据支撑，应该说明当前图谱依据不足。")
    if hint_policy_violated:
        warnings.append("练习/提示场景可能直接泄露完整答案。")

    is_safe = bool(output_text.strip()) and not hint_policy_violated
    if not evidence_count:
        is_safe = insufficiency_acknowledged

    return {
        "knowledge_support_ratio": round(min(1.0, support_ratio), 3),
        "unsupported_concept_rate": 0.0 if evidence_count else 1.0,
        "learning_goal_alignment": 1.0 if output_text.strip() else 0.0,
        "difficulty_match": "appropriate",
        "hint_policy_violated": hint_policy_violated,
        "is_safe_to_show": is_safe,
        "warnings": warnings,
    }


def build_kg_grounded_exercise(
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_content: str = "",
    evidence: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized = [
        _normalize_evidence_item(item, index=index, default_source="graph")
        for index, item in enumerate(evidence, start=1)
    ]
    if not normalized:
        return {
            "id": f"ex_{_safe_id(chapter_id)}_kg_gap",
            "question": f"当前图谱是否有足够证据为《{chapter_title or chapter_id}》生成可靠练习？",
            "options": [
                "A. 有，且可以自由扩展图谱外概念",
                "B. 有，但只能使用教师输入的口头常识",
                "C. 没有，但可以猜测标准答案",
                "D. 没有，需要先补充知识图谱证据",
            ],
            "correct_answer": "D",
            "explanation": "当前检索不到可用图谱证据。系统应先补充或导入相关知识图谱，再生成练习。",
            "learning_plan": build_learning_plan(
                query=chapter_title or chapter_id,
                evidence=[],
                task="practice",
                chapter_data={"id": chapter_id, "title": chapter_title, "content": chapter_content},
            ),
        }

    item = normalized[0]
    label = str(item.get("label") or chapter_title or "该知识点")
    content = _clip(str(item.get("content") or label), 140)
    explanation = f"依据图谱证据[{item.get('index', 1)}]“{label}”：{content}"
    plan = build_learning_plan(
        query=chapter_title or label,
        evidence=normalized,
        learner_intent="practice",
        task="practice",
        chapter_data={"id": chapter_id, "title": chapter_title, "content": chapter_content},
    )
    return {
        "id": f"ex_{_safe_id(chapter_id)}_kg_1",
        "question": f"根据当前知识图谱，关于“{label}”最可靠的说法是哪一项？",
        "options": [
            f"A. {content}",
            "B. 可以直接引入图谱中未出现的高级概念作为结论",
            "C. 即使没有证据，也可以补全不存在的概念关系",
            "D. 该知识点与本章没有任何关系",
        ],
        "correct_answer": "A",
        "explanation": explanation,
        "source_evidence": normalized[:3],
        "learning_plan": plan,
    }


def _normalize_evidence_item(item: Dict[str, Any], *, index: int, default_source: str) -> Dict[str, Any]:
    metadata = dict(item.get("metadata") or {})
    content = _node_content(item)
    label = _node_label(item)
    return {
        "index": item.get("index") or index,
        "id": str(item.get("id") or item.get("node_id") or metadata.get("id") or label or f"evidence_{index}"),
        "label": label or f"evidence_{index}",
        "type": str(item.get("type") or metadata.get("type") or "concept"),
        "content": _clip(content or label, 900),
        "source": str(metadata.get("source") or item.get("source") or default_source),
    }


def _allowed_concepts(evidence: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    concepts: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence:
        key = str(item.get("id") or item.get("label") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        concepts.append(
            {
                "id": key,
                "name": str(item.get("label") or key),
                "type": str(item.get("type") or "concept"),
                "source_index": item.get("index"),
            }
        )
    return concepts


def _build_slots(evidence: Sequence[Dict[str, Any]], relations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    concept_entities = [
        {"id": item.get("id"), "name": item.get("label")}
        for item in evidence
        if item.get("id") and item.get("label")
    ]
    if concept_entities:
        slots.append({"type": "definition", "coverage": "full", "entities": concept_entities[:8]})

    prereq_entities = [
        {"id": relation.get("source"), "name": relation.get("source")}
        for relation in relations
        if relation.get("type") in {"precedes", "prerequisite_of", "depends_on"}
    ]
    if prereq_entities:
        slots.append({"type": "prerequisite", "coverage": "partial", "entities": prereq_entities[:6]})

    exercise_entities = [
        {"id": item.get("id"), "name": item.get("label")}
        for item in evidence
        if str(item.get("type") or "").lower() in {"exercise", "quiz", "question"}
    ]
    if exercise_entities:
        slots.append({"type": "practice", "coverage": "full", "entities": exercise_entities[:6]})

    return slots


def _node_label(item: Dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    return str(
        item.get("label")
        or metadata.get("label")
        or metadata.get("title")
        or item.get("title")
        or item.get("node_id")
        or item.get("id")
        or ""
    ).strip()


def _node_content(item: Dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    return str(
        item.get("content")
        or metadata.get("content")
        or metadata.get("description")
        or item.get("description")
        or _node_label(item)
        or ""
    ).strip()


def _clip(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _tokenize(text: str) -> set[str]:
    lowered = (text or "").lower()
    ascii_tokens = {token for token in re.findall(r"[a-zA-Z0-9_]{2,}", lowered) if len(token) >= 2}
    cjk_tokens = {token for token in re.findall(r"[\u4e00-\u9fff]{2,}", lowered)}
    grams: set[str] = set()
    for token in cjk_tokens:
        grams.update(token[index : index + 2] for index in range(max(1, len(token) - 1)))
    return ascii_tokens | grams


def _overlap_score(tokens: set[str], text: str) -> int:
    if not tokens:
        return 0
    target = (text or "").lower()
    return sum(1 for token in tokens if token in target)


def _default_intent_for_task(task: str) -> str:
    return {
        "lecture": "explain",
        "qa": "explain",
        "exercise": "practice",
        "practice": "practice",
        "feedback": "feedback",
    }.get(task, "explain")


def _safe_id(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", value or "chapter").strip("_")
    return clean or "chapter"
