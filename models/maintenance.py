from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional

class StructuredSyncRequest(BaseModel):
    force: bool = Field(default=False, description="是否强制全量重建")
    dry_run: bool = Field(default=False, description="仅统计变更，不写入图谱")
    import_graph: bool = Field(default=True, description="是否导入当前生产图谱")
    skip_semantic: bool = Field(default=False, description="是否跳过语义候选关系")

class StructuredStagingRebuildRequest(BaseModel):
    toc_export_dir: Optional[str] = Field(default="目录树导出", description="TOC 导出目录或 toc_tree 文件")
    skip_semantic: bool = Field(default=False, description="是否跳过语义候选关系")
    rebuild_vector: bool = Field(default=True, description="是否重建 staging 向量索引")

class ReviewSearchRequest(BaseModel):
    query: str = Field(..., description="检索文本")
    limit: int = Field(default=10, description="返回节点数")
    chapter: Optional[str] = Field(default=None, description="按章节过滤")
