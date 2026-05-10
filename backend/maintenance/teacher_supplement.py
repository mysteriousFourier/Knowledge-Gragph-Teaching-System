"""
后台维护系统 - 老师补充内容解析更新模块
解析老师补充的内容，更新知识图谱和授课文案
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from graph_manager import KnowledgeGraph
from typing import List, Dict, Optional
import json
from datetime import datetime


class TeacherSupplementParser:
    """老师补充内容解析器"""

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def parse_and_update(self, supplement_content: str, chapter_id: Optional[str] = None,
                        teacher_id: str = "teacher_001") -> Dict:
        """
        解析并更新补充内容

        Args:
            supplement_content: 老师补充的内容
            chapter_id: 关联的章节ID
            teacher_id: 老师ID

        Returns:
            更新结果
        """
        results = {
            "success": True,
            "created_nodes": [],
            "updated_nodes": [],
            "created_relations": [],
            "created_notes": []
        }

        # 1. 将补充内容作为笔记存储
        note = self.kg.add_node(
            content=supplement_content,
            type="note",
            metadata={
                "source": "teacher_supplement",
                "teacher_id": teacher_id,
                "chapter_id": chapter_id,
                "created_at": datetime.now().isoformat()
            }
        )
        results["created_notes"].append(note.__dict__)

        # 2. 如果有关联章节，建立关系
        if chapter_id:
            self.kg.add_relation(
                source_id=chapter_id,
                target_id=note.id,
                relation_type="contains",
                metadata={"source": "teacher_supplement"}
            )
            results["created_relations"].append({
                "source": chapter_id,
                "target": note.id,
                "type": "contains"
            })

        # 3. 解析补充内容中的知识点（简化版，实际可用NLP）
        concepts = self._extract_concepts(supplement_content)

        for concept_text in concepts:
            # 检查是否已存在相似概念
            existing = self.kg.search_nodes(concept_text, node_type="concept", limit=1)

            if existing:
                # 更新现有概念
                self.kg.update_node(
                    node_id=existing[0].id,
                    metadata={
                        **existing[0].metadata,
                        "supplement_ref": note.id,
                        "last_supplemented": datetime.now().isoformat()
                    }
                )
                results["updated_nodes"].append(existing[0].id)
            else:
                # 创建新概念
                concept_node = self.kg.add_node(
                    content=concept_text,
                    type="concept",
                    metadata={
                        "source": "teacher_supplement",
                        "supplement_ref": note.id,
                        "chapter_id": chapter_id
                    }
                )
                results["created_nodes"].append(concept_node.__dict__)

                # 建立与补充笔记的关系
                self.kg.add_relation(
                    source_id=note.id,
                    target_id=concept_node.id,
                    relation_type="contains"
                )

        return results

    def _extract_concepts(self, text: str) -> List[str]:
        """
        从文本中提取概念（简化版）
        实际实现可使用NLP工具
        """
        # 简化版：按句号分割，取较长的句子作为概念
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        # 过滤掉太短的句子
        concepts = [s + '。' for s in sentences if len(s) > 10]
        return concepts[:5]  # 最多返回5个概念

    def get_supplements_by_chapter(self, chapter_id: str) -> List[Dict]:
        """获取某章节的所有补充内容"""
        # 获取章节的所有关系
        relations = self.kg.get_relations(chapter_id)

        # 筛选出补充笔记类型的关系
        supplement_ids = []
        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node and node.type == "note" and node.metadata.get("source") == "teacher_supplement":
                    supplement_ids.append(node.id)

        # 返回补充内容
        supplements = []
        for sid in supplement_ids:
            node = self.kg.get_node(sid)
            if node:
                supplements.append(node.__dict__)

        return supplements


# CC中调用示例
def cc_teacher_supplement_example():
    """
    CC中调用示例：
    解析老师补充内容并更新图谱
    """
    return '''
# 在CC中，通过MCP工具调用：

# 1. 老师补充内容后，解析并更新
supplement_content = """
同学们，关于向量空间我再补充一点：
1. 向量空间的基必须满足线性无关性
2. 维数就是基中向量的个数
3. 任何有限维向量空间都有基
"""

# 2. 添加补充笔记
note = add_memory(
  content: supplement_content,
  type: "note",
  metadata: {
    "source": "teacher_supplement",
    "teacher_id": "teacher_001",
    "chapter_id": "chapter_123",
    "created_at": "2026-04-08T20:00:00"
  }
)

# 3. 建立与章节的关系
add_relation(
  source_id: "chapter_123",
  target_id: note.id,
  relation_type: "contains",
  metadata: {"source": "teacher_supplement"}
)

# 4. 从补充内容中提取概念（CC中用NLP处理）
concepts = extract_concepts(supplement_content)  # CC中的函数
for concept_text in concepts:
    # 检查是否已存在
    existing = search_nodes(keyword=concept_text, node_type="concept", limit=1)

    if existing:
        # 更新现有概念
        update_memory(
            node_id: existing[0].id,
            metadata: {
                **existing[0].metadata,
                "supplement_ref": note.id
            }
        )
    else:
        # 创建新概念
        concept = add_memory(
            content: concept_text,
            type: "concept",
            metadata: {
                "source": "teacher_supplement",
                "supplement_ref": note.id
            }
        )
        # 建立关系
        add_relation(
            source_id: note.id,
            target_id: concept.id,
            relation_type: "contains"
        )
    '''


if __name__ == "__main__":
    # 测试补充内容解析
    parser = TeacherSupplementParser()

    print("="*50)
    print("测试老师补充内容解析")
    print("="*50)

    # 获取现有章节
    chapters = parser.kg.get_all_nodes("chapter")
    if not chapters:
        print("请先运行 import_chapter.py 添加测试数据")
        exit(1)

    chapter_id = chapters[0].id
    chapter_title = chapters[0].metadata.get("title", "未知章节")

    # 模拟老师补充内容
    supplement_text = """
    关于向量空间我再补充几点：
    第一，向量空间的基必须满足线性无关性，这意味着基中的向量不能互相表示。
    第二，维数就是基中向量的个数，这是向量空间的基本属性。
    第三，任何有限维向量空间都有基，而且同一个空间的不同基所含向量个数相同。
    """

    print(f"\n章节: {chapter_title}")
    print(f"补充内容:\n{supplement_text}")

    # 解析并更新
    print("\n正在解析并更新...")
    result = parser.parse_and_update(supplement_text, chapter_id)

    print(f"\n更新结果:")
    print(f"  创建笔记: {len(result['created_notes'])} 个")
    print(f"  创建节点: {len(result['created_nodes'])} 个")
    print(f"  更新节点: {len(result['updated_nodes'])} 个")
    print(f"  创建关系: {len(result['created_relations'])} 个")

    # 获取该章节的所有补充
    print("\n该章节的所有补充内容:")
    supplements = parser.get_supplements_by_chapter(chapter_id)
    for i, sup in enumerate(supplements, 1):
        print(f"\n补充 {i}:")
        print(f"  内容: {sup['content'][:50]}...")
        print(f"  时间: {sup['metadata']['created_at']}")

    print("\n" + "="*50)
    print("CC中调用示例:")
    print(cc_teacher_supplement_example())
