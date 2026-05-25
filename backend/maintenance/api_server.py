"""
后台维护API服务器 - 轻量级入口
通过导入新架构路由提供服务，保持向后兼容
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
_KGTS_NAME = "KGTS"
if _KGTS_NAME not in sys.modules:
    _kgts_pkg = types.ModuleType(_KGTS_NAME)
    _kgts_pkg.__path__ = [str(ROOT_DIR)]
    sys.modules[_KGTS_NAME] = _kgts_pkg
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI

from app_config import (
    DEFAULT_MAINTENANCE_API_PORT,
    get_bind_host,
    get_env_int,
    load_root_env,
)
from KGTS.middleware import setup_cors
from KGTS.maintenance.router import router as maintenance_router

load_root_env()

app = FastAPI(
    title="知识图谱后台维护API",
    description="提供知识图谱的维护功能",
    version="1.0.0",
)

setup_cors(app)

app.include_router(maintenance_router)


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化."""
    from KGTS.core.mcp_client import get_mcp_client

    print("后台维护API服务器启动...")
    print("正在初始化MCP客户端...")
    await get_mcp_client()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理."""
    from KGTS.core.mcp_client import close_mcp_client

    print("后台维护API服务器关闭...")
    await close_mcp_client()


if __name__ == "__main__":
    import uvicorn

    port = get_env_int("MAINTENANCE_API_PORT", DEFAULT_MAINTENANCE_API_PORT)
    bind_host = get_bind_host("MAINTENANCE_BIND_HOST")
    uvicorn.run(app, host=bind_host, port=port)
