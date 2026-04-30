"""
MCP服务器核心实现
定义所有可被CC调用的工具
"""
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import BaseModel, Field, model_validator
import json
import os

from graph_manager import get_knowledge_graph
from graphml_importer import parse_graphml_file, convert_to_mcp_format
from config import config

# 创建MCP服务器
server = Server("knowledge-graph-mcp", version="1.0.0")

kg = get_knowledge_graph()


# ==================== 工具参数模型 ====================

class AddMemoryParams(BaseModel):
    """添加记忆参数"""
    content: str = Field(description="记忆内容")
    type: str = Field(description="类型: chapter, concept, note, observation")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")


class GetNodeParams(BaseModel):
    """获取节点参数"""
    node_id: str = Field(description="节点ID")


class SearchNodesParams(BaseModel):
    """搜索节点参数"""
    keyword: str = Field(description="搜索关键词")
    node_type: Optional[str] = Field(default=None, description="节点类型过滤")
    limit: int = Field(default=20, description="返回结果数量")


class SemanticSearchParams(BaseModel):
    """语义搜索参数"""
    query: str = Field(description="查询文本")
    node_type: Optional[str] = Field(default=None, description="节点类型过滤")
    top_k: int = Field(default=10, description="返回结果数量")


class UpdateMemoryParams(BaseModel):
    """更新记忆参数"""
    node_id: str = Field(description="节点ID")
    content: Optional[str] = Field(default=None, description="新内容")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="新元数据")


class DeleteMemoryParams(BaseModel):
    """删除记忆参数"""
    node_id: str = Field(description="节点ID")


class AddRelationParams(BaseModel):
    """添加关系参数"""
    source_id: str = Field(description="源节点ID")
    target_id: str = Field(description="目标节点ID")
    relation_type: str = Field(description="关系类型: parent, contains, precedes, semantic_weak")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    similarity: Optional[float] = Field(default=None, description="相似度（用于弱关系）")


class GetRelationsParams(BaseModel):
    """获取关系参数"""
    node_id: Optional[str] = Field(default=None, description="节点ID（不指定则获取所有关系）")
    relation_type: Optional[str] = Field(default=None, description="关系类型过滤")


class GetNeighborsParams(BaseModel):
    """获取邻居参数"""
    node_id: str = Field(description="节点ID")
    direction: str = Field(default="both", description="方向: in, out, both")


class TraceCallPathParams(BaseModel):
    """追踪调用链参数"""
    start_node_id: str = Field(description="起始节点ID")
    max_depth: int = Field(default=5, description="最大深度")


class DiscoverWeakRelationsParams(BaseModel):
    """发现弱关系参数"""
    node_id: str = Field(description="节点ID")
    threshold: float = Field(default=0.3, description="相似度阈值")


class GetNoteParams(BaseModel):
    """获取笔记参数（学生查询授课文案）"""
    node_id: Optional[str] = Field(default=None, description="节点ID（不指定则获取所有observation类型节点）")


class BatchImportParams(BaseModel):
    """批量导入参数"""
    nodes: List[Dict[str, Any]] = Field(description="节点数据列表")
    relations: List[Dict[str, Any]] = Field(description="关系数据列表")


class ImportGraphMLParams(BaseModel):
    """导入GraphML参数"""
    file_content: str = Field(description="GraphML文件内容")
    file_path: Optional[str] = Field(None, description="GraphML文件路径（可选，用于日志记录）")


class GetGraphStatisticsParams(BaseModel):
    """获取图谱统计参数"""
    pass


class GetSubgraphByTypeParams(BaseModel):
    """获取按类型子图参数"""
    node_type: str = Field(description="节点类型")


class GetKHopNeighborsParams(BaseModel):
    """获取k跳邻居参数"""
    node_id: str = Field(description="节点ID")
    k: int = Field(default=2, description="跳数")


class GetPrerequisitesParams(BaseModel):
    """获取前置知识参数"""
    node_id: str = Field(description="节点ID")
    max_depth: int = Field(default=3, description="最大深度")


