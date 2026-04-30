"""
教育模式 - 知识路径追踪模块
追踪知识点之间的关联路径
"""
import sys
import os

# 确保当前目录在sys.path的最前面
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

sys.path.insert(0, os.path.join(current_dir, "..", "mcp-server"))
sys.path.insert(0, os.path.join(current_dir, "..", "maintenance"))

from graph_manager import KnowledgeGraph
from edu_config import EduConfig
from typing import List, Dict, Optional
import json


class KnowledgePathTracker:
    """知识路径追踪器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = EduConfig.BACKEND_DB_PATH
        self.kg = KnowledgeGraph(db_path)
        self.config = EduConfig()

    def trace_learning_path(self, start_node_id: str, end_node_id: Optional[str] = None,
                           max_depth: int = 5) -> Dict:
        """
        追踪学习路径

        Args:
            start_node_id: 起始节点ID
            end_node_id: 目标节点ID（可选）
            max_depth: 最大深度

        Returns:
            学习路径
        """
        # 追踪从起始节点的所有路径
        paths = self.kg.trace_call_path(start_node_id, max_depth)

        # 如果指定了目标节点，筛选路径
        if end_node_id:
            filtered_paths = []
            for path in paths:
                if end_node_id in path['path']:
                    filtered_paths.append(path)
            paths = filtered_paths

        # 构建路径摘要
        path_summaries = []
        for path in paths:
            path_summaries.append({
                "path": path['path'],
                "depth": path['depth'],
                "node_titles": [path['node']['metadata'].get('title', path['node']['type'])
                               for path_item in [path]]  # 修正这里
            })

        return {
            "success": True,
            "start_node": start_node_id,
            "end_node": end_node_id,
            "max_depth": max_depth,
            "total_paths": len(paths),
            "paths": paths,
            "path_summaries": path_summaries
        }

    def get_prerequisite_knowledge(self, node_id: str) -> Dict:
        """
        获取前置知识点

        Args:
            node_id: 节点ID

        Returns:
            前置知识点
        """
        # 获取入边邻居
        neighbors = self.kg.get_neighbors(node_id, direction="in")

        prerequisites = []
        for neighbor in neighbors["in"]:
            # 筛选precedes关系
            relations = self.kg.get_relations(neighbor['id'], relation_type="precedes")
            for rel in relations:
                if rel.target_id == node_id:
                    prerequisites.append(neighbor.__dict__)

        return {
            "success": True,
            "node_id": node_id,
            "prerequisite_count": len(prerequisites),
            "prerequisites": prerequisites
        }

    def get_follow_up_knowledge(self, node_id: str) -> Dict:
        """
        获取后续知识点

        Args:
            node_id: 节点ID

        Returns:
            后续知识点
        """
        # 获取出边邻居
        neighbors = self.kg.get_neighbors(node_id, direction="out")

        follow_up = []
        for neighbor in neighbors["out"]:
            # 筛选precedes关系
            relations = self.kg.get_relations(node_id, relation_type="precedes")
            for rel in relations:
                if rel.target_id == neighbor['id']:
                    follow_up.append(neighbor.__dict__)

        return {
            "success": True,
            "node_id": node_id,
            "follow_up_count": len(follow_up),
            "follow_up": follow_up
        }

    def build_knowledge_tree(self, root_node_id: str, max_depth: int = 3) -> Dict:
        """
        构建知识树

        Args:
            root_node_id: 根节点ID
            max_depth: 最大深度

        Returns:
            知识树结构
        """
        def build_tree(node_id: str, depth: int) -> Dict:
            if depth > max_depth:
                return None

            node = self.kg.get_node(node_id)
            if not node:
                return None

            # 获取子节点
            neighbors = self.kg.get_neighbors(node_id, direction="out")
            children = []

            for neighbor in neighbors["out"]:
                # 只添加contains关系
                relations = self.kg.get_relations(node_id, relation_type="contains")
                for rel in relations:
                    if rel.target_id == neighbor['id']:
                        child_tree = build_tree(neighbor['id'], depth + 1)
                        if child_tree:
                            children.append(child_tree)

            return {
                "id": node.id,
                "title": node.metadata.get('title', node.type),
                "type": node.type,
                "content": node.content[:100],
                "depth": depth,
                "children": children
            }

        tree = build_tree(root_node_id, 0)

        return {
            "success": True,
            "root_node_id": root_node_id,
            "max_depth": max_depth,
            "tree": tree
        }

    def suggest_learning_sequence(self, chapter_id: str) -> Dict:
        """
        建议学习顺序

        Args:
            chapter_id: 章节ID

        Returns:
            学习顺序建议
        """
        # 获取章节下的所有概念
        relations = self.kg.get_relations(chapter_id)
        concept_ids = []

        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node and node.type == "concept":
                    concept_ids.append((node.id, rel.metadata.get('order', 999)))

        # 按order排序
        concept_ids.sort(key=lambda x: x[1])

        # 构建学习顺序
        learning_sequence = []
        for cid, order in concept_ids:
            node = self.kg.get_node(cid)
            if node:
                # 获取前置知识
                prereq = self.get_prerequisite_knowledge(cid)

                learning_sequence.append({
                    "order": len(learning_sequence) + 1,
                    "concept_id": cid,
                    "title": node.metadata.get('title', '未命名'),
                    "content": node.content[:100],
                    "prerequisites": [p['metadata']['title'] for p in prereq['prerequisites']],
                    "estimated_time": "10-15分钟"
                })

        return {
            "success": True,
            "chapter_id": chapter_id,
            "sequence": learning_sequence,
            "total_concepts": len(learning_sequence)
        }


# CC中调用示例
def cc_knowledge_path_example():
    """
    CC中调用示例：
    追踪知识路径
    """
    return '''
# ============================================
# 教育模式 - 知识路径追踪 - CC中调用示例
# ============================================

# 1. 追踪从起始节点的所有路径
paths = trace_call_path(start_node_id="node_id", max_depth=5)

# 2. 获取前置知识点
neighbors = get_neighbors(node_id="node_id", direction="in")
prerequisites = [n for n in neighbors['in']]

# 3. 获取后续知识点
neighbors = get_neighbors(node_id="node_id", direction="out")
follow_up = [n for n in neighbors['out']]

# 4. 建立知识路径关系
add_relation(
    source_id: "prereq_node_id",
    target_id: "current_node_id",
    relation_type: "precedes"
)

# 5. 获取知识树结构
# 从根节点开始递归获取
def build_knowledge_tree(node_id, depth=0, max_depth=3):
    if depth > max_depth:
        return None

    node = get_node(node_id=node_id)
    if not node:
        return None

    # 获取子节点
    relations = get_relations(node_id=node_id, relation_type="contains")
    children = []

    for rel in relations:
        child_tree = build_knowledge_tree(rel['target_id'], depth + 1, max_depth)
        if child_tree:
            children.append(child_tree)

    return {
        "id": node['id'],
        "title": node['metadata'].get('title', node['type']),
        "children": children
    }
    '''


if __name__ == "__main__":
    # 测试知识路径追踪
    tracker = KnowledgePathTracker()

    print("="*60)
    print("        测试知识路径追踪")
    print("="*60)

    # 获取现有节点
    chapters = tracker.kg.get_all_nodes("chapter")
    if not chapters:
        print("请先运行后台维护系统的测试创建数据")
        exit(1)

    chapter_id = chapters[0].id
    chapter_title = chapters[0].metadata.get("title", "未知章节")

    print(f"\n章节: {chapter_title}")

    # 追踪学习路径
    print("\n1. 追踪学习路径:")
    path_result = tracker.trace_learning_path(chapter_id, max_depth=3)
    print(f"   找到 {path_result['total_paths']} 条路径")
    for i, path in enumerate(path_result['path_summaries'][:3], 1):
        print(f"   路径 {i}: {' -> '.join(path['node_titles'])}")

    # 获取前置知识
    print("\n2. 获取前置知识点:")
    concepts = tracker.kg.get_all_nodes("concept")
    if concepts:
        prereq_result = tracker.get_prerequisite_knowledge(concepts[0].id)
        print(f"   找到 {prereq_result['prerequisite_count']} 个前置知识点")

    # 获取后续知识
    print("\n3. 获取后续知识点:")
    if concepts:
        follow_result = tracker.get_follow_up_knowledge(concepts[0].id)
        print(f"   找到 {follow_result['follow_up_count']} 个后续知识点")

    # 构建知识树
    print("\n4. 构建知识树:")
    tree_result = tracker.build_knowledge_tree(chapter_id, max_depth=2)
    if tree_result['tree']:
        print(f"   根节点: {tree_result['tree']['title']}")
        print(f"   子节点数: {len(tree_result['tree']['children'])}")

    # 建议学习顺序
    print("\n5. 建议学习顺序:")
    sequence_result = tracker.suggest_learning_sequence(chapter_id)
    print(f"   知识点数: {sequence_result['total_concepts']}")
    for item in sequence_result['sequence'][:3]:
        print(f"   {item['order']}. {item['title']}")

    print("\n" + "="*60)
    print("CC中调用示例:")
    print(cc_knowledge_path_example())
