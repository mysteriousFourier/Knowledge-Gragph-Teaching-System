from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse

from KGTS.models.education import (
    CoursewareExportPptxRequest,
    CoursewareProjectSaveRequest,
    GenerateLectureRequest,
    GeneratePptTexRequest,
    GenerateSlideLecturesRequest,
    PreviewTexRequest,
    AskQuestionRequest,
    LearningPlanRequest,
    NaturalSupplementRequest,
    SaveChapterRequest,
    SaveLectureRequest,
)
from KGTS.models.graph import AddNodeRequest, UpdateNodeRequest
from KGTS.core.mcp_client import call_mcp_tool
from KGTS.core.bridge import (
    build_frontend_graph,
    build_rag_context,
    chapter_store,
    delete_generated_lecture_nodes,
    get_graph_schema,
    import_graph_payload,
    import_graph_db_payload,
    import_graphml_payload,
    search_nodes as backend_search_nodes,
)
from KGTS.core.graph_context import build_graphrag_context, build_node_contexts
from KGTS.education.claude_api import DeepSeekAPIClient, get_deepseek_model
from KGTS.education.kg_constraints import (
    KG_CONSTRAINED_SYSTEM_PROMPT,
    build_lecture_gc_dpg_requirements,
    build_learning_plan,
    build_constrained_generation_prompt,
    clean_generated_lecture_output,
    evidence_from_rag,
    evidence_from_graph,
    format_evidence,
    format_formula_context,
    format_graph_paths,
    expand_formula_references,
    formula_context_for_text,
    graph_paths_for_evidence,
)
from KGTS.config import load_root_env
from KGTS.education.exercise_helpers import _normalize_exercise_bank
from KGTS.education.qa_helpers import (
    _build_plan_from_graph,
    _build_question_fallback_response,
    _safe_consistency_report,
    answer_with_retrieval,
)
from KGTS.education.ppt_tex_generator import (
    ARTIFACT_DIR,
    build_pptx_artifact,
    build_tex_from_slides,
    normalize_generated_slides,
)
from KGTS.education.ppt_parser import SUPPORTED_COURSEWARE_EXTENSIONS, SUPPORTED_COURSEWARE_FORMATS_TEXT
from KGTS.education.courseware_editor import (
    assets_from_upload,
    build_editable_model,
    build_editable_model_from_slide_details,
    build_pptx_artifact_from_editable_model,
    list_courseware_projects,
    load_courseware_project,
    save_courseware_project,
    serialize_editable_model_to_tex,
)

load_root_env()

router = APIRouter(prefix="/api", tags=["education"])


@router.get("/")
async def root():
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
                "search_nodes": "/api/education/search-nodes",
            },
            "student": {
                "login": "/api/student/login",
                "chapter": "/api/student/chapter",
                "mark_chapter": "/api/student/mark-chapter",
                "exercises": "/api/student/exercises",
                "check_answer": "/api/student/check-answer",
                "question": "/api/student/question",
                "review": "/api/student/review",
            },
        },
    }


@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@router.get("/config-status")
async def config_status():
    return {
        "success": True,
        "deepseek_api_key_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        "flash_model": get_deepseek_model("flash"),
        "pro_model": get_deepseek_model("pro"),
    }