class GetFollowUpParams(BaseModel):
    """获取后置知识参数"""
    node_id: str = Field(description="节点ID")
    max_depth: int = Field(default=3, description="最大深度")


# ==================== 工具实现 ====================

@server.list_tools()
async def list_tools() -> List[Tool]:
    """列出所有可用工具"""
    return [
        # 图谱查询工具
        Tool(
            name="read_graph",
            description="获取完整的知识图谱结构，包含所有节点和关系",
            inputSchema={}
        ),
        Tool(
            name="get_node",
            description="获取单个节点的详细信息",
            inputSchema=GetNodeParams.model_json_schema()
        ),
        Tool(
            name="get_relations",
            description="获取节点间的关系",
            inputSchema=GetRelationsParams.model_json_schema()
        ),
        Tool(
            name="get_graph_schema",
            description="查询图谱结构，获取统计信息",
            inputSchema={}
        ),

        # 搜索工具
        Tool(
            name="search_nodes",
            description="按关键词搜索节点（BM25风格）",
            inputSchema=SearchNodesParams.model_json_schema()
        ),
        Tool(
            name="semantic_search",
            description="语义搜索节点（基于向量相似度）",
            inputSchema=SemanticSearchParams.model_json_schema()
        ),

        # 图谱更新工具
        Tool(
            name="add_memory",
            description="添加新节点到知识图谱",
            inputSchema=AddMemoryParams.model_json_schema()
        ),
        Tool(
            name="update_memory",
            description="更新现有节点的内容或元数据",
            inputSchema=UpdateMemoryParams.model_json_schema()
        ),
        Tool(
            name="delete_memory",
            description="删除节点及其相关关系",
            inputSchema=DeleteMemoryParams.model_json_schema()
        ),
        Tool(
            name="add_relation",
            description="添加节点间的关系",
            inputSchema=AddRelationParams.model_json_schema()
        ),

        # 高级工具
        Tool(
            name="get_neighbors",
            description="获取节点的邻居节点",
            inputSchema=GetNeighborsParams.model_json_schema()
        ),
        Tool(
            name="trace_call_path",
            description="BFS追踪知识路径（调用链）",
            inputSchema=TraceCallPathParams.model_json_schema()
        ),
        Tool(
            name="discover_weak_relations",
            description="基于向量相似度发现弱关系",
            inputSchema=DiscoverWeakRelationsParams.model_json_schema()
        ),

        # 教育专用工具
        Tool(
            name="get_note",
            description="获取授课文案（observation类型节点）",
            inputSchema=GetNoteParams.model_json_schema()
        ),

        # 批量导入工具
        Tool(
            name="batch_import_graph",
            description="批量导入节点和关系到知识图谱",
            inputSchema=BatchImportParams.model_json_schema()
        ),
        Tool(
            name="import_graphml",
            description="从GraphML文件导入知识图谱",
            inputSchema=ImportGraphMLParams.model_json_schema()
        ),

        # 图谱分析工具
        Tool(
            name="get_graph_statistics",
            description="获取知识图谱统计信息",
            inputSchema=GetGraphStatisticsParams.model_json_schema()
        ),
        Tool(
            name="get_subgraph_by_type",
            description="按节点类型获取子图",
            inputSchema=GetSubgraphByTypeParams.model_json_schema()
        ),
        Tool(
            name="get_k_hop_neighbors",
            description="获取节点的k跳邻居",
            inputSchema=GetKHopNeighborsParams.model_json_schema()
        ),

        # 教育路径推荐工具
        Tool(
            name="get_prerequisites",
            description="获取节点的前置知识（入边追溯）",
            inputSchema=GetPrerequisitesParams.model_json_schema()
        ),
        Tool(
            name="get_follow_up",
            description="获取节点的后置知识（出边追溯）",
            inputSchema=GetFollowUpParams.model_json_schema()
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """调用工具"""
    try:
        # 图谱查询工具
        if name == "read_graph":
            result = kg.get_graph_structure()
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2)
            )]

        elif name == "get_node":
            params = GetNodeParams(**arguments)
            node = kg.get_node(params.node_id)
            if node:
                return [TextContent(
                    type="text",
                    text=json.dumps(node.__dict__, ensure_ascii=False, indent=2, default=str)
                )]
            else:
                return [TextContent(type="text", text=f"Node {params.node_id} not found")]

        elif name == "get_relations":
            params = GetRelationsParams(**arguments)
            relations = kg.get_relations(params.node_id, params.relation_type)
            return [TextContent(
                type="text",
                text=json.dumps([r.__dict__ for r in relations], ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "get_graph_schema":
            graph = kg.get_graph_structure()
            schema = {
                "stats": graph["stats"],
                "vector_stats": graph["vector_stats"],
                "node_types": list(set(n["type"] for n in graph["nodes"])),
                "relation_types": list(set(r["relation_type"] for r in graph["relations"]))
            }
            return [TextContent(
                type="text",
                text=json.dumps(schema, ensure_ascii=False, indent=2)
            )]

        # 搜索工具
        elif name == "search_nodes":
            params = SearchNodesParams(**arguments)
            nodes = kg.search_nodes(params.keyword, params.node_type, params.limit)
            return [TextContent(
                type="text",
                text=json.dumps([n.__dict__ for n in nodes], ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "semantic_search":
            params = SemanticSearchParams(**arguments)
            results = kg.semantic_search(params.query, params.node_type, params.top_k)
            return [TextContent(
                type="text",
                text=json.dumps(results, ensure_ascii=False, indent=2)
            )]

        # 图谱更新工具
        elif name == "add_memory":
            params = AddMemoryParams(**arguments)
            node = kg.add_node(params.content, params.type, params.metadata)
            return [TextContent(
                type="text",
                text=json.dumps(node.__dict__, ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "update_memory":
            params = UpdateMemoryParams(**arguments)
            success = kg.update_node(params.node_id, params.content, params.metadata)
            return [TextContent(
                type="text",
                text=json.dumps({"success": success}, ensure_ascii=False)
            )]

        elif name == "delete_memory":
            params = DeleteMemoryParams(**arguments)
            success = kg.delete_node(params.node_id)
            return [TextContent(
                type="text",
                text=json.dumps({"success": success}, ensure_ascii=False)
            )]

        elif name == "add_relation":
            params = AddRelationParams(**arguments)
            relation = kg.add_relation(
                params.source_id,
                params.target_id,
                params.relation_type,
                params.metadata,
                params.similarity
            )
            return [TextContent(
                type="text",
                text=json.dumps(relation.__dict__, ensure_ascii=False, indent=2, default=str)
            )]

        # 高级工具
        elif name == "get_neighbors":
            params = GetNeighborsParams(**arguments)
            neighbors = kg.get_neighbors(params.node_id, params.direction)
            result = {
                k: [n.__dict__ for n in v]
                for k, v in neighbors.items()
            }
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "trace_call_path":
            params = TraceCallPathParams(**arguments)
            paths = kg.trace_call_path(params.start_node_id, params.max_depth)
            return [TextContent(
                type="text",
                text=json.dumps(paths, ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "discover_weak_relations":
            params = DiscoverWeakRelationsParams(**arguments)
            weak_relations = kg.discover_weak_relations(params.node_id, params.threshold)
            return [TextContent(
                type="text",
                text=json.dumps(weak_relations, ensure_ascii=False, indent=2)
            )]

        # 教育专用工具
        elif name == "get_note":
            params = GetNoteParams(**arguments)
            if params.node_id:
                node = kg.get_node(params.node_id)
                if node and node.type == "observation":
                    return [TextContent(
                        type="text",
                        text=json.dumps(node.__dict__, ensure_ascii=False, indent=2, default=str)
                    )]
                else:
                    return [TextContent(type="text", text="Note not found or wrong type")]
            else:
                # 获取所有observation类型节点
                notes = kg.get_all_nodes("observation")
                return [TextContent(
                    type="text",
                    text=json.dumps([n.__dict__ for n in notes], ensure_ascii=False, indent=2, default=str)
                )]

        # 批量导入工具
        elif name == "batch_import_graph":
            params = BatchImportParams(**arguments)
            result = kg.batch_import_graph(params.nodes, params.relations)
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2)
            )]

        elif name == "import_graphml":
            params = ImportGraphMLParams(**arguments)

            # 解析GraphML文件
            try:
                if params.file_content:
                    # 直接解析文件内容
                    import tempfile
                    import os
                    # 创建临时文件
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.graphml', delete=False, encoding='utf-8') as temp_file:
                        temp_file.write(params.file_content)
                        temp_file_path = temp_file.name

                    try:
                        nodes, edges = parse_graphml_file(temp_file_path)
                        source_info = "inline content"
                    finally:
                        # 清理临时文件
                        try:
                            os.unlink(temp_file_path)
                        except:
                            pass
                elif params.file_path:
                    # 从文件路径解析
                    nodes, edges = parse_graphml_file(params.file_path)
                    source_info = params.file_path
                else:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "success": False,
                            "error": "Either file_path or file_content must be provided"
                        }, ensure_ascii=False)
                    )]

                mcp_data = convert_to_mcp_format(nodes, edges)

                # 批量导入
                result = kg.batch_import_graph(
                    mcp_data["nodes"],
                    mcp_data["edges"]
                )

                result["source_file"] = source_info
                result["graphml_stats"] = {
                    "nodes_parsed": len(nodes),
                    "edges_parsed": len(edges)
                }

                return [TextContent(
                    type="text",
                    text=json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2)
                )]
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }, ensure_ascii=False, indent=2)
                )]

        # 图谱分析工具
        elif name == "get_graph_statistics":
            stats = kg.get_graph_statistics()
            return [TextContent(
                type="text",
                text=json.dumps(stats, ensure_ascii=False, indent=2)
            )]

        elif name == "get_subgraph_by_type":
            params = GetSubgraphByTypeParams(**arguments)
            subgraph = kg.get_subgraph_by_type(params.node_type)
            return [TextContent(
                type="text",
                text=json.dumps(subgraph, ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "get_k_hop_neighbors":
            params = GetKHopNeighborsParams(**arguments)
            neighbors = kg.get_k_hop_neighbors(params.node_id, params.k)
            return [TextContent(
                type="text",
                text=json.dumps(neighbors, ensure_ascii=False, indent=2, default=str)
            )]

        # 教育路径推荐工具
        elif name == "get_prerequisites":
            params = GetPrerequisitesParams(**arguments)
            # 使用trace_call_path追溯入边（前置知识）
            # 需要反向追踪，即找到指向当前节点的路径
            paths = []
            visited = set()

            def trace_backwards(node_id, depth, path):
                if depth > params.max_depth or node_id in visited:
                    return
                visited.add(node_id)

                neighbors = kg.get_neighbors(node_id, direction="in")
                for neighbor in neighbors["in"]:
                    new_path = path + [node_id]
                    paths.append({
                        "node_id": neighbor.id,
                        "depth": depth,
                        "path": [neighbor.id] + new_path,
                        "node": neighbor.__dict__
                    })
                    trace_backwards(neighbor.id, depth + 1, new_path)

            trace_backwards(params.node_id, 1, [])

            return [TextContent(
                type="text",
                text=json.dumps(paths, ensure_ascii=False, indent=2, default=str)
            )]

        elif name == "get_follow_up":
            params = GetFollowUpParams(**arguments)
            # 使用trace_call_path追溯出边（后置知识）
            paths = kg.trace_call_path(params.node_id, params.max_depth)
            return [TextContent(
                type="text",
                text=json.dumps(paths, ensure_ascii=False, indent=2, default=str)
            )]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """启动MCP服务器"""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
