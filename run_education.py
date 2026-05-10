"""KGTS Education API Server — standalone entry point for multi-port mode."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import uvicorn
from fastapi import FastAPI

from KGTS.config import DEFAULT_EDUCATION_API_PORT, get_bind_host, get_env_int, load_root_env
from KGTS.middleware import setup_cors
from KGTS.education.router import router as education_router
from KGTS.education.router_student import router as student_router
from KGTS.education.router_teacher import router as teacher_router

load_root_env()

app = FastAPI(title="KGTS Education API", version="2.0.0")
setup_cors(app)

app.include_router(education_router)
app.include_router(student_router)
app.include_router(teacher_router)


@app.on_event("startup")
async def _startup() -> None:
    pass


@app.on_event("shutdown")
async def _shutdown() -> None:
    from KGTS.core.mcp_client import close_mcp_client
    await close_mcp_client()


if __name__ == "__main__":
    port = get_env_int("EDUCATION_API_PORT", DEFAULT_EDUCATION_API_PORT)
    bind_host = get_bind_host("EDUCATION_BIND_HOST")
    uvicorn.run(app, host=bind_host, port=port)
