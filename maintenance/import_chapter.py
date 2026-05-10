"""Chapter import module: import PDF textbook content into the knowledge graph."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from KGTS.core.graph_manager import KnowledgeGraph


class ChapterImporter:

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def import_chapter(self, content: str, title: str, parent_id: Optional[str] = None,
                       order: Optional[int] = None) -> Dict:
        chapter_node = self.kg.add_node(
            content=content,
            type="chapter",
            metadata={
                "title": title,
                "order": order,
                "parent_id": parent_id
            }
        )

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
