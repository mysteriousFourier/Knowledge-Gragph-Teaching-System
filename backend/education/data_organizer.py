"""
教育模式 - 数据组织与展示模块
将原始图谱数据组织成适合前端展示的格式
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


class DataOrganizer:
    """数据组织器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = EduConfig.BACKEND_DB_PATH
        self.kg = KnowledgeGraph(db_path)
        self.config = EduConfig

    def organize_for_frontend(self, data_type: str, **kwargs) -> Dict:
        """
        为前端组织数据

        Args:
            data_type: 数据类型 (graph, chapter, lecture, exercise, etc.)
            **kwargs: 额外参数

        Returns:
            组织后的数据
        """
        if data_type == "graph":
            return self._organize_graph_data()
        elif data_type == "chapter":
            return self._organize_chapter_data(kwargs.get("chapter_id"))
        elif data_type == "lecture":
            return self._organize_lecture_data(kwargs.get("chapter_id"))
        elif data_type == "exercise":
            return self._organize_exercise_data(kwargs.get("chapter_id"))
        elif data_type == "qa_history":
            return self._organize_qa_history(kwargs.get("user_id"))
        else:
            return {"success": False, "error": f"Unknown data type: {data_type}"}

    def _organize_graph_data(self) -> Dict:
        """组织图谱数据用于前端可视化"""
        graph = self.kg.get_graph_structure()

        # 转换节点格式
        nodes = []
        for node in graph['nodes']:
            nodes.append({
                "id": node['id'],
                "label": node['metadata'].get('title', node['type']),
                "type": node['type'],
                "content": node['content'],
                "metadata": node['metadata']
            })

        # 转换关系格式
        edges = []
        for rel in graph['relations']:
            edges.append({
                "id": rel['id'],
                "source": rel['source_id'],
                "target": rel['target_id'],
                "label": rel['relation_type'],
                "type": rel['relation_type'],
                "similarity": rel['similarity']
            })

        return {
            "success": True,
            "nodes": nodes,
            "edges": edges,
            "stats": graph['stats']
        }

    def _organize_chapter_data(self, chapter_id: str) -> Dict:
        """组织章节数据"""
        chapter = self.kg.get_node(chapter_id)
        if not chapter:
            return {"success": False, "error": "章节不存在"}

        # 获取章节下的所有内容
        relations = self.kg.get_relations(chapter_id)

        concepts = []
        notes = []
        lectures = []

        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node:
                    if node.type == "concept":
                        concepts.append(node.__dict__)
                    elif node.type == "note":
                        notes.append(node.__dict__)
                    elif node.type == "observation" and node.metadata.get("source") == "ai_lecture":
                        lectures.append(node.__dict__)

        return {
            "success": True,
            "chapter": chapter.__dict__,
            "concepts": concepts,
            "notes": notes,
            "lectures": lectures,
            "stats": {
                "concepts": len(concepts),
                "notes": len(notes),
                "lectures": len(lectures)
            }
        }

    def _organize_lecture_data(self, chapter_id: str) -> Dict:
        """组织授课文案数据"""
        chapter_data = self._organize_chapter_data(chapter_id)

        if not chapter_data["success"]:
            return chapter_data

        # 获取最新的授课文案
        lectures = chapter_data["lectures"]
        if lectures:
            # 按创建时间排序
            lectures.sort(key=lambda x: x["metadata"].get("created_at", ""), reverse=True)
            latest_lecture = lectures[0]
        else:
            latest_lecture = None

        return {
            "success": True,
            "chapter": chapter_data["chapter"],
            "latest_lecture": latest_lecture,
            "all_lectures": lectures,
            "concepts": chapter_data["concepts"]
        }

    def _organize_exercise_data(self, chapter_id: str) -> Dict:
        """组织练习题数据"""
        chapter_data = self._organize_chapter_data(chapter_id)

        if not chapter_data["success"]:
            return chapter_data

        # 按概念组织练习题
        exercises_by_concept = {}
        for concept in chapter_data["concepts"]:
            exercises_by_concept[concept["id"]] = {
                "concept": concept,
                "exercises": []  # 实际需要从练习题数据表获取
            }

        return {
            "success": True,
            "chapter": chapter_data["chapter"],
            "exercises_by_concept": exercises_by_concept,
            "concepts": chapter_data["concepts"]
        }

    def _organize_qa_history(self, user_id: str) -> Dict:
        """组织问答历史"""
        # 获取用户的问答记录
        # (实际实现需要从问答历史表获取)

        # 这里返回示例格式
        return {
            "success": True,
            "user_id": user_id,
            "qa_history": [
                {
                    "question": "什么是向量空间？",
                    "answer": "向量空间是一个满足特定公理的集合...",
                    "timestamp": "2026-04-08T10:00:00",
                    "related_concepts": ["向量", "空间", "线性"]
                }
            ]
        }

    def format_for_markdown(self, content: str) -> str:
        """格式化为Markdown"""
        # 确保内容是有效的Markdown
        lines = content.split('\n')
        formatted_lines = []

        for line in lines:
            # 清理多余的空格
            line = line.strip()
            if line:
                formatted_lines.append(line)

        return '\n'.join(formatted_lines)

    def format_concept_cards(self, concepts: List[Dict]) -> List[Dict]:
        """格式化概念卡片"""
        cards = []

        for concept in concepts:
            cards.append({
                "id": concept["id"],
                "title": concept["metadata"].get("title", "未命名"),
                "content": concept["content"][:200] + "..." if len(concept["content"]) > 200 else concept["content"],
                "type": concept["type"],
                "difficulty": concept["metadata"].get("difficulty", "unknown"),
                "tags": concept["metadata"].get("tags", [])
            })

        return cards

    def format_timeline(self, items: List[Dict]) -> List[Dict]:
        """格式化时间线"""
        # 按时间排序
        sorted_items = sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)

        timeline = []
        for i, item in enumerate(sorted_items):
            timeline.append({
                "index": i + 1,
                "time": item.get("timestamp", "")[:19],  # 只取到秒
                "title": item.get("title", item.get("type", "事件")),
                "description": item.get("content", "")[:100],
                "type": item.get("type", "unknown"),
                "metadata": item.get("metadata", {})
            })

        return timeline


