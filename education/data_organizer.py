"""
教育模式 - 数据组织与展示模块
将原始图谱数据组织成适合前端展示的格式
"""

from KGTS.config import EduConfig
from typing import List, Dict, Optional
import json


class DataOrganizer:
    """数据组织器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = EduConfig.BACKEND_DB_PATH
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
        return {
            "success": True,
            "nodes": [],
            "edges": [],
            "stats": {},
            "message": "Use KGTS.education.router endpoints for graph data"
        }

    def _organize_chapter_data(self, chapter_id: str) -> Dict:
        """组织章节数据"""
        return {
            "success": True,
            "chapter": {"id": chapter_id},
            "concepts": [],
            "notes": [],
            "lectures": [],
            "stats": {
                "concepts": 0,
                "notes": 0,
                "lectures": 0
            }
        }

    def _organize_lecture_data(self, chapter_id: str) -> Dict:
        """组织授课文案数据"""
        chapter_data = self._organize_chapter_data(chapter_id)

        if not chapter_data["success"]:
            return chapter_data

        return {
            "success": True,
            "chapter": chapter_data["chapter"],
            "latest_lecture": None,
            "all_lectures": [],
            "concepts": chapter_data["concepts"]
        }

    def _organize_exercise_data(self, chapter_id: str) -> Dict:
        """组织练习题数据"""
        chapter_data = self._organize_chapter_data(chapter_id)

        if not chapter_data["success"]:
            return chapter_data

        exercises_by_concept = {}
        for concept in chapter_data["concepts"]:
            exercises_by_concept[concept["id"]] = {
                "concept": concept,
                "exercises": []
            }

        return {
            "success": True,
            "chapter": chapter_data["chapter"],
            "exercises_by_concept": exercises_by_concept,
            "concepts": chapter_data["concepts"]
        }

    def _organize_qa_history(self, user_id: str) -> Dict:
        """组织问答历史"""
        return {
            "success": True,
            "user_id": user_id,
            "qa_history": []
        }

    def format_for_markdown(self, content: str) -> str:
        """格式化为Markdown"""
        lines = content.split('\n')
        formatted_lines = []

        for line in lines:
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
        sorted_items = sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)

        timeline = []
        for i, item in enumerate(sorted_items):
            timeline.append({
                "index": i + 1,
                "time": item.get("timestamp", "")[:19],
                "title": item.get("title", item.get("type", "事件")),
                "description": item.get("content", "")[:100],
                "type": item.get("type", "unknown"),
                "metadata": item.get("metadata", {})
            })

        return timeline


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
