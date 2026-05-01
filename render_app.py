from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
EDUCATION_DIR = BACKEND_DIR / "education"
MAINTENANCE_DIR = BACKEND_DIR / "maintenance"
VECTOR_DIR = BACKEND_DIR / "vector_index_system"
GRAPH_ADMIN_HTML = VECTOR_DIR / "knowledge_graph" / "backend_admin.html"


for path in (ROOT_DIR, BACKEND_DIR, EDUCATION_DIR, MAINTENANCE_DIR, VECTOR_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from app_config import load_root_env  # noqa: E402


load_root_env()

from graph_service import GraphService, PRESET_RELATION_TYPES  # noqa: E402
from backend.maintenance.structured_sync import scan_structured_sources  # noqa: E402

# Import after sys.path setup. These modules keep the existing teacher/student API
# behavior, while this file only adapts how they are served on Render.
from backend.education import api_server as education_api  # noqa: E402
from backend.maintenance import api_server as maintenance_api  # noqa: E402


app = FastAPI(
    title="Knowledge-Gragph-Teaching-System",
    description="Single FastAPI web service for Render deployment.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _append_api_routes(source_app: FastAPI, *, skip_paths: Iterable[str] = ()) -> None:
    skipped = set(skip_paths)
    for route in source_app.router.routes:
        route_path = getattr(route, "path", "")
        if route_path.startswith("/api/") and route_path not in skipped:
            app.router.routes.append(route)


def _graph_db_path() -> str | None:
    explicit = os.getenv("GRAPH_DB_PATH") or os.getenv("KNOWLEDGE_GRAPH_DB_PATH")
    if explicit:
        return explicit
    data_dir = os.getenv("APP_DATA_DIR")
    if data_dir:
        return str(Path(data_dir) / "knowledge_graph.db")
    return None


def _graph() -> GraphService:
    return GraphService(db_path=_graph_db_path())


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _ensure_structured_graph() -> None:
    if not _env_flag("RENDER_AUTO_SYNC_STRUCTURED", True):
        return

    graph = _graph()
    stats = graph.read_graph().get("stats", {})
    node_count = int(stats.get("node_count") or 0)
    min_nodes = int(os.getenv("RENDER_AUTO_SYNC_MIN_NODES", "20"))
    if node_count >= min_nodes:
        return

    result = scan_structured_sources(force=True)
    summary = result.get("package_summary") or {}
    print(
        "[render] structured graph sync completed: "
        f"nodes={summary.get('node_count', 'unknown')}, "
        f"edges={summary.get('edge_count', 'unknown')}"
    )


@app.on_event("startup")
async def startup_sync_structured_graph() -> None:
    _ensure_structured_graph()


def _graph_nodes(limit: int = 5000) -> list[dict[str, Any]]:
    nodes = _graph().read_graph().get("nodes", [])[:limit]
    results: list[dict[str, Any]] = []
    for node in nodes:
        metadata = node.get("metadata") or {}
        results.append(
            {
                "id": node.get("id"),
                "label": metadata.get("label") or node.get("label") or node.get("id"),
                "type": node.get("type"),
                "content": node.get("content"),
                "source": metadata.get("source"),
                "confidence": metadata.get("confidence", 1.0),
                "created_at": node.get("created_at"),
                "updated_at": node.get("updated_at"),
                "reviewed": bool(metadata.get("reviewed")),
                "metadata": metadata,
            }
        )
    return results


def _graph_relationships(limit: int = 10000) -> list[dict[str, Any]]:
    relations = _graph().read_graph().get("relations", [])[:limit]
    results: list[dict[str, Any]] = []
    for relation in relations:
        metadata = relation.get("metadata") or {}
        source_id = relation.get("source_id") or relation.get("source_node")
        target_id = relation.get("target_id") or relation.get("target_node")
        relation_type = relation.get("relation_type") or relation.get("type") or "related"
        results.append(
            {
                "id": relation.get("id"),
                "source_node": source_id,
                "target_node": target_id,
                "source_id": source_id,
                "target_id": target_id,
                "source": source_id,
                "target": target_id,
                "type": relation_type,
                "relation_type": relation_type,
                "strength": relation.get("similarity", 1.0),
                "description": metadata.get("description", ""),
                "source_file": metadata.get("source"),
                "created_at": relation.get("created_at"),
                "updated_at": relation.get("updated_at"),
                "reviewed": bool(metadata.get("reviewed")),
                "metadata": metadata,
            }
        )
    return results


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "render-single-fastapi",
        "graph_db_path": _graph_db_path() or "default",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


def _frontend_file_response(path: Path, media_type: str | None = None) -> FileResponse:
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def frontend_home() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend home page is missing.")
    return _frontend_file_response(index_path, "text/html; charset=utf-8")


@app.get("/env-config.js", include_in_schema=False)
async def frontend_runtime_config() -> Response:
    overrides = {
        "education": os.getenv("EDUCATION_API_BASE_URL", ""),
        "maintenance": os.getenv("MAINTENANCE_API_BASE_URL", ""),
        "admin": os.getenv("BACKEND_ADMIN_BASE_URL", ""),
    }
    body = f"""
(function () {{
  var origin = window.location.origin;
  window.__APP_CONFIG__ = Object.freeze({{
    educationApiBaseUrl: {json.dumps(overrides["education"])} || origin,
    maintenanceApiBaseUrl: {json.dumps(overrides["maintenance"])} || origin,
    backendAdminBaseUrl: {json.dumps(overrides["admin"])} || origin
  }});
}})();
""".strip()
    return Response(
        content=body,
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
@app.get("/backend/vector_index_system/knowledge_graph/backend_admin.html", include_in_schema=False)
async def graph_admin_page() -> FileResponse:
    if not GRAPH_ADMIN_HTML.exists():
        raise HTTPException(status_code=404, detail="Graph admin page is missing.")
    return FileResponse(GRAPH_ADMIN_HTML)


@app.get("/backend/vector_index_system/knowledge_graph/", include_in_schema=False)
async def legacy_graph_admin_dir() -> RedirectResponse:
    return RedirectResponse("/admin", status_code=307)


@app.get("/api/graph")
async def graph_data() -> dict[str, Any]:
    return {"success": True, "data": _graph().read_graph()}


@app.get("/api/relation-audit")
async def relation_audit() -> dict[str, Any]:
    graph = _graph().read_graph()
    nodes = graph.get("nodes", [])
    relations = graph.get("relations", [])
    structural_types = {"contains", "precedes", "references_formula", "references_table"}
    type_counts = Counter(relation.get("relation_type") or "related" for relation in relations)
    degree: Counter[str] = Counter()
    semantic_candidate_count = 0

    for relation in relations:
        source_id = relation.get("source_id")
        target_id = relation.get("target_id")
        if source_id:
            degree[source_id] += 1
        if target_id:
            degree[target_id] += 1
        metadata = relation.get("metadata") or {}
        if metadata.get("relation_source") == "semantic_candidate":
            semantic_candidate_count += 1

    isolated = [
        {
            "id": node.get("id"),
            "label": (node.get("metadata") or {}).get("label") or node.get("label") or node.get("id"),
            "type": node.get("type"),
        }
        for node in nodes
        if degree[node.get("id")] == 0
    ]
    structural_count = sum(count for rel_type, count in type_counts.items() if rel_type in structural_types)
    semantic_count = len(relations) - structural_count
    node_count = len(nodes)
    relation_count = len(relations)
    present_types = set(type_counts)

    return {
        "success": True,
        "audit": {
            "node_count": node_count,
            "relation_count": relation_count,
            "type_counts": dict(sorted(type_counts.items())),
            "structural_count": structural_count,
            "semantic_count": semantic_count,
            "semantic_candidate_count": semantic_candidate_count,
            "avg_degree": round((relation_count * 2) / node_count, 2) if node_count else 0,
            "isolated_count": len(isolated),
            "isolated_nodes": isolated[:40],
            "missing_preset_types": sorted(PRESET_RELATION_TYPES - present_types),
            "coverage_note": "Structural/reference relations are deterministic. Semantic relations are generated candidates and are not guaranteed exhaustive.",
        },
    }


@app.get("/api/node")
async def get_graph_node(node_id: str = Query("", alias="node_id"), id: str = Query("", alias="id")) -> dict[str, Any]:
    target_id = node_id or id
    if not target_id:
        return {"success": False, "error": "node_id is required"}
    node = _graph().get_node(target_id)
    return {"success": bool(node), "node": node or {}}


@app.get("/api/relations")
async def get_graph_relations(node_id: str = "") -> dict[str, Any]:
    relations = _graph().get_relations(node_id=node_id or None)
    return {"success": True, "relations": relations, "count": len(relations)}


@app.get("/api/nodes")
async def get_legacy_nodes() -> dict[str, Any]:
    nodes = _graph_nodes()
    return {"success": True, "nodes": nodes, "count": len(nodes)}


@app.get("/api/relationships")
async def get_legacy_relationships() -> dict[str, Any]:
    relationships = _graph_relationships()
    return {"success": True, "relationships": relationships, "count": len(relationships)}


@app.get("/api/stats")
async def get_legacy_stats() -> dict[str, Any]:
    stats = _graph().get_graph_statistics()
    return {
        "total_nodes": stats.get("nodes", {}).get("total", 0),
        "total_relationships": stats.get("relations", {}).get("total", 0),
        "details": stats,
    }


@app.get("/api/search/{search_term}")
async def search_legacy_nodes(search_term: str) -> dict[str, Any]:
    nodes = _graph().search_nodes(search_term, limit=5000)
    return {"success": True, "nodes": nodes, "count": len(nodes), "search_term": search_term}


@app.get("/api/filter/{filter_type}")
async def filter_legacy_nodes(filter_type: str) -> dict[str, Any]:
    nodes = _graph().search_nodes("", node_type=filter_type, limit=5000)
    return {"success": True, "nodes": nodes, "count": len(nodes), "filter_type": filter_type}


@app.post("/api/update-node")
async def update_graph_node(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("node_id"):
        return {"success": False, "error": "node_id is required"}
    return _graph().update_node(
        payload["node_id"],
        payload.get("content"),
        payload.get("metadata"),
    )


@app.post("/api/update-relation")
async def update_graph_relation(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("relation_id"):
        return {"success": False, "error": "relation_id is required"}
    return _graph().update_relation(
        payload["relation_id"],
        payload.get("source_id"),
        payload.get("target_id"),
        payload.get("relation_type"),
        payload.get("metadata"),
        payload.get("similarity"),
    )


_append_api_routes(education_api.app, skip_paths={"/api/health"})
_append_api_routes(maintenance_api.app, skip_paths={"/api/health"})

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/", include_in_schema=False)
    async def missing_frontend() -> JSONResponse:
        return JSONResponse({"success": False, "error": "frontend directory is missing"}, status_code=404)
