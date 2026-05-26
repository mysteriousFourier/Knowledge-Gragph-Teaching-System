"""KGTS Maintenance API Server — standalone entry point for multi-port mode."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import uvicorn
from fastapi import FastAPI

from KGTS.config import DEFAULT_MAINTENANCE_API_PORT, get_bind_host, get_env_int, load_root_env
from KGTS.middleware import setup_cors
from KGTS.maintenance.router import router as maintenance_router

load_root_env()

app = FastAPI(title="KGTS Maintenance API", version="2.0.0")
setup_cors(app)

app.include_router(maintenance_router)


@app.on_event("startup")
async def _startup() -> None:
    pass


@app.on_event("shutdown")
async def _shutdown() -> None:
    from KGTS.core.mcp_client import close_mcp_client
    await close_mcp_client()


if __name__ == "__main__":
    port = get_env_int("MAINTENANCE_API_PORT", DEFAULT_MAINTENANCE_API_PORT)
    bind_host = get_bind_host("MAINTENANCE_BIND_HOST")
    uvicorn.run(app, host=bind_host, port=port)
