"""
后台维护系统 - 图谱搜索模块
提供关键词搜索和语义搜索能力
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from graph_manager import KnowledgeGraph
from typing import List, Dict, Optional
import json


class GraphSearch:
    """图谱搜索器"""

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def keyword_search(self, keyword: str, node_type: Optional[str] = None,
                      limit: int = 20) -> List[Dict]:
        """
        关键词搜索（BM25风格）

        Args:
            keyword: 搜索关键词
            node_type: 节点类型过滤
            limit: 返回结果数量

        Returns:
            搜索结果列表
        """
        nodes = self.kg.search_nodes(keyword, node_type, limit)
        return [node.__dict__ for node in nodes]

    def semantic_search(self, query: str, node_type: Optional[str] = None,
                       top_k: int = 10) -> List[Dict]:
        """
        语义搜索（基于向量相似度）

        Args:
            query: 查询文本
            node_type: 节点类型过滤
            top_k: 返回结果数量

        Returns:
            搜索结果列表，包含相似度分数
        """
        results = self.kg.semantic_search(query, node_type, top_k)
        return results

    def hybrid_search(self, keyword: str, node_type: Optional[str] = None,
                     limit: int = 20) -> Dict:
        """
        混合搜索（关键词 + 语义）

        Args:
            keyword: 搜索关键词
            node_type: 节点类型过滤
            limit: 返回结果数量

        Returns:
            混合搜索结果
        """
        # 关键词搜索
        keyword_results = self.keyword_search(keyword, node_type, limit)

        # 语义搜索
        semantic_results = self.semantic_search(keyword, node_type, limit)

        # 合并结果（简单去重，语义搜索结果优先）
        seen_ids = set()
        combined_results = []

        # 先添加语义搜索结果
        for result in semantic_results:
            node_id = result['node_id']
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                combined_results.append({
                    "node_id": node_id,
                    "node": result['metadata'],
                    "similarity": result['similarity'],
                    "match_type": "semantic"
                })

        # 添加关键词搜索结果（排除已存在的）
        for result in keyword_results:
            if result['id'] not in seen_ids and len(combined_results) < limit:
                seen_ids.add(result['id'])
                combined_results.append({
                    "node_id": result['id'],
                    "node": result,
                    "similarity": 0.0,
                    "match_type": "keyword"
                })

        return {
            "total": len(combined_results),
            "results": combined_results
        }


# CC中调用示例
def cc_graph_search_example():
    """
    CC中调用示例：
    通过MCP工具搜索知识图谱
    """
    return '''
# 在CC中，通过MCP工具调用：

# 1. 关键词搜索
results = search_nodes(
  keyword: "向量",
  node_type: "concept",
  limit: 10
)
# 返回: [{id, content, type, metadata, created_at, updated_at}, ...]

# 2. 语义搜索（基于向量相似度）
semantic_results = semantic_search(
  query: "什么是向量空间",
  node_type: "concept",
  top_k: 5
)
# 返回: [{node_id, similarity, metadata}, ...]

# 3. 混合搜索（在CC中自行实现）
# 先关键词搜索
keyword_results = search_nodes(keyword: "矩阵", limit: 10)
# 再语义搜索
semantic_results = semantic_search(query: "矩阵", top_k: 5)
# 合并结果（CC中处理）
    '''


if __name__ == "__main__":
    # 测试搜索功能
    search = GraphSearch()

    print("="*50)
    print("测试图谱搜索功能")
    print("="*50)

    # 关键词搜索
    print("\n1. 关键词搜索 '向量':")
    results = search.keyword_search("向量")
    for r in results:
        print(f"   - {r['content'][:50]}... (类型: {r['type']})")

    # 按类型搜索
    print("\n2. 按类型搜索概念 '向量':")
    results = search.keyword_search("向量", node_type="concept")
    for r in results:
        print(f"   - {r['content'][:50]}...")

    # 语义搜索
    print("\n3. 语义搜索 '什么是向量':")
    results = search.semantic_search("什么是向量")
    for r in results:
        print(f"   - 相似度 {r['similarity']:.3f}: {r['metadata']['content'][:50]}...")

    # 混合搜索
    print("\n4. 混合搜索 '向量':")
    hybrid = search.hybrid_search("向量")
    print(f"   找到 {hybrid['total']} 个结果")
    for r in hybrid['results'][:3]:
        print(f"   - [{r['match_type']}] {r['node']['content'][:40]}...")

    print("\n" + "="*50)
    print("CC中调用示例:")
    print(cc_graph_search_example())
