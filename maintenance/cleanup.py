"""Graph cleanup: find and delete orphan nodes."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from KGTS.core.mcp_client import call_mcp_tool


async def clean_orphan_nodes() -> Dict[str, Any]:
    graph_data = await call_mcp_tool("read_graph", {})
    graph = json.loads(graph_data) if isinstance(graph_data, str) else graph_data

    nodes_with_relations: set[str] = set()
    for rel in graph.get("relations", []):
        nodes_with_relations.add(rel.get("source_id"))
        nodes_with_relations.add(rel.get("target_id"))

    orphans: List[str] = []
    for node in graph.get("nodes", []):
        if node.get("id") not in nodes_with_relations:
            orphans.append(node.get("id"))

    deleted_count = 0
    for node_id in orphans:
        try:
            await call_mcp_tool("delete_memory", {"node_id": node_id})
            deleted_count += 1
        except Exception:
            pass

    return {
        "deleted_count": deleted_count,
        "orphans_found": len(orphans),
    }
