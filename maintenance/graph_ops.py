"""Graph CRUD operations: add/update/delete nodes and relations, queries, search."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from KGTS.core.mcp_client import call_mcp_tool
from KGTS.core.seed import ensure_seed_graph
from KGTS.core.graph_service import GraphService
from KGTS.core.bridge import (
    build_frontend_graph,
    call_backend_tool,
    get_graph_schema,
    normalize_frontend_node,
    normalize_frontend_relation,
    search_nodes as bridge_search_nodes,
)

VISUALIZATION_STRUCTURAL_NODE_TYPES = {"part", "chapter", "appendix"}
VISUALIZATION_RESOURCE_NODE_TYPES = {"formula", "theorem", "table", "example", "figure"}
VISUALIZATION_RESOURCE_ID_PREFIXES = ("formula::", "table::", "example::", "figure::")


async def add_node(
    content: str,
    type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Any:
    return await call_mcp_tool(
        "add_memory",
        {"content": content, "type": type, "metadata": metadata},
    )


async def update_node(
    node_id: str,
    content: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Any:
    return await call_mcp_tool(
        "update_memory",
        {"node_id": node_id, "content": content, "metadata": metadata},
    )


async def delete_node(node_id: str) -> Any:
    return await call_mcp_tool("delete_memory", {"node_id": node_id})


async def add_relation(
    source_id: str,
    target_id: str,
    relation_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    similarity: Optional[float] = None,
) -> Any:
    return await call_mcp_tool(
        "add_relation",
        {
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "metadata": metadata,
            "similarity": similarity,
        },
    )


async def update_relation(
    relation_id: str,
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    relation_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    similarity: Optional[float] = None,
) -> Any:
    return await call_mcp_tool(
        "update_relation",
        {
            "relation_id": relation_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "metadata": metadata,
            "similarity": similarity,
        },
    )


async def get_node(node_id: str) -> Dict[str, Any]:
    result = await call_mcp_tool("get_node", {"node_id": node_id})
    if isinstance(result, dict):
        return normalize_frontend_node(result)
    return result


async def get_graph() -> Dict[str, Any]:
    ensure_seed_graph()
    return build_frontend_graph()


async def list_nodes(
    limit: int = 5000,
    include_content: bool = False,
    node_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    ensure_seed_graph()
    result = call_backend_tool(
        "list_nodes",
        {"limit": limit, "include_content": include_content, "node_types": node_types},
    )
    nodes = result if isinstance(result, list) else []
    return {"nodes": [normalize_frontend_node(node) for node in nodes if isinstance(node, dict)], "count": len(nodes)}


async def list_relationships(
    limit: int = 10000,
    relation_type: Optional[str] = None,
    include_metadata: bool = False,
) -> Dict[str, Any]:
    ensure_seed_graph()
    result = call_backend_tool(
        "list_relationships",
        {
            "limit": limit,
            "relation_type": relation_type,
            "include_metadata": include_metadata,
        },
    )
    relationships = result if isinstance(result, list) else []
    return {
        "relationships": [
            normalize_frontend_relation(relation)
            for relation in relationships
            if isinstance(relation, dict)
        ],
        "count": len(relationships),
    }


async def get_scope_tree() -> Dict[str, Any]:
    ensure_seed_graph()
    graph = GraphService()
    scope_types = {"appendix", "chapter", "part", "section"}
    scope_metadata_keys = {
        "label",
        "chapter",
        "source_unit",
        "block_index",
        "toc_page",
        "toc_level",
        "toc_node_id",
        "toc_entry_type",
        "toc_parent_id",
        "heading_level",
        "heading_depth",
        "book_part_id",
        "part_number",
        "chapter_number",
        "role",
    }
    nodes = []
    node_ids = set()
    for item in graph.list_nodes(limit=20000, include_content=False):
        metadata = item.get("metadata") or {}
        node_id = str(item.get("id") or "")
        if not node_id:
            continue
        if (
            node_id == "toc::root"
            or node_id.startswith("toc::")
            or str(item.get("type") or "") in scope_types
            or str(metadata.get("role") or "") in {"chapter_root", "heading", "toc_entry"}
        ):
            node_ids.add(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "label": item.get("label") or node_id,
                    "type": item.get("type") or "concept",
                    "confidence": item.get("confidence", 1.0),
                    "reviewed": bool(item.get("reviewed")),
                    "metadata": {
                        key: value
                        for key, value in metadata.items()
                        if key in scope_metadata_keys
                    },
                }
            )

    relationships = []
    seen = set()
    for relation in graph.list_relationships_by_type("contains", limit=50000, include_metadata=False):
        source_id = str(relation.get("source_id") or relation.get("source_node") or "")
        target_id = str(relation.get("target_id") or relation.get("target_node") or "")
        if source_id not in node_ids or target_id not in node_ids:
            continue
        key = (source_id, target_id, str(relation.get("relation_type") or relation.get("type") or "contains"))
        if key in seen:
            continue
        seen.add(key)
        relationships.append(
            {
                "id": relation.get("id"),
                "source_id": source_id,
                "target_id": target_id,
                "source": source_id,
                "target": target_id,
                "source_node": source_id,
                "target_node": target_id,
                "type": "contains",
                "relation_type": "contains",
                "similarity": relation.get("similarity", 1.0),
                "description": "",
                "reviewed": bool(relation.get("reviewed")),
                "metadata": {},
            }
        )

    return {
        "nodes": nodes,
        "relationships": relationships,
        "count": len(nodes),
        "relationship_count": len(relationships),
    }


def _node_metadata_subset(metadata: Dict[str, Any]) -> Dict[str, Any]:
    keys = {
        "label",
        "source",
        "source_file",
        "chapter",
        "source_unit",
        "block_index",
        "toc_page",
        "toc_level",
        "toc_node_id",
        "toc_entry_type",
        "heading_depth",
        "book_part_id",
        "chapter_number",
        "role",
    }
    return {key: value for key, value in metadata.items() if key in keys and value is not None}


def _visualization_node(item: Dict[str, Any]) -> Dict[str, Any]:
    metadata = item.get("metadata") or {}
    label = item.get("label") or metadata.get("label") or item.get("id") or ""
    content = str(item.get("content") or "")
    return {
        "id": str(item.get("id") or ""),
        "label": label,
        "type": item.get("type") or "concept",
        "content": content[:800],
        "source": item.get("source") or metadata.get("source"),
        "confidence": item.get("confidence", metadata.get("confidence", 1.0)),
        "reviewed": bool(item.get("reviewed") or metadata.get("reviewed")),
        "metadata": _node_metadata_subset(metadata),
    }


def _visualization_relation(relation: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(relation.get("source_id") or relation.get("source_node") or relation.get("source") or "")
    target_id = str(relation.get("target_id") or relation.get("target_node") or relation.get("target") or "")
    relation_type = str(relation.get("relation_type") or relation.get("type") or "related")
    description = str(relation.get("description") or "")
    return {
        "id": str(relation.get("id") or f"{source_id}->{relation_type}->{target_id}"),
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "similarity": relation.get("similarity", relation.get("strength", 1.0)),
        "description": description[:240],
        "reviewed": bool(relation.get("reviewed")),
        "metadata": {},
    }


def _visualization_relation_priority(
    relation: Dict[str, Any],
    node_by_id: Dict[str, Dict[str, Any]],
    degree: Counter[str],
) -> int:
    relation_type = str(relation.get("relation_type") or relation.get("type") or "related")
    type_weight = {
        "precedes": 9000,
        "references_formula": 8400,
        "references_table": 8200,
        "references_figure": 8100,
        "references_example": 8000,
        "derives": 7600,
        "defines": 7000,
        "explains": 6200,
        "depends_on": 5800,
        "example_of": 5200,
        "supports": 4600,
        "causes": 4400,
        "contrasts_with": 3600,
        "related": 2200,
        "contains": 1200,
    }.get(relation_type, 2400)
    source_id = str(relation.get("source_id") or "")
    target_id = str(relation.get("target_id") or "")
    source_type = str((node_by_id.get(source_id) or {}).get("type") or "")
    target_type = str((node_by_id.get(target_id) or {}).get("type") or "")
    endpoint_weight = 0
    if source_type in {"chapter", "appendix", "part"}:
        endpoint_weight += 140
    if target_type in {"chapter", "appendix", "part"}:
        endpoint_weight += 140
    if _is_visualization_resource_node(source_id, node_by_id.get(source_id)):
        endpoint_weight += 220
    if _is_visualization_resource_node(target_id, node_by_id.get(target_id)):
        endpoint_weight += 220
    return type_weight + endpoint_weight + (degree[source_id] + degree[target_id]) * 3


def _is_visualization_structural_node(node_id: str, node: Optional[Dict[str, Any]]) -> bool:
    metadata = (node or {}).get("metadata") or {}
    node_type = str((node or {}).get("type") or "")
    return (
        node_id == "toc::root"
        or node_type in VISUALIZATION_STRUCTURAL_NODE_TYPES
        or metadata.get("role") == "chapter_root"
    )


def _is_visualization_resource_node(node_id: str, node: Optional[Dict[str, Any]]) -> bool:
    node_type = str((node or {}).get("type") or "")
    return node_type in VISUALIZATION_RESOURCE_NODE_TYPES or node_id.startswith(VISUALIZATION_RESOURCE_ID_PREFIXES)


def _visualization_node_priority(
    node_id: str,
    node_by_id: Dict[str, Dict[str, Any]],
    degree: Counter[str],
) -> int:
    node = node_by_id.get(node_id) or {}
    node_type = str(node.get("type") or "")
    if _is_visualization_resource_node(node_id, node):
        type_weight = {
            "formula": 9800,
            "theorem": 9600,
            "example": 8600,
            "figure": 7800,
            "table": 7600,
            "note": 7200,
        }.get(node_type, 7400)
    else:
        type_weight = {
            "chapter": 7000,
            "appendix": 6900,
            "part": 6800,
            "section": 4200,
            "proposition": 3900,
            "derivation": 3600,
            "discussion": 3200,
            "concept": 3000,
        }.get(node_type, 2400)
    return type_weight + degree[node_id] * 12


def _relation_key(relation: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(relation.get("source_id") or ""),
        str(relation.get("relation_type") or relation.get("type") or "related"),
        str(relation.get("target_id") or ""),
    )


async def get_visualization_graph(
    node_limit: int = 1500,
    relationship_limit: int = 5000,
) -> Dict[str, Any]:
    ensure_seed_graph()
    graph = GraphService()
    node_limit = max(10, min(int(node_limit or 1500), 3000))
    relationship_limit = max(20, min(int(relationship_limit or 5000), 12000))

    raw_nodes = graph.list_nodes(limit=20000, include_content=False)
    raw_relations = graph.list_relationships(limit=50000, include_metadata=False)
    node_by_id = {str(node.get("id") or ""): node for node in raw_nodes if node.get("id")}

    valid_relations = []
    degree: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    for relation in raw_relations:
        normalized = _visualization_relation(relation)
        source_id = normalized["source_id"]
        target_id = normalized["target_id"]
        if not source_id or not target_id or source_id not in node_by_id or target_id not in node_by_id:
            continue
        valid_relations.append(normalized)
        degree[source_id] += 1
        degree[target_id] += 1
        type_counts[normalized["relation_type"]] += 1

    selected_node_ids: set[str] = set()
    for node in raw_nodes:
        node_id = str(node.get("id") or "")
        if _is_visualization_structural_node(node_id, node):
            selected_node_ids.add(node_id)

    relation_type_quotas = {
        "precedes": 1600,
        "references_formula": 900,
        "references_table": 500,
        "references_figure": 400,
        "references_example": 400,
        "derives": 700,
        "defines": 600,
        "explains": 600,
        "depends_on": 600,
        "example_of": 500,
        "supports": 400,
        "causes": 260,
        "contrasts_with": 240,
        "related": 600,
        "contains": 2200,
    }
    selected_relations: list[Dict[str, Any]] = []
    selected_relation_keys: set[tuple[str, str, str]] = set()
    for relation_type, quota in relation_type_quotas.items():
        candidates = [
            relation
            for relation in valid_relations
            if relation["relation_type"] == relation_type
        ]
        candidates.sort(key=lambda item: _visualization_relation_priority(item, node_by_id, degree), reverse=True)
        for relation in candidates[:quota]:
            key = _relation_key(relation)
            if key in selected_relation_keys:
                continue
            selected_relation_keys.add(key)
            selected_relations.append(relation)
            selected_node_ids.add(relation["source_id"])
            selected_node_ids.add(relation["target_id"])

    if len(selected_node_ids) > node_limit:
        required_ids = {
            node_id
            for node_id in selected_node_ids
            if _is_visualization_structural_node(node_id, node_by_id.get(node_id))
        }
        available_after_required = max(0, node_limit - len(required_ids))
        resource_budget = min(available_after_required, max(24, min(420, node_limit // 3)))
        resource_ids = [
            node_id
            for node_id, node in node_by_id.items()
            if degree[node_id] and _is_visualization_resource_node(node_id, node)
        ]
        resource_ids.sort(
            key=lambda node_id: _visualization_node_priority(node_id, node_by_id, degree),
            reverse=True,
        )
        required_resource_ids = set(resource_ids[:resource_budget])

        resource_context_ids: list[str] = []
        seen_context_ids: set[str] = set()
        for relation in sorted(
            valid_relations,
            key=lambda item: _visualization_relation_priority(item, node_by_id, degree),
            reverse=True,
        ):
            if relation["source_id"] not in required_resource_ids and relation["target_id"] not in required_resource_ids:
                continue
            for endpoint_id in (relation["source_id"], relation["target_id"]):
                if endpoint_id in required_ids or endpoint_id in required_resource_ids or endpoint_id in seen_context_ids:
                    continue
                seen_context_ids.add(endpoint_id)
                resource_context_ids.append(endpoint_id)

        next_selected_node_ids: set[str] = set()

        def add_selected_node(node_id: str) -> None:
            if len(next_selected_node_ids) < node_limit and node_id in node_by_id:
                next_selected_node_ids.add(node_id)

        for node_id in sorted(required_ids, key=lambda item: _visualization_node_priority(item, node_by_id, degree), reverse=True):
            add_selected_node(node_id)
        for node_id in resource_ids:
            if node_id in required_resource_ids:
                add_selected_node(node_id)
        for node_id in resource_context_ids:
            add_selected_node(node_id)

        ranked_ids = sorted(
            selected_node_ids - next_selected_node_ids,
            key=lambda node_id: _visualization_node_priority(node_id, node_by_id, degree),
            reverse=True,
        )
        for node_id in ranked_ids:
            add_selected_node(node_id)
        selected_node_ids = next_selected_node_ids

    selected_resource_ids = {
        node_id
        for node_id in selected_node_ids
        if _is_visualization_resource_node(node_id, node_by_id.get(node_id))
    }
    for relation in sorted(
        valid_relations,
        key=lambda item: _visualization_relation_priority(item, node_by_id, degree),
        reverse=True,
    ):
        if relation["source_id"] not in selected_node_ids or relation["target_id"] not in selected_node_ids:
            continue
        if relation["source_id"] not in selected_resource_ids and relation["target_id"] not in selected_resource_ids:
            continue
        key = _relation_key(relation)
        if key in selected_relation_keys:
            continue
        selected_relation_keys.add(key)
        selected_relations.append(relation)

    selected_relations = [
        relation
        for relation in selected_relations
        if relation["source_id"] in selected_node_ids and relation["target_id"] in selected_node_ids
    ]
    selected_relations.sort(key=lambda item: _visualization_relation_priority(item, node_by_id, degree), reverse=True)
    selected_relations = selected_relations[:relationship_limit]

    nodes = [
        _visualization_node(node_by_id[node_id])
        for node_id in selected_node_ids
        if node_id in node_by_id
    ]
    nodes.sort(
        key=lambda node: (
            0 if node["id"] == "toc::root" else 1,
            str(node.get("type") or ""),
            str((node.get("metadata") or {}).get("chapter") or ""),
            str(node.get("label") or node.get("id") or ""),
        )
    )

    return {
        "nodes": nodes,
        "relationships": selected_relations,
        "relations": selected_relations,
        "edges": selected_relations,
        "count": len(nodes),
        "relationship_count": len(selected_relations),
        "stats": {
            "node_count": len(raw_nodes),
            "relation_count": len(valid_relations),
            "returned_node_count": len(nodes),
            "returned_relation_count": len(selected_relations),
            "truncated": len(raw_nodes) > len(nodes) or len(valid_relations) > len(selected_relations),
            "relation_type_counts": dict(sorted(type_counts.items())),
        },
    }


async def get_relations(
    node_id: Optional[str] = None,
    relation_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    result = await call_mcp_tool(
        "get_relations",
        {"node_id": node_id, "relation_type": relation_type},
    )
    relation_items = result.get("relations") if isinstance(result, dict) else result
    return [
        normalize_frontend_relation(item) if isinstance(item, dict) else item
        for item in (relation_items if isinstance(relation_items, list) else [])
    ]


async def get_schema() -> Dict[str, Any]:
    return get_graph_schema()


async def search_nodes(
    keyword: str,
    node_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    return bridge_search_nodes(keyword, node_type=node_type, limit=limit)


async def semantic_search(
    query: str,
    node_type: Optional[str] = None,
    top_k: int = 10,
) -> Any:
    return await call_mcp_tool(
        "semantic_search",
        {"query": query, "node_type": node_type, "top_k": top_k},
    )
