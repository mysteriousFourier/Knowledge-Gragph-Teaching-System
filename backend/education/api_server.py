"""
教育模式API服务器 - 轻量级入口
通过导入新架构路由提供服务，保持向后兼容
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR.parent))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from app_config import (
    DEFAULT_EDUCATION_API_PORT,
    get_bind_host,
    get_env_int,
    load_root_env,
)
from KGTS.middleware import setup_cors
from KGTS.education.router import router as education_router
from KGTS.education.router_student import router as student_router
from KGTS.education.router_teacher import router as teacher_router

load_root_env()

app = FastAPI(
    title="知识图谱教育系统API",
    description="提供授课文案生成、问答等教育功能",
    version="1.0.0",
)

setup_cors(app)

app.include_router(education_router)
app.include_router(student_router)
app.include_router(teacher_router)


@app.post("/api/education/ppt-slide-image/{slide_index}")
async def ppt_slide_image(slide_index: int, file: UploadFile = File(...)):
    """获取PPT指定页的图片数据（用于按需加载大图）."""
    try:
        file_bytes = await file.read()
        from ppt_parser import parse_ppt

        parse_result = parse_ppt(file_bytes)
        if not parse_result.get("success"):
            raise HTTPException(status_code=400, detail="PPT 解析失败")

        slides = parse_result.get("slides", [])
        if slide_index < 1 or slide_index > len(slides):
            raise HTTPException(
                status_code=404, detail=f"幻灯片第 {slide_index} 页不存在"
            )

        slide = slides[slide_index - 1]
        images = slide.get("images", [])
        return {
            "success": True,
            "slide_index": slide_index,
            "images": images,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"获取幻灯片图片失败: {str(e)}"
        )


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化."""
    from KGTS.core.mcp_client import get_mcp_client

    print("教育模式API服务器启动...")
    print("正在初始化MCP客户端...")
    await get_mcp_client()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理."""
    from KGTS.core.mcp_client import close_mcp_client

    print("教育模式API服务器关闭...")
    await close_mcp_client()


if __name__ == "__main__":
    import uvicorn

    port = get_env_int("EDUCATION_API_PORT", DEFAULT_EDUCATION_API_PORT)
    bind_host = get_bind_host("EDUCATION_BIND_HOST")
    uvicorn.run(app, host=bind_host, port=port)
