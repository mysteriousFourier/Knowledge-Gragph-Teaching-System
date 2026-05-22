from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional

class StructuredSyncRequest(BaseModel):
    force: bool = Field(default=False, description="是否强制全量重建")

class ReviewSearchRequest(BaseModel):
    query: str = Field(..., description="检索文本")
    limit: int = Field(default=10, description="返回节点数")
    chapter: Optional[str] = Field(default=None, description="按章节过滤")
