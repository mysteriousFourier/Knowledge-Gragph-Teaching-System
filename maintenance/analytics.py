"""Graph analytics: degree analysis, type distribution, relation audit."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from KGTS.core.mcp_client import call_mcp_tool
from KGTS.core.bridge import build_frontend_graph


async def compute_graph_analytics() -> Dict[str, Any]:
    stats = await call_mcp_tool("get_graph_statistics", {})
    graph = build_frontend_graph()
    nodes = graph.get("nodes", [])
    relations = graph.get("relations", [])

    node_degrees: Dict[str, Dict[str, int]] = {}
    for node in nodes:
        node_degrees[node["id"]] = {"in_degree": 0, "out_degree": 0, "total_degree": 0}

    for rel in relations:
        source_id = rel.get("source_id")
        target_id = rel.get("target_id")
        if source_id in node_degrees:
            node_degrees[source_id]["out_degree"] += 1
            node_degrees[source_id]["total_degree"] += 1
        if target_id in node_degrees:
            node_degrees[target_id]["in_degree"] += 1
            node_degrees[target_id]["total_degree"] += 1

    sorted_nodes = sorted(
        node_degrees.items(),
        key=lambda x: x[1]["total_degree"],
        reverse=True,
    )
    top_nodes = sorted_nodes[:5]

    type_distribution: Dict[str, int] = {}
    for node in nodes:
        node_type = node.get("type", "unknown")
        type_distribution[node_type] = type_distribution.get(node_type, 0) + 1

    relation_distribution: Dict[str, int] = {}
    for rel in relations:
        rel_type = rel.get("relation_type", "unknown")
        relation_distribution[rel_type] = relation_distribution.get(rel_type, 0) + 1

    enhanced_stats = {
        **stats,
        "node_degree_analysis": {
            "average_degree": sum(d["total_degree"] for d in node_degrees.values()) / len(node_degrees) if node_degrees else 0,
            "max_degree": max((d["total_degree"] for d in node_degrees.values()), default=0),
            "min_degree": min((d["total_degree"] for d in node_degrees.values()), default=0),
            "top_nodes": [
                {
                    "node_id": node_id,
                    "node_label": next((n.get("content", node_id) for n in nodes if n.get("id") == node_id), node_id)[:50],
                    "degree": degree_data,
                }
                for node_id, degree_data in top_nodes
            ],
        },
        "type_distribution": type_distribution,
        "relation_distribution": relation_distribution,
    }
    return enhanced_stats


def compute_relation_audit(
    preset_relation_types: set[str] | None = None,
) -> Dict[str, Any]:
    if preset_relation_types is None:
        preset_relation_types = {
            "contains", "precedes", "references_formula", "references_table",
            "references", "defines", "explains", "derives", "depends_on",
            "supports", "contrasts_with", "example_of", "applies_to",
            "equivalent_to", "causes", "related",
        }

    graph = build_frontend_graph()
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

    isolated: List[Dict[str, Any]] = [
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
        "node_count": node_count,
        "relation_count": relation_count,
        "type_counts": dict(sorted(type_counts.items())),
        "structural_count": structural_count,
        "semantic_count": semantic_count,
        "semantic_candidate_count": semantic_candidate_count,
        "avg_degree": round((relation_count * 2) / node_count, 2) if node_count else 0,
        "isolated_count": len(isolated),
        "isolated_nodes": isolated[:40],
        "missing_preset_types": sorted(preset_relation_types - present_types),
        "coverage_note": "Structural/reference relations are deterministic. Semantic relations are generated candidates and are not guaranteed exhaustive.",
    }
