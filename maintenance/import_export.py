"""Graph import/export operations."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional

from KGTS.core.bridge import (
    build_frontend_graph,
    import_graph_payload,
    import_graphml_payload,
)


async def import_graph(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    result = import_graph_payload(graph_data)
    input_nodes = graph_data.get("nodes", [])
    input_edges = graph_data.get("edges", graph_data.get("relations", []))
    node_success = int(result.get("nodes", {}).get("success", 0))
    edge_success = int(result.get("relations", {}).get("success", 0))
    return {
        "data": result,
        "imported_nodes": [
            {
                "id": node.get("id"),
                "label": node.get("label") or node.get("id"),
                "type": node.get("type", "concept"),
                "status": "success" if index < node_success else "failed",
            }
            for index, node in enumerate(input_nodes)
        ],
        "imported_edges": [
            {
                "source": edge.get("source") or edge.get("source_id"),
                "target": edge.get("target") or edge.get("target_id"),
                "type": edge.get("type") or edge.get("relation_type", "related"),
                "status": "success" if index < edge_success else "failed",
            }
            for index, edge in enumerate(input_edges)
        ],
        "total_nodes": len(input_nodes),
        "total_edges": len(input_edges),
    }


async def import_graphml(
    file_path: Optional[str] = None,
    file_content: Optional[str] = None,
    graph_name: Optional[str] = None,
) -> Dict[str, Any]:
    result = import_graphml_payload(
        file_path=file_path,
        file_content=file_content,
    )
    return {
        "data": result,
        "graph_name": graph_name,
    }


async def visualize_graphml(
    file_path: Optional[str] = None,
    file_content: Optional[str] = None,
    max_nodes: Optional[int] = None,
) -> Dict[str, Any]:
    resolved_path = None
    if file_content:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".graphml", delete=False, encoding="utf-8"
        ) as temp_file:
            temp_file.write(file_content)
            resolved_path = temp_file.name
    elif file_path:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        resolved_path = file_path
    else:
        raise ValueError("Must provide file_path or file_content")

    try:
        from KGTS.core.bridge import call_backend_tool
        data = call_backend_tool("parse_graphml_to_vis_json", {"file_path": resolved_path})

        if max_nodes and max_nodes > 0:
            keep_ids = set(n["id"] for n in data["nodes"][:max_nodes])
            data["nodes"] = [n for n in data["nodes"] if n["id"] in keep_ids]
            data["edges"] = [e for e in data["edges"] if e["from"] in keep_ids and e["to"] in keep_ids]
            data["stats"]["node_count"] = len(data["nodes"])
            data["stats"]["edge_count"] = len(data["edges"])

        return data
    finally:
        if file_content and resolved_path:
            try:
                os.unlink(resolved_path)
            except Exception:
                pass


async def export_graph() -> Dict[str, Any]:
    return build_frontend_graph()


async def export_teacher_package() -> Dict[str, Any]:
    from KGTS.maintenance.structured_sync import build_teacher_package, TEACHER_PACKAGE_PATH

    package = build_teacher_package()
    return {
        "data": package,
        "file_path": str(TEACHER_PACKAGE_PATH),
    }
