from __future__ import annotations
from fastapi import HTTPException
from typing import Any

class GraphNotFoundError(HTTPException):
    def __init__(self, detail: str = "知识图谱未找到"):
        super().__init__(status_code=404, detail=detail)

class NodeNotFoundError(HTTPException):
    def __init__(self, node_id: str = ""):
        super().__init__(status_code=404, detail=f"节点未找到: {node_id}")

class GraphOperationError(HTTPException):
    def __init__(self, detail: str = "图谱操作失败"):
        super().__init__(status_code=500, detail=detail)

class LLMConfigError(HTTPException):
    def __init__(self, detail: str = "LLM 配置错误"):
        super().__init__(status_code=400, detail=detail)
