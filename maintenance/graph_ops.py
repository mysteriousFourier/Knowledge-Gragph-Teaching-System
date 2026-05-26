"""Graph CRUD operations: add/update/delete nodes and relations, queries, search."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from KGTS.core.mcp_client import call_mcp_tool
from KGTS.core.seed import ensure_seed_graph
from KGTS.core.bridge import (
    build_frontend_graph,
    call_backend_tool,
    get_graph_schema,
    normalize_frontend_node,
    normalize_frontend_relation,
    search_nodes as bridge_search_nodes,
)


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
