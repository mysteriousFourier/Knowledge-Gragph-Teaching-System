from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from KGTS.models.education import (
    GenerateLectureRequest,
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
        try:
            graph_data = await call_mcp_tool("read_graph")
            if isinstance(graph_data, dict):
                graph_data = build_frontend_graph(graph_data)
        except Exception:
            try:
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
        chapter_data = {
            "id": request.chapter_id,
            "title": chapter_title,
            "content": chapter_content,
        }
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
            sync_backend=False,
        )
        saved_chapter = chapter_store.save_lecture(
            chapter_id=request.chapter_id,
            lecture_content=lecture_content,
            learning_plan=learning_plan,
            consistency_report=consistency_report,
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
        chapter_data = chapter_store.save_chapter(
            title=request.title,
            content=request.content,
            graph_data=request.graph_data,
            chapter_id=request.chapter_id,
            source_type=request.source_type,
            ppt_slides=request.ppt_slides,
            slide_lectures=request.slide_lectures,
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
            ppt_slides=request.ppt_slides,
            slide_lectures=request.slide_lectures,
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
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    if not file.filename.lower().endswith((".pptx", ".ppt")):
        raise HTTPException(status_code=400, detail="仅支持 .pptx 和 .ppt 格式的 PPT 文件")

    try:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")

        if len(file_bytes) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件大小超过 50MB 限制")

        from KGTS.education.ppt_parser import parse_ppt, build_ppt_lecture_prompt_data

        parse_result = parse_ppt(file_bytes)
        if not parse_result.get("success"):
            raise HTTPException(status_code=400, detail=parse_result.get("error", "PPT 解析失败"))

        prompt_data = build_ppt_lecture_prompt_data(parse_result)

        chapter_title = prompt_data["chapter_title"]
        chapter_content = prompt_data["chapter_content"]
        slide_details = prompt_data["slide_details"]

        if not chapter_content.strip():
            return {
                "success": True,
                "chapter_title": chapter_title,
                "slide_count": prompt_data["total_slides"],
                "slides": slide_details,
                "full_text": chapter_content,
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
                "warning": "PPT 中未提取到有效文本内容，可能是纯图片幻灯片",
            }

        graph_data = None
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
            "id": f"ppt_{hashlib.md5(file.filename.encode()).hexdigest()[:12]}",
            "title": chapter_title,
            "content": chapter_content,
        }
        lecture_learning_plan = _build_ppt_learning_plan(
            chapter_title=chapter_title,
            chapter_content=chapter_content,
            graph_data=graph_data if isinstance(graph_data, dict) else None,
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
        )
        lecture_consistency_report = _safe_consistency_report(lecture_content, lecture_learning_plan, task="lecture")

        return {
            "success": True,
            "chapter_title": chapter_title,
            "slide_count": prompt_data["total_slides"],
            "slides": slide_details,
            "full_text": chapter_content,
            "lecture_content": lecture_content,
            "slide_lectures": slide_lectures,
            "learning_plan": lecture_learning_plan,
            "graph_paths": lecture_graph_paths,
            "formula_context": lecture_formula_context,
            "consistency_report": lecture_consistency_report,
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
        raise HTTPException(status_code=500, detail=f"PPT 处理失败: {str(e)}")


async def _generate_per_slide_lectures(
    client: DeepSeekAPIClient,
    slide_details: List[Dict],
    style: str,
    chapter_title: str,
    graph_data: Optional[Dict[str, Any]] = None,
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
            "content": slide_text,
        }
        learning_plan = _build_ppt_learning_plan(
            chapter_title=chapter_title,
            chapter_content=slide_text,
            graph_data=graph_data,
            chapter_data=chapter_data,
            query=f"{chapter_title}\n{slide_text[:800]}",
        )
        sources = learning_plan.get("evidence") or []
        if not sources:
            try:
                rag = build_rag_context(f"{chapter_title}\n{slide_text[:800]}", limit=4)
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
        graph_paths = graph_paths_for_evidence(graph_data, learning_plan.get("evidence") or [], limit=8)
        formula_context = formula_context_for_text(slide_text, limit=8)

        requirements = [
            *build_lecture_gc_dpg_requirements(style, slide_level=True),
            "Explain this slide in accessible classroom language.",
            "Add only the background needed to make the slide teachable; keep unsupported extensions bounded.",
            "Use the graph relation paths as the main teaching order when they are relevant.",
            "If formulas appear, explain the meaning of the main symbols.",
            "When the same symbol can mean different things elsewhere, explain only the meaning in this slide/chapter scope.",
            "If a formula is derived from earlier formulas, mention the immediate derivation dependency in teacher-friendly language.",
            "Include 1-2 natural classroom questions when useful.",
            "Output directly usable Markdown prose for this slide.",
        ]
        requirement_text = "\n".join(
            f"{index}. {item}" for index, item in enumerate(requirements, start=1)
        )
        prompt = f"""You are a teacher. Generate the lecture script for one PPT slide.

Chapter topic: {chapter_title}
Current slide: {slide['index']}

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
) -> Dict[str, Any]:
    chapter_payload = chapter_data or {"title": chapter_title, "content": chapter_content}
    search_query = query or f"{chapter_title}\n{chapter_content[:1200]}"
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
        evidence = [slide_evidence] + [
            item for item in evidence if isinstance(item, dict) and item.get("id") != slide_evidence["id"]
        ]
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

    if not file.filename.lower().endswith((".pptx", ".ppt")):
        raise HTTPException(status_code=400, detail="仅支持 .pptx 和 .ppt 格式")

    try:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")

        from KGTS.education.ppt_parser import parse_ppt, build_ppt_lecture_prompt_data

        parse_result = parse_ppt(file_bytes)
        if not parse_result.get("success"):
            raise HTTPException(status_code=400, detail=parse_result.get("error", "PPT 解析失败"))

        prompt_data = build_ppt_lecture_prompt_data(parse_result)

        return {
            "success": True,
            "chapter_title": prompt_data["chapter_title"],
            "slide_count": prompt_data["total_slides"],
            "slides": prompt_data["slide_details"],
            "full_text": prompt_data["chapter_content"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPT 预览失败: {str(e)}")
