"""Graph data formatting helpers for API responses."""

from __future__ import annotations

import json
from typing import Any

from KGTS.core.graph_service import GraphService


def graph_nodes(graph: GraphService, limit: int = 5000) -> list[dict[str, Any]]:
    nodes = graph.read_graph().get("nodes", [])[:limit]
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


def graph_relationships(graph: GraphService, limit: int = 10000) -> list[dict[str, Any]]:
    relations = graph.read_graph().get("relations", [])[:limit]
    results: list[dict[str, Any]] = []
    for relation in relations:
        metadata = relation.get("metadata") or relation.get("properties") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        metadata = metadata if isinstance(metadata, dict) else {}
        source_id = (
            relation.get("source_id")
            or relation.get("source")
            or relation.get("source_node")
            or relation.get("sourceId")
            or relation.get("sourceNode")
            or relation.get("from")
            or metadata.get("source_id")
            or metadata.get("source")
            or metadata.get("source_node")
            or metadata.get("sourceId")
            or metadata.get("sourceNode")
            or metadata.get("from")
        )
        target_id = (
            relation.get("target_id")
            or relation.get("target")
            or relation.get("target_node")
            or relation.get("targetId")
            or relation.get("targetNode")
            or relation.get("to")
            or metadata.get("target_id")
            or metadata.get("target")
            or metadata.get("target_node")
            or metadata.get("targetId")
            or metadata.get("targetNode")
            or metadata.get("to")
        )
        relation_type = relation.get("relation_type") or relation.get("type") or relation.get("label") or metadata.get("relation_type") or metadata.get("type") or metadata.get("label") or "related"
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
