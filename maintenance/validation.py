"""Graph validation: integrity and consistency checks."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from KGTS.core.mcp_client import call_mcp_tool


async def validate_graph() -> Dict[str, Any]:
    stats = await call_mcp_tool("get_graph_statistics", {})
    graph_stats = json.loads(stats) if isinstance(stats, str) else stats

    issues: List[str] = []

    if graph_stats.get("nodes", {}).get("total", 0) > 0:
        total_relations = graph_stats.get("relations", {}).get("total", 0)
        if total_relations == 0:
            issues.append("警告: 图谱中没有关系，所有节点都是孤立的")

    density = graph_stats.get("connectivity", {}).get("density", 0)
    if density < 0.01:
        issues.append(f"警告: 图谱连接密度过低 ({density:.4f})，可能存在许多孤立节点")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "statistics": graph_stats,
    }
