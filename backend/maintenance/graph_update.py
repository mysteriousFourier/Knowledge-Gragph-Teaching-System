"""
后台维护系统 - 图谱更新模块
提供节点和关系的增删改功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from graph_manager import KnowledgeGraph
from typing import List, Dict, Optional
import json


class GraphUpdate:
    """图谱更新器"""

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def add_node(self, content: str, type: str, metadata: Optional[Dict] = None) -> Dict:
        """添加节点"""
        node = self.kg.add_node(content, type, metadata)
        return node.__dict__

    def update_node(self, node_id: str, content: Optional[str] = None,
                   metadata: Optional[Dict] = None) -> Dict:
        """更新节点"""
        success = self.kg.update_node(node_id, content, metadata)
        return {"success": success, "node_id": node_id}

    def delete_node(self, node_id: str) -> Dict:
        """删除节点"""
        success = self.kg.delete_node(node_id)
        return {"success": success, "node_id": node_id}

    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                    metadata: Optional[Dict] = None, similarity: Optional[float] = None) -> Dict:
        """添加关系"""
        relation = self.kg.add_relation(source_id, target_id, relation_type, metadata, similarity)
        return relation.__dict__

    def delete_relation(self, relation_id: str) -> Dict:
        """删除关系"""
        success = self.kg.delete_relation(relation_id)
        return {"success": success, "relation_id": relation_id}

    def batch_add_nodes(self, nodes: List[Dict]) -> List[Dict]:
        """批量添加节点"""
        results = []
        for node in nodes:
            result = self.add_node(
                content=node.get("content", ""),
                type=node.get("type", "concept"),
                metadata=node.get("metadata", {})
            )
            results.append(result)
        return results

    def batch_add_relations(self, relations: List[Dict]) -> List[Dict]:
        """批量添加关系"""
        results = []
        for rel in relations:
            result = self.add_relation(
                source_id=rel.get("source_id", ""),
                target_id=rel.get("target_id", ""),
                relation_type=rel.get("relation_type", "related"),
                metadata=rel.get("metadata", {}),
                similarity=rel.get("similarity")
            )
            results.append(result)
        return results


# CC中调用示例
def cc_graph_update_example():
    """
    CC中调用示例：
    通过MCP工具更新知识图谱
    """
    return '''
# 在CC中，通过MCP工具调用：

# 1. 添加节点
node = add_memory(
  content: "线性相关是一组向量的重要性质...",
  type: "concept",
  metadata: {
    "title": "线性相关",
    "chapter_id": "chapter_id",
    "difficulty": "medium"
  }
)
# 返回: {id, content, type, metadata, created_at, updated_at}

# 2. 更新节点
update_memory(
  node_id: "node-123",
  content: "更新后的内容",
  metadata: {"difficulty": "hard"}
)
# 返回: {success: true, node_id: "node-123"}

# 3. 删除节点
delete_memory(node_id: "node-123")
# 返回: {success: true, node_id: "node-123"}

# 4. 添加关系
relation = add_relation(
  source_id: "chapter_id",
  target_id: "concept_id",
  relation_type: "contains",
  metadata: {"order": 1}
)
# 返回: {id, source_id, target_id, relation_type, metadata, created_at}

# 5. 添加弱关系（带相似度）
weak_relation = add_relation(
  source_id: "node-1",
  target_id: "node-2",
  relation_type: "semantic_weak",
  similarity: 0.45
)

# 6. 批量操作（在CC中循环调用）
for item in items:
    add_memory(
        content=item["content"],
        type=item["type"],
        metadata=item.get("metadata", {})
    )
    '''


if __name__ == "__main__":
    # 测试更新功能
    update = GraphUpdate()

    print("="*50)
    print("测试图谱更新功能")
    print("="*50)

    # 获取现有章节
    chapters = update.kg.get_all_nodes("chapter")
    if not chapters:
        print("请先运行 import_chapter.py 添加测试数据")
        exit(1)

    chapter_id = chapters[0].id

    # 添加新节点
    print("\n1. 添加新概念节点:")
    new_node = update.add_node(
        content="线性变换是保持向量加法和数乘运算的映射",
        type="concept",
        metadata={
            "title": "线性变换",
            "chapter_id": chapter_id,
            "difficulty": "medium"
        }
    )
    print(f"   添加成功，ID: {new_node['id']}")

    # 添加关系
    print("\n2. 添加章节-概念关系:")
    relation = update.add_relation(
        source_id=chapter_id,
        target_id=new_node['id'],
        relation_type="contains"
    )
    print(f"   关系添加成功，ID: {relation['id']}")

    # 更新节点
    print("\n3. 更新节点:")
    update_result = update.update_node(
        node_id=new_node['id'],
        content="线性变换是从一个向量空间到另一个向量空间的映射，保持向量加法和数乘运算"
    )
    print(f"   更新结果: {update_result}")

    # 批量添加节点
    print("\n4. 批量添加节点:")
    batch_nodes = [
        {
            "content": "矩阵可以表示线性变换",
            "type": "concept",
            "metadata": {"chapter_id": chapter_id}
        },
        {
            "content": "特征值和特征向量是线性变换的重要概念",
            "type": "concept",
            "metadata": {"chapter_id": chapter_id}
        }
    ]
    batch_results = update.batch_add_nodes(batch_nodes)
    print(f"   批量添加完成，共 {len(batch_results)} 个节点")

    # 验证结果
    print("\n5. 验证结果:")
    updated_graph = update.kg.get_graph_structure()
    print(f"   当前图谱节点数: {updated_graph['stats']['node_count']}")
    print(f"   当前图谱关系数: {updated_graph['stats']['relation_count']}")

    print("\n" + "="*50)
    print("CC中调用示例:")
    print(cc_graph_update_example())
