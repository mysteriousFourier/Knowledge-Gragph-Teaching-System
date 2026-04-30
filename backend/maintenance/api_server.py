"""
后台维护API服务器 - 为前端提供HTTP接口
集成MCP客户端进行图谱维护
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Optional, Any
import asyncio
import uvicorn
from datetime import datetime

import sys
import os
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
ROOT_DIR = BACKEND_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import DEFAULT_MAINTENANCE_API_PORT, get_bind_host, get_env_int, load_root_env

load_root_env()

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
sys.path.insert(0, str(BACKEND_DIR / "mcp-server"))
sys.path.insert(0, str(BACKEND_DIR / "education"))

from mcp_client import get_mcp_client, close_mcp_client, call_mcp_tool
from vector_backend_bridge import (
    build_frontend_graph,
    get_graph_schema,
    import_graph_payload,
    import_graphml_payload,
    normalize_frontend_node,
    normalize_frontend_relation,
    search_nodes as backend_search_nodes,
)
from structured_sync import TEACHER_PACKAGE_PATH, build_teacher_package, review_search, scan_structured_sources


# 创建FastAPI应用
app = FastAPI(
    title="知识图谱后台维护API",
    description="提供知识图谱的维护功能",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)


# ==================== 请求模型 ====================

class AddNodeRequest(BaseModel):
    """添加节点请求"""
    content: str = Field(..., description="节点内容")
    type: str = Field(..., description="节点类型: chapter, concept, note, observation")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class UpdateNodeRequest(BaseModel):
    """更新节点请求"""
    node_id: str = Field(..., description="节点ID")
    content: Optional[str] = Field(None, description="新内容")
    metadata: Optional[Dict[str, Any]] = Field(None, description="新元数据")


class AddRelationRequest(BaseModel):
    """添加关系请求"""
    source_id: str = Field(..., description="源节点ID")
    target_id: str = Field(..., description="目标节点ID")
    relation_type: str = Field(..., description="关系类型: parent, contains, precedes, semantic_weak")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    similarity: Optional[float] = Field(None, description="相似度（用于弱关系）")


class ImportGraphRequest(BaseModel):
    """导入知识图谱请求"""
    graph_data: Dict[str, Any] = Field(..., description="知识图谱数据")
    graph_name: Optional[str] = Field(None, description="图谱名称")


class SearchNodesRequest(BaseModel):
    """搜索节点请求"""
    keyword: str = Field(..., description="搜索关键词")
    node_type: Optional[str] = Field(None, description="节点类型过滤")
    limit: int = Field(20, description="返回结果数量")


class SemanticSearchRequest(BaseModel):
    """语义搜索请求"""
    query: str = Field(..., description="查询文本")
    node_type: Optional[str] = Field(None, description="节点类型过滤")
    top_k: int = Field(default=10, description="返回结果数量")


class GetSchemaRequest(BaseModel):
    """获取图谱结构请求"""
    pass


class ImportGraphMLRequest(BaseModel):
    """导入GraphML请求"""
    file_path: Optional[str] = Field(None, description="GraphML文件路径")
    file_content: Optional[str] = Field(None, description="GraphML文件内容（用于直接传递内容）")
    graph_name: Optional[str] = Field(None, description="图谱名称")
    max_nodes: Optional[int] = Field(None, description="最大导入节点数，None表示全部")

    @model_validator(mode='after')
    def validate_file_input(self):
        """确保至少提供文件路径或文件内容"""
        if not self.file_path and not self.file_content:
            raise ValueError("必须提供 file_path 或 file_content 其中之一")
        return self


class StructuredSyncRequest(BaseModel):
    """增量扫描 structured 目录。"""

    force: bool = Field(default=False, description="是否强制全量重建")


class ReviewSearchRequest(BaseModel):
    """按文本检索节点与相关边。"""

    query: str = Field(..., description="检索文本")
    limit: int = Field(default=10, description="返回节点数")
    chapter: Optional[str] = Field(default=None, description="按章节过滤")


class UpdateRelationRequest(BaseModel):
    """更新关系请求。"""

    relation_id: str = Field(..., description="关系ID")
    source_id: Optional[str] = Field(default=None, description="源节点ID")
    target_id: Optional[str] = Field(default=None, description="目标节点ID")
    relation_type: Optional[str] = Field(default=None, description="关系类型")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    similarity: Optional[float] = Field(default=None, description="关系强度")


class GetAnalyticsRequest(BaseModel):
    """获取分析数据请求"""
    pass


class ValidateGraphRequest(BaseModel):
    """验证图谱请求"""
    pass


class CleanOrphanNodesRequest(BaseModel):
    """清理孤立节点请求"""
    pass


class GetSubgraphRequest(BaseModel):
    """获取子图请求"""
    node_type: str = Field(..., description="节点类型")


class GetKHopNeighborsRequest(BaseModel):
    """获取k跳邻居请求"""
    node_id: str = Field(..., description="节点ID")
    k: int = Field(default=2, description="跳数")


class GetPrerequisitesRequest(BaseModel):
    """获取前置知识请求"""
    node_id: str = Field(..., description="节点ID")
    max_depth: int = Field(default=3, description="最大深度")


class GetFollowUpRequest(BaseModel):
    """获取后置知识请求"""
    node_id: str = Field(..., description="节点ID")
    max_depth: int = Field(default=3, description="最大深度")


# ==================== API接口 ====================

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "知识图谱后台维护API",
        "version": "1.0.0",
        "endpoints": {
            "add_node": "/api/maintenance/add-node",
            "update_node": "/api/maintenance/update-node",
            "delete_node": "/api/maintenance/delete-node",
            "add_relation": "/api/maintenance/add-relation",
            "get_node": "/api/maintenance/get-node",
            "get_graph": "/api/maintenance/graph",
            "search_nodes": "/api/maintenance/search-nodes",
            "semantic_search": "/api/maintenance/semantic-search",
            "get_relations": "/api/maintenance/relations",
            "import_graphml": "/api/maintenance/import-graphml",
            "export_graph": "/api/maintenance/export-graph",
            "export_teacher_package": "/api/maintenance/export-teacher-package",
            "scan_structured": "/api/maintenance/scan-structured",
            "review_search": "/api/maintenance/review-search",
            "update_relation": "/api/maintenance/update-relation",
            "analytics": "/api/maintenance/analytics",
            "validate_graph": "/api/maintenance/validate-graph",
            "clean_orphans": "/api/maintenance/clean-orphans",
            "get_subgraph": "/api/maintenance/subgraph",
            "k_hop_neighbors": "/api/maintenance/k-hop-neighbors",
            "prerequisites": "/api/maintenance/prerequisites",
            "follow_up": "/api/maintenance/follow-up"
        }
    }


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/maintenance/add-node")
async def add_node(request: AddNodeRequest):
    """
    添加节点

    向知识图谱添加新节点
    """
    try:
        result = await call_mcp_tool(
            "add_memory",
            {
                "content": request.content,
                "type": request.type,
                "metadata": request.metadata
            }
        )
        return {
            "success": True,
            "node": result,
            "added_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加节点失败: {str(e)}")


@app.put("/api/maintenance/update-node")
async def update_node(request: UpdateNodeRequest):
    """
    更新节点

    更新知识图谱中现有节点（不依赖MCP时返回模拟响应）
    """
    try:
        result = await call_mcp_tool(
            "update_memory",
            {
                "node_id": request.node_id,
                "content": request.content,
                "metadata": request.metadata,
            },
        )
        return {
            "success": True,
            "updated": result,
            "updated_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新节点失败: {str(e)}")


@app.delete("/api/maintenance/delete-node")
async def delete_node(node_id: str):
    """
    删除节点

    从知识图谱删除节点（不依赖MCP时返回模拟响应）
    """
    try:
        result = await call_mcp_tool("delete_memory", {"node_id": node_id})
        return {
            "success": True,
            "deleted": result,
            "deleted_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除节点失败: {str(e)}")


@app.post("/api/maintenance/add-relation")
async def add_relation(request: AddRelationRequest):
    """
    添加关系

    在节点间添加关系
    """
    try:
        result = await call_mcp_tool(
            "add_relation",
            {
                "source_id": request.source_id,
                "target_id": request.target_id,
                "relation_type": request.relation_type,
                "metadata": request.metadata,
                "similarity": request.similarity
            }
        )
        return {
            "success": True,
            "relation": result,
            "added_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加关系失败: {str(e)}")


@app.put("/api/maintenance/update-relation")
async def update_relation(request: UpdateRelationRequest):
    """
    更新关系

    用于教师端审阅和修改节点间关系。
    """
    try:
        result = await call_mcp_tool(
            "update_relation",
            {
                "relation_id": request.relation_id,
                "source_id": request.source_id,
                "target_id": request.target_id,
                "relation_type": request.relation_type,
                "metadata": request.metadata,
                "similarity": request.similarity,
            },
        )
        return {
            "success": True,
            "relation": result,
            "updated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新关系失败: {str(e)}")


@app.get("/api/maintenance/get-node")
async def get_node(node_id: str):
    """
    获取节点详情

    获取单个节点的详细信息（不依赖MCP时返回模拟数据）
    """
    try:
        result = await call_mcp_tool("get_node", {"node_id": node_id})
        return {
            "success": True,
            "node": normalize_frontend_node(result) if isinstance(result, dict) else result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取节点失败: {str(e)}")


@app.get("/api/maintenance/graph")
async def get_graph():
    """
    获取知识图谱

    直接从数据库返回完整的知识图谱数据
    """
    try:
        return {
            "success": True,
            "data": build_frontend_graph()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取知识图谱失败: {str(e)}")


@app.post("/api/maintenance/import-graph")
async def import_graph(request: ImportGraphRequest):
    """
    导入知识图谱

    批量导入节点和关系到MCP服务器
    """
    try:
        result = import_graph_payload(request.graph_data)
        input_nodes = request.graph_data.get("nodes", [])
        input_edges = request.graph_data.get("edges", request.graph_data.get("relations", []))
        node_success = int(result.get("nodes", {}).get("success", 0))
        edge_success = int(result.get("relations", {}).get("success", 0))
        return {
            "success": True,
            "data": result,
            "imported_nodes": [
                {
                    "id": node.get("id"),
                    "label": node.get("label") or node.get("id"),
                    "type": node.get("type", "concept"),
                    "status": "success" if index < node_success else "failed",
                }
                for index, node in enumerate(input_nodes)
            ],
            "imported_edges": [
                {
                    "source": edge.get("source") or edge.get("source_id"),
                    "target": edge.get("target") or edge.get("target_id"),
                    "type": edge.get("type") or edge.get("relation_type", "related"),
                    "status": "success" if index < edge_success else "failed",
                }
                for index, edge in enumerate(input_edges)
            ],
            "total_nodes": len(input_nodes),
            "total_edges": len(input_edges),
            "imported_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入知识图谱失败: {str(e)}")


@app.post("/api/maintenance/search-nodes")
async def search_nodes(request: SearchNodesRequest):
    """
    搜索节点

    按关键词搜索知识图谱中的节点（不依赖MCP时返回空结果）
    """
    try:
        return {
            "success": True,
            "results": backend_search_nodes(
                request.keyword,
                node_type=request.node_type,
                limit=request.limit,
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索节点失败: {str(e)}")


@app.post("/api/maintenance/review-search")
async def review_search_nodes(request: ReviewSearchRequest):
    """
    按文本检索节点，并返回相关边与相邻节点。
    """
    try:
        return review_search(
            request.query,
            limit=request.limit,
            chapter=request.chapter,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"审阅检索失败: {str(e)}")


@app.post("/api/maintenance/semantic-search")
async def semantic_search(request: SemanticSearchRequest):
    """
    语义搜索

    基于向量相似度搜索节点（不依赖MCP时返回空结果）
    """
    try:
        result = await call_mcp_tool(
            "semantic_search",
            {
                "query": request.query,
                "node_type": request.node_type,
                "top_k": request.top_k,
            },
        )
        return {
            "success": True,
            "results": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语义搜索失败: {str(e)}")


@app.get("/api/maintenance/relations")
async def get_relations(node_id: Optional[str] = None, relation_type: Optional[str] = None):
    """
    获取关系

    获取节点间的关系
    """
    try:
        result = await call_mcp_tool(
            "get_relations",
            {"node_id": node_id, "relation_type": relation_type},
        )
        relation_items = result.get("relations") if isinstance(result, dict) else result
        return {
            "success": True,
            "relations": [
                normalize_frontend_relation(item) if isinstance(item, dict) else item
                for item in (relation_items if isinstance(relation_items, list) else [])
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取关系失败: {str(e)}")


@app.get("/api/maintenance/schema")
async def get_schema():
    """
    获取图谱结构

    返回知识图谱的统计信息和结构
    """
    try:
        return {
            "success": True,
            "schema": get_graph_schema()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取图谱结构失败: {str(e)}")


# ==================== 新增API端点 ====================

@app.post("/api/maintenance/scan-structured")
async def scan_structured(request: StructuredSyncRequest):
    """
    扫描 structured 目录并做增量同步，同时生成教师端可加载包。
    """
    try:
        result = scan_structured_sources(force=request.force)
        return {
            "success": True,
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"structured 同步失败: {str(e)}")


@app.post("/api/maintenance/import-graphml")
async def import_graphml(request: ImportGraphMLRequest):
    """
    导入GraphML文件

    从GraphML文件批量导入知识图谱数据
    """
    try:
        result = import_graphml_payload(
            file_path=request.file_path,
            file_content=request.file_content,
        )
        return {
            "success": True,
            "data": result,
            "graph_name": request.graph_name,
            "imported_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入GraphML失败: {str(e)}")


@app.post("/api/maintenance/visualize-graphml")
async def visualize_graphml(request: ImportGraphMLRequest):
    """
    将 GraphML 文件解析为 vis.js 兼容的 JSON 数据，
    用于前端交互式可视化渲染。
    """
    import tempfile

    try:
        file_path = None
        if request.file_content:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.graphml', delete=False, encoding='utf-8'
            ) as temp_file:
                temp_file.write(request.file_content)
                file_path = temp_file.name
        elif request.file_path:
            if not os.path.exists(request.file_path):
                raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
            file_path = request.file_path
        else:
            raise HTTPException(status_code=400, detail="Must provide file_path or file_content")

        try:
            sys.path.insert(0, os.path.dirname(__file__) + os.sep + "..")
            from graphml_to_html import parse_graphml_to_vis_json
            data = parse_graphml_to_vis_json(file_path)

            # Limit nodes if max_nodes is specified
            if request.max_nodes and request.max_nodes > 0:
                keep_ids = set(n["id"] for n in data["nodes"][:request.max_nodes])
                data["nodes"] = [n for n in data["nodes"] if n["id"] in keep_ids]
                data["edges"] = [e for e in data["edges"]
                                 if e["from"] in keep_ids and e["to"] in keep_ids]
                data["stats"]["node_count"] = len(data["nodes"])
                data["stats"]["edge_count"] = len(data["edges"])

            return {"success": True, "data": data}
        finally:
            if request.file_content and file_path:
                try:
                    os.unlink(file_path)
                except Exception:
                    pass

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse GraphML: {str(e)}")


@app.get("/api/maintenance/export-graph")
async def export_graph():
    """
    导出知识图谱

    返回完整的知识图谱数据用于导出
    """
    try:
        return {
            "success": True,
            "data": build_frontend_graph(),
            "exported_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出知识图谱失败: {str(e)}")


@app.get("/api/maintenance/export-teacher-package")
async def export_teacher_package():
    """
    生成教师端可直接加载的 JSON 包，并写入本地文件。
    """
    try:
        package = build_teacher_package()
        return {
            "success": True,
            "data": package,
            "file_path": str(TEACHER_PACKAGE_PATH),
            "exported_at": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出教师包失败: {str(e)}")


@app.get("/api/maintenance/analytics")
async def get_analytics():
    """
    获取图谱分析数据

    返回知识图谱的统计和分析信息
    """
    try:
        stats = await call_mcp_tool("get_graph_statistics", {})
        graph = build_frontend_graph()
        nodes = graph.get("nodes", [])
        relations = graph.get("relations", [])

        # 计算节点度数分析
        node_degrees = {}
        # 初始化所有节点的度数
        for node in nodes:
            node_degrees[node["id"]] = {"in_degree": 0, "out_degree": 0, "total_degree": 0}

        # 计算度数
        for rel in relations:
            source_id = rel.get("source_id")
            target_id = rel.get("target_id")
            if source_id in node_degrees:
                node_degrees[source_id]["out_degree"] += 1
                node_degrees[source_id]["total_degree"] += 1
            if target_id in node_degrees:
                node_degrees[target_id]["in_degree"] += 1
                node_degrees[target_id]["total_degree"] += 1

        # 找出关键节点（度数最高的节点）
        sorted_nodes = sorted(
            node_degrees.items(),
            key=lambda x: x[1]["total_degree"],
            reverse=True
        )
        top_nodes = sorted_nodes[:5]

        # 计算节点类型分布
        type_distribution = {}
        for node in nodes:
            node_type = node.get("type", "unknown")
            type_distribution[node_type] = type_distribution.get(node_type, 0) + 1

        # 计算关系类型分布
        relation_distribution = {}
        for rel in relations:
            rel_type = rel.get("relation_type", "unknown")
            relation_distribution[rel_type] = relation_distribution.get(rel_type, 0) + 1

        # 增强统计数据
        enhanced_stats = {
            **stats,
            "node_degree_analysis": {
                "average_degree": sum(d["total_degree"] for d in node_degrees.values()) / len(node_degrees) if node_degrees else 0,
                "max_degree": max((d["total_degree"] for d in node_degrees.values()), default=0),
                "min_degree": min((d["total_degree"] for d in node_degrees.values()), default=0),
                "top_nodes": [
                    {
                        "node_id": node_id,
                        "node_label": next((n.get("content", node_id) for n in nodes if n.get("id") == node_id), node_id)[:50],
                        "degree": degree_data
                    }
                    for node_id, degree_data in top_nodes
                ]
            },
            "type_distribution": type_distribution,
            "relation_distribution": relation_distribution
        }

        return {
            "success": True,
            "data": enhanced_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分析数据失败: {str(e)}")


@app.post("/api/maintenance/validate-graph")
async def validate_graph(request: ValidateGraphRequest):
    """
    验证图谱

    检查知识图谱的完整性和一致性
    """
    try:
        stats = await call_mcp_tool("get_graph_statistics", {})
        import json
        graph_stats = json.loads(stats) if isinstance(stats, str) else stats

        # 验证逻辑
        issues = []

        # 检查孤立节点（有节点但没有关系）
        if graph_stats.get("nodes", {}).get("total", 0) > 0:
            total_relations = graph_stats.get("relations", {}).get("total", 0)
            if total_relations == 0:
                issues.append("警告: 图谱中没有关系，所有节点都是孤立的")

        # 检查连接密度
        density = graph_stats.get("connectivity", {}).get("density", 0)
        if density < 0.01:
            issues.append(f"警告: 图谱连接密度过低 ({density:.4f})，可能存在许多孤立节点")

        return {
            "success": True,
            "valid": len(issues) == 0,
            "issues": issues,
            "statistics": graph_stats,
            "validated_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证图谱失败: {str(e)}")


@app.post("/api/maintenance/clean-orphans")
async def clean_orphan_nodes(request: CleanOrphanNodesRequest):
    """
    清理孤立节点

    删除没有关系的孤立节点
    """
    try:
        # 获取图谱数据
        graph_data = await call_mcp_tool("read_graph", {})
        import json
        graph = json.loads(graph_data) if isinstance(graph_data, str) else graph_data

        # 找出有关系的节点
        nodes_with_relations = set()
        for rel in graph.get("relations", []):
            nodes_with_relations.add(rel.get("source_id"))
            nodes_with_relations.add(rel.get("target_id"))

        # 找出孤立节点
        orphans = []
        for node in graph.get("nodes", []):
            if node.get("id") not in nodes_with_relations:
                orphans.append(node.get("id"))

        # 删除孤立节点
        deleted_count = 0
        for node_id in orphans:
            try:
                await call_mcp_tool("delete_memory", {"node_id": node_id})
                deleted_count += 1
            except:
                pass

        return {
            "success": True,
            "deleted_count": deleted_count,
            "orphans_found": len(orphans),
            "cleaned_at": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理孤立节点失败: {str(e)}")


@app.get("/api/maintenance/subgraph")
async def get_subgraph(node_type: str):
    """
    获取按类型的子图

    返回指定类型的节点及其关系
    """
    try:
        subgraph = await call_mcp_tool(
            "get_subgraph_by_type",
            {"node_type": node_type}
        )
        return {
            "success": True,
            "data": subgraph
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取子图失败: {str(e)}")


@app.get("/api/maintenance/k-hop-neighbors")
async def get_k_hop_neighbors(node_id: str, k: int = 2):
    """
    获取k跳邻居

    返回指定节点的k跳邻居节点
    """
    try:
        neighbors = await call_mcp_tool(
            "get_k_hop_neighbors",
            {"node_id": node_id, "k": k}
        )
        return {
            "success": True,
            "data": neighbors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取k跳邻居失败: {str(e)}")


@app.get("/api/maintenance/prerequisites")
async def get_prerequisites(node_id: str, max_depth: int = 3):
    """
    获取前置知识

    返回指向当前节点的路径（前置知识点）
    """
    try:
        prerequisites = await call_mcp_tool(
            "get_prerequisites",
            {"node_id": node_id, "max_depth": max_depth}
        )
        return {
            "success": True,
            "data": prerequisites
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取前置知识失败: {str(e)}")


@app.get("/api/maintenance/follow-up")
async def get_follow_up(node_id: str, max_depth: int = 3):
    """
    获取后置知识

    返回从当前节点出发的路径（后置知识点）
    """
    try:
        follow_up = await call_mcp_tool(
            "get_follow_up",
            {"node_id": node_id, "max_depth": max_depth}
        )
        return {
            "success": True,
            "data": follow_up
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取后置知识失败: {str(e)}")


# ==================== 生命周期管理 ====================

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    print("后台维护API服务器启动...")
    print("正在初始化MCP客户端...")
    await get_mcp_client()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    print("后台维护API服务器关闭...")
    await close_mcp_client()


# ==================== 主函数 ====================

def run_server(host: str = get_bind_host("MAINTENANCE_API_BIND_HOST"), port: int = DEFAULT_MAINTENANCE_API_PORT):
    """
    运行API服务器

    Args:
        host: 监听地址
        port: 监听端口
    """
    print(f"启动后台维护API服务器: http://{host}:{port}")
    print("API文档: http://{}:{}/docs".format(host, port))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server(port=get_env_int("MAINTENANCE_API_PORT", DEFAULT_MAINTENANCE_API_PORT))