@router.post("/education/generate-lecture")
async def generate_lecture(request: GenerateLectureRequest):
    graph_data = None
    try:
        raw_chapter_title = (request.chapter_title or "").strip()
        chapter_content = expand_formula_references(request.chapter_content or "")
        selected_context = None
        graphrag_context = None
        source_node_ids = _normalize_source_node_ids(request.source_node_id, request.source_node_ids)
        source_node_id = source_node_ids[0] if source_node_ids else None
        if source_node_ids:
            selected_context = build_node_contexts(source_node_ids)
            if not selected_context.get("success"):
                raise HTTPException(status_code=404, detail=selected_context.get("error") or "Graph node not found")
            graph_content = str(selected_context.get("chapter_content") or "").strip()
            supplemental_content = chapter_content.strip()
            chapter_content = graph_content
            if supplemental_content and supplemental_content not in graph_content:
                chapter_content = f"{graph_content}\n\nTeacher supplemental notes:\n{supplemental_content}"
            if not raw_chapter_title:
                raw_chapter_title = str(selected_context.get("chapter_title") or "").strip()
            graph_data = selected_context.get("graph_data")
        try:
            if graph_data is None:
                graph_data = await call_mcp_tool("read_graph")
            if isinstance(graph_data, dict):
                graph_data = build_frontend_graph(graph_data)
        except Exception:
            try:
                if graph_data is None:
                    graph_data = build_frontend_graph()
            except Exception:
                graph_data = None

        claude_client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=request.model or get_deepseek_model("pro"),
        )
        generated_title = raw_chapter_title or await _generate_chapter_title(
            claude_client,
            graph_data if isinstance(graph_data, dict) else {"nodes": [], "relations": []},
            chapter_content,
        )
        chapter_title = generated_title or "未命名章节"
        graphrag_query = f"{chapter_title}\n{chapter_content[:1200]}"
        try:
            graphrag_context = build_graphrag_context(
                graphrag_query,
                seed_node_ids=source_node_ids or None,
                limit=8,
            )
            if source_node_ids:
                selected_context = graphrag_context.get("selected_context") or selected_context
            graph_data = graphrag_context.get("graph_data") or graph_data
            if graphrag_context.get("context"):
                chapter_content = str(graphrag_context.get("context") or chapter_content)
        except Exception:
            graphrag_context = None
        chapter_data = {
            "id": request.chapter_id,
            "title": chapter_title,
            "content": chapter_content,
            "teacher_guidance": str(request.teacher_guidance or "").strip(),
            "source_node_ids": source_node_ids,
            "graphrag_context": graphrag_context,
            "graph_context": _format_graphrag_generation_context(graphrag_context) if graphrag_context else "",
        }
        if graphrag_context and graphrag_context.get("llm_context"):
            learning_plan = build_learning_plan(
                query=chapter_title,
                evidence=evidence_from_rag(graphrag_context.get("llm_context") or [], limit=8),
                relations=[
                    {
                        "source": item.get("source"),
                        "target": item.get("target"),
                        "type": item.get("type") or "related",
                        "metadata": {"description": item.get("description", "")},
                    }
                    for item in (graphrag_context.get("graph_paths") or [])
                ],
                learner_intent="explain",
                learning_level="beginner",
                task="lecture",
                chapter_data=chapter_data,
            )
        elif selected_context and selected_context.get("evidence"):
            learning_plan = build_learning_plan(
                query=chapter_title,
                evidence=selected_context.get("evidence") or [],
                learner_intent="explain",
                learning_level="beginner",
                task="lecture",
                chapter_data=chapter_data,
            )
        else:
            learning_plan = _build_plan_from_graph(
                query=chapter_title,
                graph_data=graph_data if isinstance(graph_data, dict) else None,
                task="lecture",
                chapter_data=chapter_data,
            )
        if not learning_plan.get("evidence"):
            rag = build_rag_context(f"{chapter_title}\n{chapter_content[:800]}", limit=6)
            learning_plan = build_learning_plan(
                query=chapter_title,
                evidence=evidence_from_rag(rag.get("llm_context") or [], limit=6),
                learner_intent="explain",
                learning_level="beginner",
                task="lecture",
                chapter_data=chapter_data,
            )

        lecture_content = await claude_client.generate_lecture(
            graph_data if isinstance(graph_data, dict) else {"nodes": [], "relations": []},
            chapter_data,
            request.style,
        )
        lecture_content = clean_generated_lecture_output(lecture_content)
        consistency_report = _safe_consistency_report(lecture_content, learning_plan, task="lecture")
        chapter_store.save_chapter(
            title=chapter_title,
            content=chapter_content,
            chapter_id=request.chapter_id,
            source_type="graph_subtree" if selected_context else None,
            source_node_ids=source_node_ids or None,
            source_scope=(selected_context or {}).get("scope"),
            sync_backend=False,
        )
        saved_chapter = chapter_store.save_lecture(
            chapter_id=request.chapter_id,
            lecture_content=lecture_content,
            learning_plan=learning_plan,
            consistency_report=consistency_report,
            source_type="graph_subtree" if selected_context else None,
            source_node_ids=source_node_ids or None,
            source_scope=(selected_context or {}).get("scope"),
        )

        return {
            "success": True,
            "content": lecture_content,
            "lecture_content": lecture_content,
            "chapter_id": saved_chapter.get("id") or request.chapter_id,
            "chapter_title": chapter_title,
            "style": request.style,
            "model": claude_client.model,
            "learning_plan": learning_plan,
            "consistency_report": consistency_report,
            "source_node_id": source_node_id,
            "source_node_ids": source_node_ids,
            "source_scope": (selected_context or {}).get("scope"),
            "retrieval_mode": (graphrag_context or {}).get("retrieval_mode"),
            "retrieval_stats": (graphrag_context or {}).get("retrieval_stats"),
            "graphrag_context": graphrag_context,
            "vector_hits": (graphrag_context or {}).get("vector_hits"),
            "graph_paths": (graphrag_context or {}).get("graph_paths"),
            "formula_context": (graphrag_context or {}).get("formula_context"),
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


async def _generate_chapter_title(client: DeepSeekAPIClient, graph_data: Dict[str, Any], chapter_content: str) -> str:
    evidence = evidence_from_graph(graph_data, query=chapter_content[:800] or "课程章节", limit=8)
    evidence_text = format_evidence(evidence)
    prompt = f"""请基于以下课程材料生成一个简洁、准确的章节标题。

要求：
1. 只输出标题本身，不要解释。
2. 优先保留原文中的章节名、英文术语和编号。
3. 标题长度不超过 40 个汉字或 80 个英文字符。
4. 不要使用“未命名章节”“授课文案”“生成文案”等泛化标题。

章节正文：
{chapter_content[:1200] or "（未提供章节正文，请根据图谱证据判断）"}

图谱证据：
{evidence_text}
"""
    title = await client._call_deepseek(
        prompt,
        max_tokens=120,
        system_prompt="You generate concise course chapter titles. Return only the title.",
    )
    return str(title or "").strip().strip("\"'“”")


@router.post("/education/generate-ppt-tex")
async def generate_ppt_tex(request: GeneratePptTexRequest):
    source_node_ids = _normalize_source_node_ids(request.source_node_id, request.source_node_ids)
    if not source_node_ids:
        raise HTTPException(status_code=400, detail="请选择图谱章节树节点后再生成 PPT/TeX")
    try:
        selected_context = build_node_contexts(source_node_ids)
        if not selected_context.get("success"):
            raise HTTPException(status_code=404, detail=selected_context.get("error") or "Graph node not found")
        chapter_title = str(request.chapter_title or selected_context.get("chapter_title") or "").strip() or "图谱生成课件"
        graphrag_context = build_graphrag_context(
            f"{chapter_title}\n{str(selected_context.get('chapter_content') or '')[:1200]}",
            seed_node_ids=source_node_ids,
            limit=10,
        )
        selected_context = graphrag_context.get("selected_context") or selected_context
        graph_data = graphrag_context.get("graph_data") or selected_context.get("graph_data")
        context_content = _format_graphrag_generation_context(graphrag_context) or str(selected_context.get("chapter_content") or "").strip()
        source_evidence = evidence_from_rag(graphrag_context.get("llm_context") or [], limit=10)
        learning_plan = _build_ppt_learning_plan(
            chapter_title=chapter_title,
            chapter_content=context_content,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            selected_evidence=source_evidence,
        )
        graph_paths = graphrag_context.get("graph_paths") or graph_paths_for_evidence(
            graph_data if isinstance(graph_data, dict) else None,
            learning_plan.get("evidence") or [],
            limit=12,
        )
        formula_context = graphrag_context.get("formula_context") or formula_context_for_text(context_content, limit=12)
        raw_slides: Any = None
        warning = ""
        try:
            client = DeepSeekAPIClient(
                api_key=request.api_key,
                model=request.model or get_deepseek_model("pro"),
            )
            prompt = _build_ppt_tex_prompt(
                chapter_title=chapter_title,
                context_content=context_content,
                learning_plan=learning_plan,
                graph_paths=graph_paths,
                formula_context=formula_context,
                style=request.style,
                teacher_guidance=str(request.teacher_guidance or "").strip(),
                max_slides=request.max_slides,
            )
            raw_slides = await client._call_deepseek(
                prompt,
                max_tokens=3600,
                system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT,
                read_timeout_seconds=90.0,
            )
            model_name = client.model
        except ValueError as exc:
            if "API" not in str(exc).upper():
                raise
            warning = "DeepSeek API未配置，已使用图谱内容生成基础 PPT/TeX。"
            model_name = get_deepseek_model("pro")
        except Exception as exc:
            warning = f"PPT/TeX大模型生成失败，已使用图谱内容生成基础 PPT/TeX：{exc}"
            model_name = get_deepseek_model("pro")

        slides = normalize_generated_slides(
            raw_slides,
            fallback_title=chapter_title,
            fallback_content=context_content,
            max_slides=max(1, min(int(request.max_slides or 12), 30)),
        )
        tex_content = build_tex_from_slides(chapter_title, slides)
        editable_model = build_editable_model_from_slide_details(
            slides,
            title=chapter_title,
            source_tex=tex_content,
            tex_source_file="generated.tex",
        )
        artifact = build_pptx_artifact(chapter_title, slides, source_node_ids=source_node_ids)
        artifact["tex_content_hash"] = hashlib.md5(tex_content.encode("utf-8")).hexdigest()
        artifact.pop("tex_content", None)
        return {
            "success": True,
            "chapter_title": chapter_title,
            "slide_count": len(slides),
            "slides": slides,
            "full_text": "\n\n---\n\n".join(str(slide.get("raw_text") or "") for slide in slides),
            "tex_content": tex_content,
            "editable_model": editable_model,
            "asset_map": editable_model.get("assets") or {},
            "layout": editable_model.get("layout") or {},
            "source_tex": tex_content,
            "ppt_artifact": artifact,
            "learning_plan": learning_plan,
            "retrieval_mode": graphrag_context.get("retrieval_mode"),
            "retrieval_stats": graphrag_context.get("retrieval_stats"),
            "graphrag_context": graphrag_context,
            "vector_hits": graphrag_context.get("vector_hits"),
            "graph_paths": graph_paths,
            "formula_context": formula_context,
            "source_node_id": source_node_ids[0],
            "source_node_ids": source_node_ids,
            "source_scope": selected_context.get("scope"),
            "style": request.style,
            "model": model_name,
            "generated_at": datetime.now().isoformat(),
            **({"warning": warning} if warning else {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPT/TeX 生成失败: {str(e)}")


@router.post("/education/generate-slide-lectures")
async def generate_slide_lectures(request: GenerateSlideLecturesRequest):
    source_node_ids = _normalize_source_node_ids(request.source_node_id, request.source_node_ids)
    if not source_node_ids:
        source_node_ids = _normalize_source_node_ids(None, request.ppt_source_node_ids)
    if not source_node_ids:
        raise HTTPException(status_code=400, detail="请选择图谱章节树节点后再生成逐页讲解")
    if not request.slides:
        raise HTTPException(status_code=400, detail="缺少已生成的 PPT/TeX 页面内容")
    try:
        selected_context = build_node_contexts(source_node_ids)
        if not selected_context.get("success"):
            raise HTTPException(status_code=404, detail=selected_context.get("error") or "Graph node not found")
        chapter_title = request.chapter_title or selected_context.get("chapter_title") or "图谱生成课件"
        base_query = "\n\n".join(str(slide.get("raw_text") or slide.get("content") or slide.get("title") or "") for slide in request.slides)[:1400]
        graphrag_context = build_graphrag_context(
            f"{chapter_title}\n{base_query}",
            seed_node_ids=source_node_ids,
            limit=10,
        )
        selected_context = graphrag_context.get("selected_context") or selected_context
        graph_data = graphrag_context.get("graph_data") or selected_context.get("graph_data")
        graph_context_content = _format_graphrag_generation_context(graphrag_context)
        source_evidence = evidence_from_rag(graphrag_context.get("llm_context") or [], limit=10)
        client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=request.model or get_deepseek_model("pro"),
        )
        slide_lectures = await _generate_per_slide_lectures(
            client,
            request.slides,
            request.style,
            chapter_title,
            graph_data if isinstance(graph_data, dict) else None,
            selected_evidence=source_evidence,
            selected_graph_context=graph_context_content,
            source_node_ids=source_node_ids,
            teacher_guidance=str(request.teacher_guidance or "").strip(),
        )
        merged_lecture = _merge_slide_lectures(slide_lectures)
        learning_plan = _build_ppt_learning_plan(
            chapter_title=chapter_title,
            chapter_content="\n\n".join(str(slide.get("raw_text") or slide.get("content") or "") for slide in request.slides),
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            selected_evidence=source_evidence,
        )
        drift_report = _build_source_drift_report(request.ppt_source_node_ids or [], source_node_ids)
        return {
            "success": True,
            "chapter_title": request.chapter_title or selected_context.get("chapter_title") or "图谱生成课件",
            "slide_count": len(request.slides),
            "slides": request.slides,
            "full_text": "\n\n---\n\n".join(str(slide.get("raw_text") or "") for slide in request.slides),
            "tex_content": request.tex_content,
            "lecture_content": merged_lecture,
            "slide_lectures": slide_lectures,
            "learning_plan": learning_plan,
            "consistency_report": _safe_consistency_report(merged_lecture, learning_plan, task="lecture"),
            "retrieval_mode": graphrag_context.get("retrieval_mode"),
            "retrieval_stats": graphrag_context.get("retrieval_stats"),
            "graphrag_context": graphrag_context,
            "vector_hits": graphrag_context.get("vector_hits"),
            "graph_paths": graphrag_context.get("graph_paths"),
            "formula_context": graphrag_context.get("formula_context"),
            "source_node_id": source_node_ids[0],
            "source_node_ids": source_node_ids,
            "source_scope": selected_context.get("scope"),
            "ppt_source_node_ids": request.ppt_source_node_ids or [],
            "lecture_source_node_ids": source_node_ids,
            "drift_report": drift_report,
            "warning": drift_report.get("warning") or None,
            "style": request.style,
            "model": client.model,
            "generated_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except ValueError as e:
        if "API" in str(e).upper():
            return {
                "success": False,
                "error": "DeepSeek API is not configured",
                "message": "Please configure a DeepSeek API key in settings or DEEPSEEK_API_KEY.",
            }
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"逐页讲解生成失败: {str(e)}")


def _normalize_source_node_ids(source_node_id: Optional[str], source_node_ids: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for node_id in [source_node_id, *(source_node_ids or [])]:
        text = str(node_id or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _scope_graph_to_ids(graph_data: Optional[Dict[str, Any]], allowed_node_ids: List[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(graph_data, dict) or not allowed_node_ids:
        return graph_data
    allowed = {str(node_id or "").strip() for node_id in allowed_node_ids if str(node_id or "").strip()}
    if not allowed:
        return graph_data
    nodes = [
        node
        for node in graph_data.get("nodes", [])
        if isinstance(node, dict) and str(node.get("id") or "") in allowed
    ]
    relations = []
    for relation in graph_data.get("relations") or graph_data.get("edges") or []:
        if not isinstance(relation, dict):
            continue
        source = str(relation.get("source_id") or relation.get("source") or relation.get("from") or "")
        target = str(relation.get("target_id") or relation.get("target") or relation.get("to") or "")
        if source in allowed and target in allowed:
            relations.append(relation)
    return {
        **graph_data,
        "nodes": nodes,
        "relations": relations,
        "edges": relations,
        "stats": {"node_count": len(nodes), "relation_count": len(relations)},
    }


def _build_ppt_tex_prompt(
    *,
    chapter_title: str,
    context_content: str,
    learning_plan: Dict[str, Any],
    graph_paths: List[Dict[str, Any]],
    formula_context: List[Dict[str, Any]],
    style: str,
    teacher_guidance: str,
    max_slides: int,
) -> str:
    guidance = f"\nTeacher guidance:\n{teacher_guidance[:1600]}\n" if teacher_guidance else ""
    return f"""Generate a classroom PPT/TeX slide plan from the selected graph subtree.

Return only valid JSON in this exact shape:
{{
  "slides": [
    {{
      "title": "short slide title",
      "bullets": ["3-5 concise bullet points"],
      "notes": "short teacher note for this slide"
    }}
  ]
}}

Rules:
1. Generate {max(1, min(int(max_slides or 12), 30))} slides or fewer.
2. Use the selected graph subtree as the evidence boundary.
3. Keep formulas in LaTeX when they appear in evidence.
4. Do not invent concepts outside the selected graph context.
5. Make slide titles specific enough to map back to the source nodes.
6. The teaching style is: {style}.
{guidance}
Chapter title:
{chapter_title}

Selected graph subtree context:
{context_content[:7000]}

Matched graph evidence:
{format_evidence(learning_plan.get("evidence") or [])}

Graph relation paths:
{format_graph_paths(graph_paths)}

Formula derivation and scoped symbol context:
{format_formula_context(formula_context)}
"""


def _format_graphrag_generation_context(graphrag_context: Optional[Dict[str, Any]]) -> str:
    if not graphrag_context:
        return ""
    parts = []
    context = str(graphrag_context.get("context") or "").strip()
    if context:
        parts.append("GraphRAG vector hits and graph expansion:\n" + context)
    graph_paths = graphrag_context.get("graph_paths") or []
    if graph_paths:
        parts.append("Graph relation paths:\n" + format_graph_paths(graph_paths))
    formulas = graphrag_context.get("formula_context") or []
    if formulas:
        parts.append("Formula derivation and scoped symbol context:\n" + format_formula_context(formulas))
    return "\n\n".join(parts)


def _merge_slide_lectures(slide_lectures: List[Dict[str, Any]]) -> str:
    return "\n\n---\n\n".join(
        f"## 第 {item.get('index')} 页：{item.get('title') or ''}\n\n{str(item.get('lecture') or '').strip() or '_本页未生成文案_'}"
        for item in slide_lectures
    )


def _build_source_drift_report(ppt_source_node_ids: List[str], lecture_source_node_ids: List[str]) -> Dict[str, Any]:
    ppt_set = {str(item) for item in (ppt_source_node_ids or []) if str(item).strip()}
    lecture_set = {str(item) for item in (lecture_source_node_ids or []) if str(item).strip()}
    if not ppt_set:
        return {"status": "unknown", "changed": False}
    added = sorted(lecture_set - ppt_set)
    removed = sorted(ppt_set - lecture_set)
    changed = bool(added or removed)
    report: Dict[str, Any] = {
        "status": "changed" if changed else "aligned",
        "changed": changed,
        "added_node_ids": added,
        "removed_node_ids": removed,
        "ppt_source_node_ids": sorted(ppt_set),
        "lecture_source_node_ids": sorted(lecture_set),
    }
    if changed:
        report["warning"] = "讲解阶段选择的图谱范围与生成 PPT/TeX 时不完全一致，系统已用页面内容作为主锚点降低漂移。"
    return report


@router.post("/education/ask-question")
async def ask_question(request: AskQuestionRequest):
    try:
        return await answer_with_retrieval(request.question, request.api_key, timeout_seconds=40)
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


@router.post("/education/learning-plan")
async def create_learning_plan(request: LearningPlanRequest):
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


@router.post("/education/natural-supplement")
async def natural_supplement(request: NaturalSupplementRequest):
    query = f"{request.supplement}\n{request.original_text[:800]}"
    graph_data = None
    warning = None
    try:
        graph_data = build_frontend_graph()
    except Exception as exc:
        warning = f"图谱读取失败，已尝试使用 RAG 检索：{exc}"

    learning_plan = _build_plan_from_graph(
        query=query,
        graph_data=graph_data if isinstance(graph_data, dict) else None,
        task="lecture",
        chapter_data={
            "title": "自然补充",
            "content": f"{request.original_text}\n\n{request.supplement}",
        },
    )
    sources = learning_plan.get("evidence") or []
    retrieval_context = ""
    if not sources:
        try:
            rag = build_rag_context(query, limit=6)
            retrieval_context = rag.get("context") or ""
            sources = rag.get("llm_context") or []
            learning_plan = build_learning_plan(
                query=query,
                evidence=evidence_from_rag(sources, limit=6),
                learner_intent="explain",
                learning_level="beginner",
                task="lecture",
                chapter_data={
                    "title": "自然补充",
                    "content": f"{request.original_text}\n\n{request.supplement}",
                },
            )
            warning = warning or "图谱未命中，已使用 RAG 检索证据生成补充文案。"
        except Exception as exc:
            warning = f"{warning + '；' if warning else ''}RAG 检索失败，已退回纯模型补充：{exc}"

    try:
        claude_client = DeepSeekAPIClient(
            api_key=request.api_key,
            model=get_deepseek_model("pro"),
        )
        prompt = build_constrained_generation_prompt(
            task_title="将补充内容自然融入授课文案",
            user_input=request.supplement,
            source_content=request.original_text,
            learning_plan=learning_plan,
            requirements=[
                "保持原文逻辑结构和语气，输出整段融合后的最终文案。",
                "优先使用证据中出现的概念、公式、术语和关系。",
                "如果补充内容中有证据未覆盖的扩展，请在措辞中保持限定，不编造课程私有事实。",
                "不要输出提纲、自检说明或证据清单。",
            ],
        )
        result = expand_formula_references(
            await claude_client._call_deepseek(
                prompt,
                max_tokens=2600,
                system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT,
                read_timeout_seconds=60.0,
            ),
            expand_labels=True,
        )
        payload = {
            "success": True,
            "result": result,
            "model": claude_client.model,
            "retrieval_context": retrieval_context,
            "sources": sources,
            "learning_plan": learning_plan,
            "consistency_report": _safe_consistency_report(result, learning_plan, task="lecture"),
        }
        if warning:
            payload["warning"] = warning
        return payload
    except ValueError as e:
        error_text = str(e)
        if "API密钥" in error_text or "API" in error_text.upper() or "KEY" in error_text.upper():
            fallback_result = f"{request.original_text}\n\n{request.supplement}"
            return {
                "success": True,
                "result": fallback_result,
                "warning": "DeepSeek API未配置，请在设置中配置API密钥",
                "retrieval_context": retrieval_context,
                "sources": sources,
                "learning_plan": learning_plan,
                "consistency_report": _safe_consistency_report(fallback_result, learning_plan, task="lecture"),
            }
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自然补充失败: {str(e)}")


@router.get("/education/graph")
async def get_graph():
    try:
        delete_generated_lecture_nodes()
        return {
            "success": True,
            "data": build_frontend_graph(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取知识图谱失败: {str(e)}")


@router.get("/education/graph/node-context")
async def get_graph_node_context(node_id: List[str] = Query(...), max_nodes: int = 260):
    try:
        result = build_node_contexts(node_id, max_nodes=max(1, min(max_nodes, 600)))
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error") or "Graph node not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"构建节点备课上下文失败: {str(e)}")


@router.get("/education/artifacts/{filename}")
async def get_generated_artifact(filename: str):
    safe_name = Path(filename).name
    path = ARTIFACT_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="生成文件不存在")
    media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if safe_name.lower().endswith(".tex"):
        media_type = "application/x-tex"
    return FileResponse(path, media_type=media_type, filename=safe_name)


@router.post("/education/cleanup-lecture-nodes")
async def cleanup_lecture_nodes():
    try:
        return delete_generated_lecture_nodes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup lecture nodes failed: {str(e)}")


@router.post("/education/add-node")
async def add_node(request: AddNodeRequest):
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


@router.put("/education/update-node")
async def update_node(request: UpdateNodeRequest):
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


@router.get("/education/search-nodes")
async def search_nodes(keyword: str, node_type: Optional[str] = None, limit: int = 10):
    try:
        return {
            "success": True,
            "results": backend_search_nodes(keyword, node_type=node_type, limit=limit),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索节点失败: {str(e)}")


@router.get("/education/schema")
async def get_schema():
    try:
        return {
            "success": True,
            "schema": get_graph_schema(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取图谱结构失败: {str(e)}")


@router.post("/education/upload-graph")
async def upload_graph(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    filename = file.filename
    lower_name = filename.lower()
    if not lower_name.endswith((".json", ".graphml", ".xml", ".db", ".sqlite", ".sqlite3")):
        raise HTTPException(status_code=400, detail="仅支持 .json、.graphml、.xml、.db、.sqlite 或 .sqlite3 图谱文件")

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="上传的文件为空")
        if len(file_bytes) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过 50MB 限制")

        if lower_name.endswith((".db", ".sqlite", ".sqlite3")):
            result = import_graph_db_payload(file_bytes)
            parsed_stats = result.get("sqlite_stats") if isinstance(result, dict) else {}
            parsed = {
                "nodes": parsed_stats.get("nodes_parsed", 0),
                "relations": parsed_stats.get("relations_parsed", 0),
            }
            graph_type = "sqlite"
        else:
            text = file_bytes.decode("utf-8-sig")
            if lower_name.endswith(".json"):
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise HTTPException(status_code=400, detail="JSON 图谱文件必须是对象")
                graph_data = payload.get("graph_data") if isinstance(payload.get("graph_data"), dict) else payload
                result = import_graph_payload(graph_data)
                parsed = {
                    "nodes": len(graph_data.get("nodes") or []),
                    "relations": len(graph_data.get("relations") or graph_data.get("edges") or []),
                }
                graph_type = "json"
            else:
                result = import_graphml_payload(file_content=text)
                parsed_stats = result.get("graphml_stats") if isinstance(result, dict) else {}
                parsed = {
                    "nodes": parsed_stats.get("nodes_parsed", 0),
                    "relations": parsed_stats.get("edges_parsed", 0),
                }
                graph_type = "graphml"

        return {
            "success": True,
            "file_name": filename,
            "graph_type": graph_type,
            "chapter_hint": {
                "title": "",
                "content": f"请基于已导入的知识图谱生成授课文案。图谱文件：{filename}",
            },
            "parsed": parsed,
            "result": result,
            "message": "图谱文件导入成功",
            "imported_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件必须使用 UTF-8 编码")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e.msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图谱文件导入失败: {str(e)}")


@router.post("/education/save-chapter")
async def save_chapter(request: SaveChapterRequest):
    try:
        source_node_ids = _normalize_source_node_ids(None, request.source_node_ids)
        chapter_data = chapter_store.save_chapter(
            title=request.title,
            content=request.content,
            graph_data=request.graph_data,
            chapter_id=request.chapter_id,
            source_type=request.source_type,
            source_node_ids=source_node_ids or request.source_node_ids,
            source_scope=request.source_scope,
            ppt_slides=request.ppt_slides,
            slide_lectures=request.slide_lectures,
            tex_content=request.tex_content,
            editable_model=request.editable_model,
            asset_map=request.asset_map,
            ppt_artifact=request.ppt_artifact,
            ppt_source_node_ids=request.ppt_source_node_ids,
            lecture_source_node_ids=request.lecture_source_node_ids,
        )
        return {
            "success": True,
            "chapter_id": chapter_data["id"],
            "chapter": chapter_data,
            "message": "章节保存成功",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存章节失败: {str(e)}")


@router.get("/education/list-chapters")
async def list_chapters():
    try:
        return {
            "success": True,
            "chapters": chapter_store.list_chapters(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节列表失败: {str(e)}")


@router.get("/education/get-chapter")
async def get_chapter(chapter_id: str):
    try:
        chapter = chapter_store.get_chapter(chapter_id)
        if not chapter:
            return {"success": False, "error": "章节不存在"}
        cleaned_bank = _normalize_exercise_bank(chapter.get("exercise_bank") or chapter.get("exercises"))
        approved_bank = _normalize_exercise_bank(chapter.get("approved_exercise_bank"))
        chapter = dict(chapter)
        chapter["exercise_bank"] = cleaned_bank
        chapter["approved_exercise_bank"] = approved_bank
        chapter["exercises"] = cleaned_bank[0] if cleaned_bank else None
        return {"success": True, "chapter": chapter}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节数据失败: {str(e)}")


@router.delete("/education/delete-chapter")
async def delete_chapter(chapter_id: str):
    try:
        result = chapter_store.delete_chapter(chapter_id)
        if not result.get("success"):
            return {"success": False, "error": "Chapter not found", "chapter_id": chapter_id}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete chapter failed: {str(e)}")


@router.post("/education/save-lecture")
async def save_lecture(request: SaveLectureRequest):
    try:
        existing_chapter = chapter_store.get_chapter(request.chapter_id) or {}
        source_node_ids = _normalize_source_node_ids(None, request.source_node_ids)
        cleaned_content = clean_generated_lecture_output(request.lecture_content)
        learning_plan = request.learning_plan if request.learning_plan is not None else existing_chapter.get("lecture_learning_plan")
        consistency_report = request.consistency_report if request.consistency_report is not None else None
        if consistency_report is None and isinstance(learning_plan, dict):
            consistency_report = _safe_consistency_report(cleaned_content, learning_plan, task="lecture")
        chapter = chapter_store.save_lecture(
            chapter_id=request.chapter_id,
            lecture_content=cleaned_content,
            graph_data=request.graph_data,
            source_type=request.source_type,
            source_node_ids=source_node_ids or request.source_node_ids,
            source_scope=request.source_scope,
            ppt_slides=request.ppt_slides,
            slide_lectures=request.slide_lectures,
            tex_content=request.tex_content,
            editable_model=request.editable_model,
            asset_map=request.asset_map,
            ppt_artifact=request.ppt_artifact,
            ppt_source_node_ids=request.ppt_source_node_ids,
            lecture_source_node_ids=request.lecture_source_node_ids,
            learning_plan=learning_plan if isinstance(learning_plan, dict) else None,
            consistency_report=consistency_report if isinstance(consistency_report, dict) else None,
        )
        return {
            "success": True,
            "chapter": chapter,
            "message": "授课文案保存成功",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存授课文案失败: {str(e)}")


@router.post("/education/upload-ppt")
async def upload_ppt(
    file: UploadFile = File(...),
    style: str = Form("引导式教学"),
    api_key: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    source_node_id: Optional[str] = Form(None),
    source_node_ids: Optional[List[str]] = Form(None),
    graph_scope: Optional[str] = Form(None),
    teacher_guidance: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    if not file.filename.lower().endswith(tuple(SUPPORTED_COURSEWARE_EXTENSIONS)):
        raise HTTPException(status_code=400, detail=f"仅支持 {SUPPORTED_COURSEWARE_FORMATS_TEXT} 格式的课件文件")

    try:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")

        if len(file_bytes) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过 50MB 限制")

        from KGTS.education.ppt_parser import parse_courseware, build_ppt_lecture_prompt_data

        parse_result = parse_courseware(file_bytes, file.filename)
        if not parse_result.get("success"):
            raise HTTPException(status_code=400, detail=parse_result.get("error", "课件解析失败"))

        prompt_data = build_ppt_lecture_prompt_data(parse_result)
        editable_model = build_editable_model(parse_result, prompt_data)

        chapter_title = prompt_data["chapter_title"]
        chapter_content = prompt_data["chapter_content"]
        slide_details = prompt_data["slide_details"]
        normalized_source_node_ids = _normalize_source_node_ids(source_node_id, source_node_ids)
        selected_context = None
        graph_data = None
        source_scope = None
        graph_context_content = ""
        selected_evidence: List[Dict[str, Any]] = []

        if normalized_source_node_ids:
            selected_context = build_node_contexts(normalized_source_node_ids)
            if not selected_context.get("success"):
                raise HTTPException(status_code=404, detail=selected_context.get("error") or "Graph node not found")
            graph_data = selected_context.get("graph_data")
            source_scope = selected_context.get("scope")
            graph_context_content = str(selected_context.get("chapter_content") or "").strip()
            selected_evidence = selected_context.get("evidence") or []

        if not chapter_content.strip():
            payload = {
                "success": True,
                "chapter_title": chapter_title,
                "slide_count": prompt_data["total_slides"],
                "slides": slide_details,
                "full_text": chapter_content,
                "tex_content": parse_result.get("tex_content") or "",
                "tex_source_file": parse_result.get("tex_source_file") or "",
                "editable_model": editable_model,
                "asset_map": editable_model.get("assets") or {},
                "layout": editable_model.get("layout") or {},
                "source_tex": parse_result.get("tex_content") or "",
                "lecture_content": "",
                "slide_lectures": [
                    {
                        "index": slide.get("index"),
                        "title": slide.get("title", ""),
                        "lecture": "",
                        "skipped": True,
                    }
                    for slide in slide_details
                ],
                "warning": "课件中未提取到有效文本内容，可能是纯图片或扫描件",
            }
            if normalized_source_node_ids:
                payload.update(
                    {
                        "source_node_id": normalized_source_node_ids[0],
                        "source_node_ids": normalized_source_node_ids,
                        "source_scope": source_scope,
                    }
                )
            return payload

        if graph_data is None:
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
            "id": f"courseware_{hashlib.md5(file.filename.encode()).hexdigest()[:12]}",
            "title": chapter_title,
            "content": (
                f"Selected graph subtree context:\n{graph_context_content}\n\nCourseware full text:\n{chapter_content}"
                if graph_context_content
                else chapter_content
            ),
            "teacher_guidance": str(teacher_guidance or "").strip(),
        }
        lecture_learning_plan = _build_ppt_learning_plan(
            chapter_title=chapter_title,
            chapter_content=chapter_content,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
            selected_evidence=selected_evidence,
        )
        lecture_graph_paths = graph_paths_for_evidence(
            graph_data if isinstance(graph_data, dict) else None,
            lecture_learning_plan.get("evidence") or [],
            limit=10,
        )
        lecture_formula_context = formula_context_for_text(chapter_content, limit=10)
        chapter_data["graph_context"] = _format_ppt_generation_context(
            learning_plan=lecture_learning_plan,
            graph_paths=lecture_graph_paths,
            formulas=lecture_formula_context,
        )

        claude_client = DeepSeekAPIClient(
            api_key=api_key,
            model=model or get_deepseek_model("pro"),
        )

        lecture_content = await claude_client.generate_lecture(
            graph_data if isinstance(graph_data, dict) else {"nodes": [], "relations": []},
            chapter_data,
            style,
        )
        lecture_content = clean_generated_lecture_output(lecture_content)

        slide_lectures = await _generate_per_slide_lectures(
            claude_client,
            slide_details,
            style,
            chapter_title,
            graph_data if isinstance(graph_data, dict) else None,
            selected_evidence=selected_evidence,
            selected_graph_context=graph_context_content,
            source_node_ids=normalized_source_node_ids or None,
            teacher_guidance=str(teacher_guidance or "").strip(),
        )
        lecture_consistency_report = _safe_consistency_report(lecture_content, lecture_learning_plan, task="lecture")

        return {
            "success": True,
            "chapter_title": chapter_title,
            "slide_count": prompt_data["total_slides"],
            "slides": slide_details,
            "full_text": chapter_content,
            "tex_content": parse_result.get("tex_content") or "",
            "tex_source_file": parse_result.get("tex_source_file") or "",
            "editable_model": editable_model,
            "asset_map": editable_model.get("assets") or {},
            "layout": editable_model.get("layout") or {},
            "source_tex": parse_result.get("tex_content") or "",
            "lecture_content": lecture_content,
            "slide_lectures": slide_lectures,
            "learning_plan": lecture_learning_plan,
            "graph_paths": lecture_graph_paths,
            "formula_context": lecture_formula_context,
            "consistency_report": lecture_consistency_report,
            "source_node_id": normalized_source_node_ids[0] if normalized_source_node_ids else None,
            "source_node_ids": normalized_source_node_ids,
            "source_scope": source_scope,
            "style": style,
            "model": claude_client.model,
            "generated_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except ValueError as e:
        if "API" in str(e).upper():
            return {
                "success": False,
                "error": "DeepSeek API is not configured",
                "message": "Please configure a DeepSeek API key in settings or DEEPSEEK_API_KEY.",
            }
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"课件处理失败: {str(e)}")


async def _generate_per_slide_lectures(
    client: DeepSeekAPIClient,
    slide_details: List[Dict],
    style: str,
    chapter_title: str,
    graph_data: Optional[Dict[str, Any]] = None,
    selected_evidence: Optional[List[Dict[str, Any]]] = None,
    selected_graph_context: str = "",
    source_node_ids: Optional[List[str]] = None,
    teacher_guidance: str = "",
) -> List[Dict]:
    results = []
    for slide in slide_details:
        content_parts = []
        if slide.get("title"):
            content_parts.append(f"标题: {slide['title']}")
        if slide.get("content"):
            content_parts.append(slide["content"])
        if slide.get("notes"):
            content_parts.append(f"[备注] {slide['notes']}")
        for table_data in slide.get("tables", []):
            rows = table_data.get("rows", [])
            if rows:
                table_lines = []
                for row in rows:
                    table_lines.append(" | ".join(str(c) for c in row))
                content_parts.append("\n".join(table_lines))

        slide_text = "\n".join(content_parts)
        if not slide_text.strip():
            learning_plan = build_learning_plan(
                query=f"{chapter_title} 第 {slide.get('index')} 页",
                evidence=[],
                learner_intent="explain",
                learning_level="beginner",
                task="lecture",
                chapter_data={"title": chapter_title, "content": ""},
            )
            results.append({
                "index": slide["index"],
                "title": slide.get("title", ""),
                "lecture": "",
                "skipped": True,
                "learning_plan": learning_plan,
                "sources": [],
                "graph_paths": [],
                "formula_context": [],
            })
            continue

        chapter_data = {
            "title": f"{chapter_title} - 第 {slide['index']} 页",
            "content": (
                f"Selected graph subtree context:\n{selected_graph_context}\n\nPPT slide content:\n{slide_text}"
                if selected_graph_context
                else slide_text
            ),
        }
        slide_graphrag_context = None
        slide_graph_data = graph_data
        slide_selected_evidence = selected_evidence
        try:
            slide_graphrag_context = build_graphrag_context(
                f"{chapter_title}\n{slide_text[:1000]}",
                seed_node_ids=source_node_ids,
                limit=6,
            )
            slide_graph_data = slide_graphrag_context.get("graph_data") or graph_data
            slide_selected_evidence = evidence_from_rag(slide_graphrag_context.get("llm_context") or [], limit=6)
            if slide_graphrag_context.get("context"):
                chapter_data["content"] = (
                    f"GraphRAG scoped context:\n{_format_graphrag_generation_context(slide_graphrag_context)}\n\n"
                    f"PPT slide content:\n{slide_text}"
                )
        except Exception:
            slide_graphrag_context = None
        learning_plan = _build_ppt_learning_plan(
            chapter_title=chapter_title,
            chapter_content=slide_text,
            graph_data=slide_graph_data,
            chapter_data=chapter_data,
            query=f"{chapter_title}\n{slide_text[:800]}",
            selected_evidence=slide_selected_evidence,
        )
        sources = learning_plan.get("evidence") or []
        if not sources:
            try:
                rag = build_rag_context(
                    f"{chapter_title}\n{slide_text[:800]}",
                    limit=4,
                    seed_node_ids=source_node_ids,
                )
                sources = rag.get("llm_context") or []
                learning_plan = build_learning_plan(
                    query=f"{chapter_title}\n{slide_text[:800]}",
                    evidence=evidence_from_rag(sources, limit=4),
                    learner_intent="explain",
                    learning_level="beginner",
                    task="lecture",
                    chapter_data=chapter_data,
                )
            except Exception:
                sources = []
        graph_paths = (slide_graphrag_context or {}).get("graph_paths") or graph_paths_for_evidence(slide_graph_data, learning_plan.get("evidence") or [], limit=8)
        formula_context = (slide_graphrag_context or {}).get("formula_context") or formula_context_for_text(slide_text, limit=8)

        requirements = [
            *build_lecture_gc_dpg_requirements(style, slide_level=True),
            "Use the selected graph subtree evidence first when it is provided, then use this slide's own text as the slide-specific anchor.",
            "Explain this slide in accessible classroom language.",
            "Add only the background needed to make the slide teachable; keep unsupported extensions bounded.",
            "Use the graph relation paths as the main teaching order when they are relevant.",
            "If formulas appear, explain the meaning of the main symbols.",
            "When the same symbol can mean different things elsewhere, explain only the meaning in this slide/chapter scope.",
            "If a formula is derived from earlier formulas, mention the immediate derivation dependency in teacher-friendly language.",
            "Include 1-2 natural classroom questions when useful.",
            "Output directly usable Markdown prose for this slide.",
        ]
        if teacher_guidance:
            requirements.append(
                "Teacher guidance for emphasis, selection, and pacing. Treat it as generation guidance only; it must not override source/graph facts:\n"
                + teacher_guidance[:1600]
            )
        requirement_text = "\n".join(
            f"{index}. {item}" for index, item in enumerate(requirements, start=1)
        )
        selected_context_text = ""
        if selected_graph_context.strip():
            selected_context_text = f"""
Selected graph subtree context:
{selected_graph_context[:3500]}
"""
        prompt = f"""You are a teacher. Generate the lecture script for one PPT slide.

Chapter topic: {chapter_title}
Current slide: {slide['index']}
{selected_context_text}

Slide content:
{slide_text}

Available graph/RAG evidence for this slide:
{format_evidence(learning_plan.get("evidence") or [])}

Graph relation paths to use when teaching:
{format_graph_paths(graph_paths)}

Formula derivation and scoped symbol context:
{format_formula_context(formula_context)}

Requirements:
{requirement_text}

Output only the final slide lecture script."""

        try:
            lecture = expand_formula_references(
                await client._call_deepseek(
                    prompt,
                    max_tokens=2000,
                    system_prompt=KG_CONSTRAINED_SYSTEM_PROMPT,
                    read_timeout_seconds=60.0,
                ),
                expand_labels=True,
            )
            lecture = clean_generated_lecture_output(lecture)
        except Exception:
            lecture = ""

        results.append({
            "index": slide["index"],
            "title": slide.get("title", ""),
            "lecture": lecture,
            "skipped": not lecture.strip(),
            "sources": sources,
            "retrieval_mode": (slide_graphrag_context or {}).get("retrieval_mode"),
            "retrieval_stats": (slide_graphrag_context or {}).get("retrieval_stats"),
            "graphrag_context": slide_graphrag_context,
            "vector_hits": (slide_graphrag_context or {}).get("vector_hits"),
            "graph_paths": graph_paths,
            "formula_context": formula_context,
            "learning_plan": learning_plan,
            "consistency_report": _safe_consistency_report(lecture, learning_plan, task="lecture"),
        })

    return results


def _build_ppt_learning_plan(
    *,
    chapter_title: str,
    chapter_content: str,
    graph_data: Optional[Dict[str, Any]],
    chapter_data: Optional[Dict[str, Any]] = None,
    query: Optional[str] = None,
    selected_evidence: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    chapter_payload = chapter_data or {"title": chapter_title, "content": chapter_content}
    search_query = query or f"{chapter_title}\n{chapter_content[:1200]}"
    subtree_evidence = [
        item
        for item in (selected_evidence or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if subtree_evidence:
        matched_graph_evidence = evidence_from_graph(
            graph_data,
            query=search_query,
            chapter_data=chapter_payload,
            limit=8,
        )
        evidence = _dedupe_evidence([*subtree_evidence[:12], *matched_graph_evidence])
    else:
        evidence = evidence_from_graph(
            graph_data,
            query=search_query,
            chapter_data=chapter_payload,
            limit=10,
        )
    if chapter_content.strip():
        slide_evidence = {
            "index": 1,
            "id": f"ppt_slide::{hashlib.md5(search_query.encode('utf-8')).hexdigest()[:10]}",
            "label": str(chapter_payload.get("title") or chapter_title or "PPT slide"),
            "type": "ppt_slide",
            "content": chapter_content[:1800],
            "source": "ppt",
        }
        evidence = _dedupe_evidence([*evidence, slide_evidence] if subtree_evidence else [slide_evidence, *evidence])
    relations = graph_paths_for_evidence(graph_data, evidence, limit=12)
    learning_relations = [
        {
            "source": item.get("source"),
            "target": item.get("target"),
            "type": item.get("type") or "related",
            "metadata": {"description": item.get("description", "")},
        }
        for item in relations
    ]
    return build_learning_plan(
        query=search_query,
        evidence=evidence,
        relations=learning_relations,
        learner_intent="explain",
        learning_level="beginner",
        task="lecture",
        chapter_data=chapter_payload,
    )


def _dedupe_evidence(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        key = item_id or f"{item.get('source')}::{item.get('label')}::{item.get('content')}"
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _format_ppt_generation_context(
    *,
    learning_plan: Dict[str, Any],
    graph_paths: List[Dict[str, Any]],
    formulas: List[Dict[str, Any]],
) -> str:
    return "\n\n".join(
        [
            "Matched graph evidence:\n" + format_evidence(learning_plan.get("evidence") or []),
            "Graph relation paths:\n" + format_graph_paths(graph_paths),
            "Formula derivation and scoped symbol context:\n" + format_formula_context(formulas),
        ]
    )


@router.post("/education/upload-ppt-preview")
async def upload_ppt_preview(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    if not file.filename.lower().endswith(tuple(SUPPORTED_COURSEWARE_EXTENSIONS)):
        raise HTTPException(status_code=400, detail=f"仅支持 {SUPPORTED_COURSEWARE_FORMATS_TEXT} 格式")

    try:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")

        from KGTS.education.ppt_parser import parse_courseware, build_ppt_lecture_prompt_data

        parse_result = parse_courseware(file_bytes, file.filename)
        if not parse_result.get("success"):
            raise HTTPException(status_code=400, detail=parse_result.get("error", "课件解析失败"))

        prompt_data = build_ppt_lecture_prompt_data(parse_result)
        editable_model = build_editable_model(parse_result, prompt_data)

        return {
            "success": True,
            "chapter_title": prompt_data["chapter_title"],
            "slide_count": prompt_data["total_slides"],
            "slides": prompt_data["slide_details"],
            "full_text": prompt_data["chapter_content"],
            "tex_content": parse_result.get("tex_content") or "",
            "tex_source_file": parse_result.get("tex_source_file") or "",
            "editable_model": editable_model,
            "asset_map": editable_model.get("assets") or {},
            "layout": editable_model.get("layout") or {},
            "source_tex": parse_result.get("tex_content") or "",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"课件预览失败: {str(e)}")


@router.post("/education/preview-tex")
async def preview_tex(request: PreviewTexRequest):
    tex_content = str(request.tex_content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not tex_content.strip():
        raise HTTPException(status_code=400, detail="TeX 源码为空")

    try:
        from KGTS.education.ppt_parser import parse_text_courseware, build_ppt_lecture_prompt_data

        parse_result = parse_text_courseware(tex_content.encode("utf-8"), request.filename or "edited.tex")
        if not parse_result.get("success"):
            raise HTTPException(status_code=400, detail=parse_result.get("error", "TeX 解析失败"))

        prompt_data = build_ppt_lecture_prompt_data(parse_result)
        editable_model = build_editable_model(parse_result, prompt_data)
        return {
            "success": True,
            "chapter_title": prompt_data["chapter_title"],
            "slide_count": prompt_data["total_slides"],
            "slides": prompt_data["slide_details"],
            "full_text": prompt_data["chapter_content"],
            "tex_content": tex_content,
            "editable_model": editable_model,
            "asset_map": editable_model.get("assets") or {},
            "layout": editable_model.get("layout") or {},
            "source_tex": tex_content,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TeX 预览失败: {str(e)}")


@router.post("/education/courseware/assets")
async def upload_courseware_assets(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")
    lower_name = file.filename.lower()
    if not lower_name.endswith((".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg")):
        raise HTTPException(status_code=400, detail="仅支持图片文件或 ZIP 图片包")
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="上传的文件为空")
        assets = assets_from_upload(file_bytes, file.filename)
        return {
            "success": True,
            "asset_map": assets,
            "assets": list(assets.values()),
            "asset_count": len(assets),
            "uploaded_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片资源上传失败: {str(e)}")


@router.post("/education/courseware/projects")
async def save_courseware_project_route(request: CoursewareProjectSaveRequest):
    try:
        model = request.editable_model or {}
        tex_content = request.tex_content
        if not tex_content and model:
            tex_content = serialize_editable_model_to_tex(model, title=request.title)
        record = save_courseware_project(
            {
                "project_id": request.project_id,
                "title": request.title,
                "editable_model": model,
                "asset_map": request.asset_map,
                "slides": request.slides,
                "tex_content": tex_content or "",
                "ppt_artifact": request.ppt_artifact,
                "source_node_ids": request.source_node_ids or [],
            }
        )
        return {"success": True, "project": record, "project_id": record["id"], "message": "课件项目保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"课件项目保存失败: {str(e)}")


@router.get("/education/courseware/projects")
async def list_courseware_projects_route():
    try:
        return {"success": True, "projects": list_courseware_projects()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"课件项目列表读取失败: {str(e)}")


@router.get("/education/courseware/projects/{project_id}")
async def load_courseware_project_route(project_id: str):
    try:
        record = load_courseware_project(project_id)
        if not record:
            raise HTTPException(status_code=404, detail="课件项目不存在")
        return {"success": True, "project": record}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"课件项目读取失败: {str(e)}")


@router.post("/education/courseware/export-pptx")
async def export_courseware_pptx(request: CoursewareExportPptxRequest):
    try:
        model = request.editable_model or {}
        if not model.get("slides"):
            raise HTTPException(status_code=400, detail="缺少可导出的课件页面")
        title = request.title or str(model.get("title") or "未命名课件")
        artifact = build_pptx_artifact_from_editable_model(
            title,
            model,
            source_node_ids=_normalize_source_node_ids(None, request.source_node_ids),
        )
        return {"success": True, "ppt_artifact": artifact, "artifact": artifact}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPTX 导出失败: {str(e)}")