# CC中调用示例
def cc_data_organization_example():
    """
    CC中调用示例：
    组织数据用于前端展示
    """
    return '''
# ============================================
# 教育模式 - 数据组织与展示 - CC中调用示例
# ============================================

# 1. 获取图谱数据
graph = read_graph()

# 2. 组织节点数据用于可视化
nodes = []
for node in graph['nodes']:
    nodes.append({
        "id": node['id'],
        "label": node['metadata'].get('title', node['type']),
        "type": node['type'],
        "group": node['type'],  # 用于着色分组
        "size": 20 if node['type'] == 'chapter' else 10
    })

# 3. 组织边数据
edges = []
for edge in graph['relations']:
    edges.append({
        "id": edge['id'],
        "source": edge['source_id'],
        "target": edge['target_id'],
        "label": edge['relation_type'],
        "type": edge['relation_type']
    })

# 4. 返回给前端可视化库
# 前端使用 D3.js, Cytoscape.js, ECharts 等库渲染

# 5. 组织章节数据
chapter = get_node(node_id="chapter_id")
relations = get_relations(node_id="chapter_id")

concepts = []
for rel in relations:
    if rel['relation_type'] == "contains":
        node = get_node(node_id=rel['target_id'])
        if node and node['type'] == "concept":
            concepts.append({
                "id": node['id'],
                "title": node['metadata']['title'],
                "content": node['content'],
                "difficulty": node['metadata'].get('difficulty', 'unknown')
            })

# 6. 组织授课文案数据
lecture = get_note()  # 获取授课文案

# 7. 格式化Markdown内容
formatted_content = content.replace('\\n', '\\n\\n')  # 添加段落间距

# 8. 格式化时间线
timeline_items = sorted(items, key=lambda x: x['timestamp'], reverse=True)
    '''


if __name__ == "__main__":
    # 测试数据组织
    organizer = DataOrganizer()

    print("="*60)
    print("        测试数据组织与展示")
    print("="*60)

    # 组织图谱数据
    print("\n1. 组织图谱数据:")
    graph_data = organizer._organize_graph_data()
    print(f"   节点数: {len(graph_data['nodes'])}")
    print(f"   边数: {len(graph_data['edges'])}")
    print(f"\n   节点类型:")
    for node_type in set(n['type'] for n in graph_data['nodes']):
        count = sum(1 for n in graph_data['nodes'] if n['type'] == node_type)
        print(f"     {node_type}: {count}")

    # 组织章节数据
    chapters = organizer.kg.get_all_nodes("chapter")
    if chapters:
        print("\n2. 组织章节数据:")
        chapter_data = organizer._organize_chapter_data(chapters[0].id)
        print(f"   章节: {chapter_data['chapter']['metadata']['title']}")
        print(f"   概念数: {chapter_data['stats']['concepts']}")
        print(f"   笔记数: {chapter_data['stats']['notes']}")
        print(f"   授课文案数: {chapter_data['stats']['lectures']}")

    # 组织授课文案数据
    if chapters:
        print("\n3. 组织授课文案数据:")
        lecture_data = organizer._organize_lecture_data(chapters[0].id)
        if lecture_data['latest_lecture']:
            print(f"   最新文案ID: {lecture_data['latest_lecture']['id']}")
            print(f"   内容长度: {len(lecture_data['latest_lecture']['content'])}")
        else:
            print("   暂无授课文案")

    # 格式化概念卡片
    if chapters:
        print("\n4. 格式化概念卡片:")
        chapter_data = organizer._organize_chapter_data(chapters[0].id)
        cards = organizer.format_concept_cards(chapter_data['concepts'])
        for card in cards[:3]:
            print(f"   - {card['title']}: {card['content'][:30]}...")

    print("\n" + "="*60)
    print("CC中调用示例:")
    print(cc_data_organization_example())
