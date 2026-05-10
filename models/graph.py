from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Optional, Any

class AddNodeRequest(BaseModel):
    content: str = Field(..., description="节点内容")
    type: str = Field(..., description="节点类型: chapter, concept, note, observation")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

class UpdateNodeRequest(BaseModel):
    node_id: str = Field(..., description="节点ID")
    content: Optional[str] = Field(None, description="新内容")
    metadata: Optional[Dict[str, Any]] = Field(None, description="新元数据")

class AddRelationRequest(BaseModel):
    source_id: str = Field(..., description="源节点ID")
    target_id: str = Field(..., description="目标节点ID")
    relation_type: str = Field(..., description="关系类型: parent, contains, precedes, semantic_weak")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    similarity: Optional[float] = Field(None, description="相似度（用于弱关系）")

class UpdateRelationRequest(BaseModel):
    relation_id: str = Field(..., description="关系ID")
    source_id: Optional[str] = Field(default=None, description="源节点ID")
    target_id: Optional[str] = Field(default=None, description="目标节点ID")
    relation_type: Optional[str] = Field(default=None, description="关系类型")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    similarity: Optional[float] = Field(default=None, description="关系强度")

class SearchNodesRequest(BaseModel):
    keyword: str = Field(..., description="搜索关键词")
    node_type: Optional[str] = Field(None, description="节点类型过滤")
    limit: int = Field(20, description="返回结果数量")

class SemanticSearchRequest(BaseModel):
    query: str = Field(..., description="查询文本")
    node_type: Optional[str] = Field(None, description="节点类型过滤")
    top_k: int = Field(default=10, description="返回结果数量")

class ImportGraphRequest(BaseModel):
    graph_data: Dict[str, Any] = Field(..., description="知识图谱数据")
    graph_name: Optional[str] = Field(None, description="图谱名称")

class ImportGraphMLRequest(BaseModel):
    file_path: Optional[str] = Field(None, description="GraphML文件路径")
    file_content: Optional[str] = Field(None, description="GraphML文件内容")
    graph_name: Optional[str] = Field(None, description="图谱名称")
    max_nodes: Optional[int] = Field(None, description="最大导入节点数")

    @model_validator(mode='after')
    def validate_file_input(self):
        if not self.file_path and not self.file_content:
            raise ValueError("必须提供 file_path 或 file_content 其中之一")
        return self

class GetSubgraphRequest(BaseModel):
    node_type: str = Field(..., description="节点类型")

class GetKHopNeighborsRequest(BaseModel):
    node_id: str = Field(..., description="节点ID")
    k: int = Field(default=2, description="跳数")

class GetPrerequisitesRequest(BaseModel):
    node_id: str = Field(..., description="节点ID")
    max_depth: int = Field(default=3, description="最大深度")

class GetFollowUpRequest(BaseModel):
    node_id: str = Field(..., description="节点ID")
    max_depth: int = Field(default=3, description="最大深度")

class ValidateGraphRequest(BaseModel):
    pass

class CleanOrphanNodesRequest(BaseModel):
    pass

class GetAnalyticsRequest(BaseModel):
    pass

class GetSchemaRequest(BaseModel):
    pass
