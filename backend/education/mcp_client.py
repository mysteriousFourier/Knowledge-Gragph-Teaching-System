"""In-process MCP compatibility client backed by vector_index_system."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from vector_backend_bridge import call_backend_tool


TOOL_NAMES = [
    "read_graph",
    "get_node",
    "get_relations",
    "get_graph_schema",
    "search_nodes",
    "semantic_search",
    "add_memory",
    "update_memory",
    "delete_memory",
    "add_relation",
    "get_neighbors",
    "trace_call_path",
    "discover_weak_relations",
    "get_note",
    "batch_import_graph",
    "get_graph_statistics",
    "get_subgraph_by_type",
    "get_k_hop_neighbors",
    "get_prerequisites",
    "get_follow_up",
]


class MCPClient:
    """Small async wrapper that preserves the old MCP client interface."""

    async def start(self) -> None:
        return None

    async def list_tools(self) -> List[Dict[str, Any]]:
        return [{"name": name} for name in TOOL_NAMES]

    async def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        return call_backend_tool(tool_name, arguments or {})

    async def close(self) -> None:
        return None


_mcp_client: Optional[MCPClient] = None


async def get_mcp_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
        await _mcp_client.start()
    return _mcp_client


async def close_mcp_client() -> None:
    global _mcp_client
    if _mcp_client is not None:
        await _mcp_client.close()
        _mcp_client = None


async def call_mcp_tool(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
    client = await get_mcp_client()
    return await client.call_tool(tool_name, arguments)

