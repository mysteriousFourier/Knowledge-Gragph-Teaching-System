"""
后台维护系统 - 授课文案数据更新模块
管理AI生成的授课文案，支持存储、查询和更新
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from graph_manager import KnowledgeGraph
from typing import List, Dict, Optional
import json
from datetime import datetime


class LectureNoteManager:
    """授课文案管理器"""

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def store_lecture_note(self, content: str, chapter_id: str, teacher_id: str = "teacher_001",
                          metadata: Optional[Dict] = None) -> Dict:
        """
        存储授课文案

        Args:
            content: 授课文案内容
            chapter_id: 关联的章节ID
            teacher_id: 老师ID
            metadata: 额外元数据

        Returns:
            存储结果
        """
        note_metadata = {
            "source": "ai_lecture",
            "teacher_id": teacher_id,
            "chapter_id": chapter_id,
            "created_at": datetime.now().isoformat(),
            "status": "draft",  # draft, approved, used
            **(metadata or {})
        }

        # 存储为observation类型节点
        note = self.kg.add_node(content, type="observation", metadata=note_metadata)

        # 建立与章节的关系
        self.kg.add_relation(
            source_id=chapter_id,
            target_id=note.id,
            relation_type="contains",
            metadata={"type": "lecture_note"}
        )

        return {
            "success": True,
            "note_id": note.id,
            "metadata": note_metadata
        }

    def get_lecture_note(self, note_id: str) -> Optional[Dict]:
        """获取单条授课文案"""
        note = self.kg.get_node(note_id)
        if note and note.type == "observation":
            return note.__dict__
        return None

    def get_lecture_notes_by_chapter(self, chapter_id: str) -> List[Dict]:
        """获取某章节的所有授课文案"""
        relations = self.kg.get_relations(chapter_id)

        note_ids = []
        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node and node.type == "observation" and node.metadata.get("source") == "ai_lecture":
                    note_ids.append(node.id)

        notes = []
        for nid in note_ids:
            node = self.kg.get_node(nid)
            if node:
                notes.append(node.__dict__)

        return notes

    def get_latest_lecture_note(self, chapter_id: str) -> Optional[Dict]:
        """获取某章节的最新授课文案"""
        notes = self.get_lecture_notes_by_chapter(chapter_id)
        if notes:
            # 按创建时间排序
            notes.sort(key=lambda x: x["metadata"]["created_at"], reverse=True)
            return notes[0]
        return None

    def update_lecture_note(self, note_id: str, content: Optional[str] = None,
                           metadata: Optional[Dict] = None) -> Dict:
        """更新授课文案"""
        success = self.kg.update_node(note_id, content, metadata)
        return {
            "success": success,
            "note_id": note_id
        }

    def approve_lecture_note(self, note_id: str, teacher_id: str) -> Dict:
        """审核通过授课文案"""
        note = self.kg.get_node(note_id)
        if not note:
            return {"success": False, "error": "Note not found"}

        # 更新状态
        success = self.kg.update_node(
            note_id,
            metadata={
                **note.metadata,
                "status": "approved",
                "approved_by": teacher_id,
                "approved_at": datetime.now().isoformat()
            }
        )

        return {"success": success, "note_id": note_id}

    def delete_lecture_note(self, note_id: str) -> Dict:
        """删除授课文案"""
        success = self.kg.delete_node(note_id)
        return {"success": success, "note_id": note_id}

    def search_lecture_notes(self, keyword: str) -> List[Dict]:
        """搜索授课文案"""
        nodes = self.kg.search_nodes(keyword, node_type="observation")

        # 过滤出授课文案类型的observation
        lecture_notes = [
            node.__dict__ for node in nodes
            if node.metadata.get("source") == "ai_lecture"
        ]

        return lecture_notes


# CC中调用示例
def cc_lecture_note_example():
    """
    CC中调用示例：
    管理授课文案
    """
    return '''
# 在CC中，通过MCP工具调用：

# 1. 存储AI生成的授课文案
note = add_memory(
  content: "今天我们学习向量空间的基本概念...",
  type: "observation",
  metadata: {
    "source": "ai_lecture",
    "teacher_id": "teacher_001",
    "chapter_id": "chapter_123",
    "created_at": "2026-04-08T20:00:00",
    "status": "draft"
  }
)

# 2. 建立与章节的关系
add_relation(
  source_id: "chapter_123",
  target_id: note.id,
  relation_type: "contains",
  metadata: {"type": "lecture_note"}
)

# 3. 获取授课文案（通过get_note工具）
notes = get_note()  # 获取所有observation类型节点
# 或
note_detail = get_note(node_id=note.id)

# 4. 老师修改授课文案
update_memory(
  node_id: note.id,
  content: "修改后的授课文案内容...",
  metadata: {"status": "modified", "modified_by": "teacher_001"}
)

# 5. 审核通过授课文案
update_memory(
  node_id: note.id,
  metadata: {
    "status": "approved",
    "approved_by": "teacher_001",
    "approved_at": "2026-04-08T21:00:00"
  }
)

# 6. 学生查询授课文案
student_notes = get_note()  # 获取所有approved状态的notes
    '''


if __name__ == "__main__":
    # 测试授课文案管理
    manager = LectureNoteManager()

    print("="*50)
    print("测试授课文案管理")
    print("="*50)

    # 获取现有章节
    chapters = manager.kg.get_all_nodes("chapter")
    if not chapters:
        print("请先运行 import_chapter.py 添加测试数据")
        exit(1)

    chapter_id = chapters[0].id
    chapter_title = chapters[0].metadata.get("title", "未知章节")

    # 模拟AI生成的授课文案
    lecture_content = """
    大家好，今天我们学习""" + chapter_title + """。

    首先让我们理解向量空间的基本概念。向量空间是一个集合，其中的元素叫做向量。

    向量空间需要满足一些基本性质：
    1. 对加法封闭：两个向量相加还是向量
    2. 对数乘封闭：向量乘以标量还是向量
    3. 存在零向量
    4. 每个向量都有负向量

    接下来我们学习向量的线性组合和线性相关...

    好了，今天的课程就到这里，大家有什么问题吗？
    """

    print(f"\n章节: {chapter_title}")
    print(f"AI生成的授课文案:\n{lecture_content}")

    # 存储授课文案
    print("\n正在存储授课文案...")
    result = manager.store_lecture_note(lecture_content, chapter_id)
    print(f"存储成功，ID: {result['note_id']}")

    # 获取授课文案
    print("\n获取存储的授课文案:")
    note = manager.get_lecture_note(result['note_id'])
    if note:
        print(f"  内容长度: {len(note['content'])} 字符")
        print(f"  状态: {note['metadata']['status']}")
        print(f"  创建时间: {note['metadata']['created_at']}")

    # 更新授课文案（老师修改）
    print("\n老师修改授课文案:")
    updated_content = lecture_content + "\n\n补充：大家要特别注意向量的维数概念！"
    manager.update_lecture_note(result['note_id'], updated_content, {"status": "modified"})
    print("  修改成功")

    # 审核通过
    print("\n审核通过授课文案:")
    manager.approve_lecture_note(result['note_id'], "teacher_001")
    print("  审核成功")

    # 获取章节所有授课文案
    print("\n该章节的所有授课文案:")
    all_notes = manager.get_lecture_notes_by_chapter(chapter_id)
    for i, note in enumerate(all_notes, 1):
        print(f"  {i}. {note['id']} - 状态: {note['metadata']['status']}")

    # 获取最新授课文案
    print("\n最新授课文案:")
    latest = manager.get_latest_lecture_note(chapter_id)
    if latest:
        print(f"  ID: {latest['id']}")
        print(f"  状态: {latest['metadata']['status']}")
        print(f"  内容摘要: {latest['content'][:50]}...")

    print("\n" + "="*50)
    print("CC中调用示例:")
    print(cc_lecture_note_example())
