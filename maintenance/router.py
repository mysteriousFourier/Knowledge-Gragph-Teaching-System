"""Consolidated maintenance API router."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from KGTS.models.graph import (
    AddNodeRequest,
    AddRelationRequest,
    CleanOrphanNodesRequest,
    GetAnalyticsRequest,
    GetFollowUpRequest,
    GetKHopNeighborsRequest,
    GetPrerequisitesRequest,
    GetSchemaRequest,
    GetSubgraphRequest,
    ImportGraphMLRequest,
    ImportGraphRequest,
    SearchNodesRequest,
    SemanticSearchRequest,
    UpdateNodeRequest,
    UpdateRelationRequest,
    ValidateGraphRequest,
)
from KGTS.models.maintenance import ReviewSearchRequest, StructuredStagingRebuildRequest, StructuredSyncRequest
from KGTS.responses import success_response, timestamped_response, error_response
from KGTS.maintenance.graph_ops import (
    add_node as _add_node,
    update_node as _update_node,
    delete_node as _delete_node,
    add_relation as _add_relation,
    update_relation as _update_relation,
    get_node as _get_node,
    get_graph as _get_graph,
    list_nodes as _list_nodes,
    list_relationships as _list_relationships,
    get_scope_tree as _get_scope_tree,
    get_relations as _get_relations,
    get_schema as _get_schema,
    search_nodes as _search_nodes,
    semantic_search as _semantic_search,
)
from KGTS.maintenance.analytics import compute_graph_analytics, compute_relation_audit
from KGTS.maintenance.validation import validate_graph as _validate_graph
from KGTS.maintenance.cleanup import clean_orphan_nodes as _clean_orphan_nodes
from KGTS.maintenance.import_export import (
    import_graph as _import_graph,
    import_graphml as _import_graphml,
    visualize_graphml as _visualize_graphml,
    export_graph as _export_graph,
    export_teacher_package as _export_teacher_package,
)
from KGTS.maintenance.structured_sync import (
    rebuild_staging_graph,
    scan_structured_sources,
    review_search,
)


router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("/")
async def root():
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
            "rebuild_staging_graph": "/api/maintenance/rebuild-staging-graph",
            "review_search": "/api/maintenance/review-search",
            "update_relation": "/api/maintenance/update-relation",
            "analytics": "/api/maintenance/analytics",
            "validate_graph": "/api/maintenance/validate-graph",
            "clean_orphans": "/api/maintenance/clean-orphans",
            "get_subgraph": "/api/maintenance/subgraph",
            "k_hop_neighbors": "/api/maintenance/k-hop-neighbors",
            "prerequisites": "/api/maintenance/prerequisites",
            "follow_up": "/api/maintenance/follow-up",
        },
    }


@router.post("/add-node")
async def add_node(request: AddNodeRequest):
    try:
        result = await _add_node(
            content=request.content,
            type=request.type,
            metadata=request.metadata,
        )
        return timestamped_response(node=result, added_at_key="added_at")
    except Exception as e:
        error_response(f"添加节点失败: {e}")


@router.put("/update-node")
async def update_node(request: UpdateNodeRequest):
    try:
        result = await _update_node(
            node_id=request.node_id,
            content=request.content,
            metadata=request.metadata,
        )
        return timestamped_response(updated=result, updated_at_key="updated_at")
    except Exception as e:
        error_response(f"更新节点失败: {e}")


@router.delete("/delete-node")
async def delete_node(node_id: str):
    try:
        result = await _delete_node(node_id)
        return timestamped_response(deleted=result, deleted_at_key="deleted_at")
    except Exception as e:
        error_response(f"删除节点失败: {e}")


@router.post("/add-relation")
async def add_relation(request: AddRelationRequest):
    try:
        result = await _add_relation(
            source_id=request.source_id,
            target_id=request.target_id,
            relation_type=request.relation_type,
            metadata=request.metadata,
            similarity=request.similarity,
        )
        return timestamped_response(relation=result, added_at_key="added_at")
    except Exception as e:
        error_response(f"添加关系失败: {e}")


@router.put("/update-relation")
async def update_relation(request: UpdateRelationRequest):
    try:
        result = await _update_relation(
            relation_id=request.relation_id,
            source_id=request.source_id,
            target_id=request.target_id,
            relation_type=request.relation_type,
            metadata=request.metadata,
            similarity=request.similarity,
        )
        return timestamped_response(relation=result, updated_at_key="updated_at")
    except Exception as e:
        error_response(f"更新关系失败: {e}")


@router.get("/get-node")
async def get_node(node_id: str):
    try:
        node = await _get_node(node_id)
        return success_response(node=node)
    except Exception as e:
        error_response(f"获取节点失败: {e}")


@router.get("/graph")
async def get_graph():
    try:
        data = await _get_graph()
        return success_response(data=data)
    except Exception as e:
        error_response(f"获取知识图谱失败: {e}")


@router.get("/graph/nodes")
async def list_graph_nodes(
    limit: int = 5000,
    include_content: bool = False,
    node_type: Optional[List[str]] = Query(default=None),
):
    try:
        data = await _list_nodes(limit=limit, include_content=include_content, node_types=node_type)
        return success_response(data=data)
    except Exception as e:
        error_response(f"获取图谱节点失败: {e}")


@router.get("/graph/relationships")
async def list_graph_relationships(
    limit: int = 10000,
    relation_type: Optional[str] = None,
    include_metadata: bool = False,
):
    try:
        data = await _list_relationships(
            limit=limit,
            relation_type=relation_type,
            include_metadata=include_metadata,
        )
        return success_response(data=data)
    except Exception as e:
        error_response(f"获取图谱关系失败: {e}")


@router.get("/graph/scope-tree")
async def get_graph_scope_tree():
    try:
        data = await _get_scope_tree()
        return success_response(data=data)
    except Exception as e:
        error_response(f"获取章节树失败: {e}")


@router.get("/stats")
async def get_graph_stats():
    try:
        from KGTS.core.bridge import call_backend_tool

        stats = call_backend_tool("get_graph_statistics")
        return success_response(
            data={
                "total_nodes": (stats.get("nodes") or {}).get("total", 0),
                "total_relationships": (stats.get("relations") or {}).get("total", 0),
                "details": stats,
            }
        )
    except Exception as e:
        error_response(f"获取图谱统计失败: {e}")


@router.post("/import-graph")
async def import_graph(request: ImportGraphRequest):
    try:
        result = await _import_graph(request.graph_data)
        return timestamped_response(
            data=result["data"],
            imported_nodes=result["imported_nodes"],
            imported_edges=result["imported_edges"],
            total_nodes=result["total_nodes"],
            total_edges=result["total_edges"],
            imported_at_key="imported_at",
        )
    except Exception as e:
        error_response(f"导入知识图谱失败: {e}")


@router.post("/search-nodes")
async def search_nodes(request: SearchNodesRequest):
    try:
        results = await _search_nodes(
            keyword=request.keyword,
            node_type=request.node_type,
            limit=request.limit,
        )
        return success_response(results=results)
    except Exception as e:
        error_response(f"搜索节点失败: {e}")


@router.post("/review-search")
async def review_search_nodes(request: ReviewSearchRequest):
    try:
        return review_search(
            request.query,
            limit=request.limit,
            chapter=request.chapter,
        )
    except Exception as e:
        error_response(f"审阅检索失败: {e}")


@router.post("/semantic-search")
async def semantic_search(request: SemanticSearchRequest):
    try:
        result = await _semantic_search(
            query=request.query,
            node_type=request.node_type,
            top_k=request.top_k,
        )
        return success_response(results=result)
    except Exception as e:
        error_response(f"语义搜索失败: {e}")


@router.get("/relations")
async def get_relations(node_id: Optional[str] = None, relation_type: Optional[str] = None):
    try:
        relations = await _get_relations(node_id=node_id, relation_type=relation_type)
        return success_response(relations=relations)
    except Exception as e:
        error_response(f"获取关系失败: {e}")


@router.get("/schema")
async def get_schema():
    try:
        schema = await _get_schema()
        return success_response(schema=schema)
    except Exception as e:
        error_response(f"获取图谱结构失败: {e}")


@router.post("/scan-structured")
async def scan_structured(request: StructuredSyncRequest):
    try:
        result = scan_structured_sources(
            force=request.force,
            dry_run=request.dry_run,
            skip_semantic=request.skip_semantic,
            import_graph=request.import_graph,
        )
        return success_response(data=result)
    except Exception as e:
        error_response(f"structured 同步失败: {e}")


@router.post("/rebuild-staging-graph")
async def rebuild_staging_graph_endpoint(request: StructuredStagingRebuildRequest):
    try:
        result = rebuild_staging_graph(
            toc_export_dir=request.toc_export_dir,
            skip_semantic=request.skip_semantic,
            rebuild_vector=request.rebuild_vector,
        )
        return success_response(data=result)
    except Exception as e:
        error_response(f"staging 图谱重建失败: {e}")


@router.post("/import-graphml")
async def import_graphml(request: ImportGraphMLRequest):
    try:
        result = await _import_graphml(
            file_path=request.file_path,
            file_content=request.file_content,
            graph_name=request.graph_name,
        )
        return timestamped_response(
            data=result["data"],
            graph_name=result["graph_name"],
            imported_at_key="imported_at",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_response(f"导入GraphML失败: {e}")


@router.post("/visualize-graphml")
async def visualize_graphml(request: ImportGraphMLRequest):
    try:
        data = await _visualize_graphml(
            file_path=request.file_path,
            file_content=request.file_content,
            max_nodes=request.max_nodes,
        )
        return success_response(data=data)
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_response(f"Failed to parse GraphML: {e}")


@router.get("/export-graph")
async def export_graph():
    try:
        data = await _export_graph()
        return timestamped_response(data=data, exported_at_key="exported_at")
    except Exception as e:
        error_response(f"导出知识图谱失败: {e}")


@router.get("/export-teacher-package")
async def export_teacher_package():
    try:
        result = await _export_teacher_package()
        return timestamped_response(
            data=result["data"],
            file_path=result["file_path"],
            exported_at_key="exported_at",
        )
    except Exception as e:
        error_response(f"导出教师包失败: {e}")


@router.get("/analytics")
async def get_analytics():
    try:
        data = await compute_graph_analytics()
        return success_response(data=data)
    except Exception as e:
        error_response(f"获取分析数据失败: {e}")


@router.post("/validate-graph")
async def validate_graph(request: ValidateGraphRequest):
    try:
        result = await _validate_graph()
        return timestamped_response(
            valid=result["valid"],
            issues=result["issues"],
            statistics=result["statistics"],
            validated_at_key="validated_at",
        )
    except Exception as e:
        error_response(f"验证图谱失败: {e}")


@router.post("/clean-orphans")
async def clean_orphan_nodes(request: CleanOrphanNodesRequest):
    try:
        result = await _clean_orphan_nodes()
        return timestamped_response(
            deleted_count=result["deleted_count"],
            orphans_found=result["orphans_found"],
            cleaned_at_key="cleaned_at",
        )
    except Exception as e:
        error_response(f"清理孤立节点失败: {e}")


@router.get("/subgraph")
async def get_subgraph(node_type: str):
    try:
        from KGTS.core.mcp_client import call_mcp_tool

        subgraph = await call_mcp_tool(
            "get_subgraph_by_type",
            {"node_type": node_type},
        )
        return success_response(data=subgraph)
    except Exception as e:
        error_response(f"获取子图失败: {e}")


@router.get("/k-hop-neighbors")
async def get_k_hop_neighbors(node_id: str, k: int = 2):
    try:
        from KGTS.core.mcp_client import call_mcp_tool

        neighbors = await call_mcp_tool(
            "get_k_hop_neighbors",
            {"node_id": node_id, "k": k},
        )
        return success_response(data=neighbors)
    except Exception as e:
        error_response(f"获取k跳邻居失败: {e}")


@router.get("/prerequisites")
async def get_prerequisites(node_id: str, max_depth: int = 3):
    try:
        from KGTS.core.mcp_client import call_mcp_tool

        prerequisites = await call_mcp_tool(
            "get_prerequisites",
            {"node_id": node_id, "max_depth": max_depth},
        )
        return success_response(data=prerequisites)
    except Exception as e:
        error_response(f"获取前置知识失败: {e}")


@router.get("/follow-up")
async def get_follow_up(node_id: str, max_depth: int = 3):
    try:
        from KGTS.core.mcp_client import call_mcp_tool

        follow_up = await call_mcp_tool(
            "get_follow_up",
            {"node_id": node_id, "max_depth": max_depth},
        )
        return success_response(data=follow_up)
    except Exception as e:
        error_response(f"获取后置知识失败: {e}")
