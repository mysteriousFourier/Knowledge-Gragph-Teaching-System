"""
后台维护系统 - 导入章节模块
将PDF教材内容导入知识图谱
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from graph_manager import KnowledgeGraph
from typing import List, Dict, Optional
import json


class ChapterImporter:
    """章节导入器"""

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def import_chapter(self, content: str, title: str, parent_id: Optional[str] = None,
                       order: Optional[int] = None) -> Dict:
        """
        导入单个章节

        Args:
            content: 章节内容
            title: 章节标题
            parent_id: 父节点ID（用于建立层级关系）
            order: 章节顺序

        Returns:
            导入结果
        """
        # 添加章节节点
        chapter_node = self.kg.add_node(
            content=content,
            type="chapter",
            metadata={
                "title": title,
                "order": order,
                "parent_id": parent_id
            }
        )

        # 如果有父节点，建立关系
        if parent_id:
            self.kg.add_relation(
                source_id=parent_id,
                target_id=chapter_node.id,
                relation_type="contains",
                metadata={"order": order}
            )

        return {
            "success": True,
            "node_id": chapter_node.id,
            "title": title,
            "message": f"章节 '{title}' 导入成功"
        }

    def import_chapter_from_file(self, file_path: str, title: Optional[str] = None,
                                  parent_id: Optional[str] = None) -> Dict:
        """
        从文件导入章节

        Args:
            file_path: 文件路径
            title: 章节标题（不指定则使用文件名）
            parent_id: 父节点ID

        Returns:
            导入结果
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if title is None:
                title = os.path.basename(file_path).replace('.txt', '')

            return self.import_chapter(content, title, parent_id)

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"导入文件失败: {file_path}"
            }

    def batch_import(self, chapters: List[Dict]) -> List[Dict]:
        """
        批量导入章节

        Args:
            chapters: 章节列表，每个元素包含 content, title, parent_id, order

        Returns:
            导入结果列表
        """
        results = []
        for i, chapter in enumerate(chapters):
            result = self.import_chapter(
                content=chapter.get("content", ""),
                title=chapter.get("title", f"第{i+1}章"),
                parent_id=chapter.get("parent_id"),
                order=chapter.get("order", i+1)
            )
            results.append(result)

        return results


# CC中调用示例
def cc_import_chapter_example():
    """
    CC中调用示例：
    通过MCP工具调用 add_memory 导入章节
    """
    example_code = '''
    # 在CC中，通过MCP工具调用：

    # 1. 添加章节
    add_memory(
      content: "第三章：向量空间的主要内容...",
      type: "chapter",
      metadata: {
        "title": "第三章：向量空间",
        "order": 3,
        "parent_id": "root_chapter_id"
      }
    )

    # 2. 添加概念
    add_memory(
      content: "向量是具有大小和方向的量...",
      type: "concept",
      metadata: {
        "title": "向量定义",
        "chapter_id": "chapter_id_from_step_1"
      }
    )

    # 3. 建立关系
    add_relation(
      source_id: "chapter_id_from_step_1",
      target_id: "concept_id_from_step_2",
      relation_type: "contains"
    )
    '''
    return example_code


if __name__ == "__main__":
    # 测试导入功能
    importer = ChapterImporter()

    # 示例：导入一个章节
    test_chapter = """
    第三章：向量空间

    3.1 向量的定义
    向量是具有大小和方向的量。在n维空间中，向量可以表示为有序的n元组。

    3.2 向量的运算
    向量的加法、减法、数乘运算满足以下性质...
    """

    result = importer.import_chapter(
        content=test_chapter.strip(),
        title="第三章：向量空间",
        order=3
    )

    print("导入结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n" + "="*50)
    print("CC中调用示例:")
    print(cc_import_chapter_example())
