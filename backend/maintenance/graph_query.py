"""
后台维护系统 - 图谱查询模块
提供知识图谱的查询能力
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from graph_manager import KnowledgeGraph
from typing import List, Dict, Optional, Any
import json


class GraphQuery:
    """图谱查询器"""

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def get_graph_structure(self) -> Dict:
        """获取完整图谱结构"""
        return self.kg.get_graph_structure()

    def get_graph_schema(self) -> Dict:
        """获取图谱结构统计"""
        return self.kg.get_graph_schema()

    def get_node(self, node_id: str) -> Optional[Dict]:
        """获取单个节点"""
        node = self.kg.get_node(node_id)
        if node:
            return node.__dict__
        return None

    def get_nodes_by_type(self, node_type: str) -> List[Dict]:
        """按类型获取节点"""
        nodes = self.kg.get_all_nodes(node_type)
        return [node.__dict__ for node in nodes]

    def get_relations(self, node_id: Optional[str] = None,
                     relation_type: Optional[str] = None) -> List[Dict]:
        """获取关系"""
        relations = self.kg.get_relations(node_id, relation_type)
        return [r.__dict__ for r in relations]

    def get_neighbors(self, node_id: str, direction: str = "both") -> Dict[str, List[Dict]]:
        """获取邻居节点"""
        neighbors = self.kg.get_neighbors(node_id, direction)
        return {
            "in": [n.__dict__ for n in neighbors["in"]],
            "out": [n.__dict__ for n in neighbors["out"]]
        }

    def trace_call_path(self, start_node_id: str, max_depth: int = 5) -> List[Dict]:
        """BFS追踪知识路径"""
        return self.kg.trace_call_path(start_node_id, max_depth)

    def discover_weak_relations(self, node_id: str, threshold: float = 0.3) -> List[Dict]:
        """发现弱关系"""
        return self.kg.discover_weak_relations(node_id, threshold)


# CC中调用示例
def cc_graph_query_example():
    """
    CC中调用示例：
    通过MCP工具查询知识图谱
    """
    return '''
# 在CC中，通过MCP工具调用：

# 1. 获取完整图谱结构
graph_structure = read_graph()
# 返回: {nodes: [...], relations: [...], stats: {...}}

# 2. 获取图谱结构统计
schema = get_graph_schema()
# 返回: {stats: {...}, vector_stats: {...}, node_types: [...], relation_types: [...]}

# 3. 获取单个节点
node = get_node(node_id="node-123")

# 4. 按类型获取节点
chapters = search_nodes(keyword="", node_type="chapter")

# 5. 获取节点关系
relations = get_relations(node_id="node-123")
# 或按类型获取
parent_relations = get_relations(node_id="node-123", relation_type="parent")

# 6. 获取邻居节点
neighbors = get_neighbors(node_id="node-123", direction="out")
# 返回: {in: [...], out: [...]}

# 7. 追踪知识路径（BFS）
paths = trace_call_path(start_node_id="node-123", max_depth=3)
# 返回: [{node_id, depth, path, node}, ...]

# 8. 发现弱关系（基于向量相似度）
weak_relations = discover_weak_relations(node_id="node-123", threshold=0.4)
# 返回: [{source_id, target_id, relation_type, similarity, target_metadata}, ...]
    '''


if __name__ == "__main__":
    # 测试查询功能
    query = GraphQuery()

    print("="*50)
    print("测试图谱查询功能")
    print("="*50)

    # 获取图谱结构
    print("\n1. 获取图谱结构:")
    structure = query.get_graph_structure()
    print(f"   节点数: {structure['stats']['node_count']}")
    print(f"   关系数: {structure['stats']['relation_count']}")
    print(f"   节点类型: {structure['stats']['node_types']}")

    # 获取图谱统计
    print("\n2. 获取图谱统计:")
    schema = query.get_graph_schema()
    print(f"   向量模式: {schema['vector_stats']['mode']}")

    # 按类型获取节点
    print("\n3. 按类型获取章节:")
    chapters = query.get_nodes_by_type("chapter")
    for ch in chapters:
        print(f"   - {ch['metadata']['title']} (ID: {ch['id']})")

    # 获取概念节点
    print("\n4. 按类型获取概念:")
    concepts = query.get_nodes_by_type("concept")
    for c in concepts:
        print(f"   - {c['content'][:30]}... (ID: {c['id']})")

    # 获取关系
    print("\n5. 获取关系:")
    if chapters:
        relations = query.get_relations(chapters[0]['id'])
        print(f"   节点 {chapters[0]['metadata']['title']} 的关系数: {len(relations)}")

    # 获取邻居
    print("\n6. 获取邻居:")
    if concepts:
        neighbors = query.get_neighbors(concepts[0]['id'])
        print(f"   节点的出边邻居: {len(neighbors['out'])} 个")
        print(f"   节点的入边邻居: {len(neighbors['in'])} 个")

    # 追踪路径
    print("\n7. 追踪知识路径:")
    if chapters:
        paths = query.trace_call_path(chapters[0]['id'], max_depth=2)
        print(f"   找到 {len(paths)} 条路径")

    # 发现弱关系
    print("\n8. 发现弱关系:")
    if concepts:
        weak_relations = query.discover_weak_relations(concepts[0]['id'])
        print(f"   发现 {len(weak_relations)} 个弱关系")

    print("\n" + "="*50)
    print("CC中调用示例:")
    print(cc_graph_query_example())
