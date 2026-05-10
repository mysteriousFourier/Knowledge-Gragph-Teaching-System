from __future__ import annotations
from functools import lru_cache
from typing import Any, Dict, List, Optional

from KGTS.core.graph_service import GraphService
from KGTS.core.mcp_client import MCPClient, get_mcp_client

@lru_cache
def get_graph_service(db_path: str | None = None) -> GraphService:
    return GraphService(db_path=db_path)

async def get_mcp() -> MCPClient:
    return await get_mcp_client()
