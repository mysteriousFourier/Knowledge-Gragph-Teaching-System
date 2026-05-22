"""
教育模式 - AI授课文案生成模块
基于知识图谱生成授课文案
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
from graph_query import GraphQuery
from graph_search import GraphSearch
from edu_config import EduConfig
from kg_constraints import build_constrained_generation_prompt, build_learning_plan
from typing import List, Dict, Optional
import json


class LectureGenerator:
    """授课文案生成器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = EduConfig.BACKEND_DB_PATH
        self.kg = KnowledgeGraph(db_path)
        self.query = GraphQuery(db_path)
        self.search = GraphSearch(db_path)
        self.config = EduConfig()

    def generate_lecture(self, chapter_id: str, style: Optional[str] = None,
                        length: Optional[str] = None) -> Dict:
        """
        生成授课文案

        Args:
            chapter_id: 章节ID
            style: 授课风格
            length: 文案长度

        Returns:
            生成的授课文案和相关信息
        """
        style = style or self.config.LECTURE_STYLE
        length = length or self.config.LECTURE_LENGTH

        # 1. 获取章节信息
        chapter = self.kg.get_node(chapter_id)
        if not chapter:
            return {"success": False, "error": "章节不存在"}

        # 2. 获取章节下的所有知识点
        relations = self.kg.get_relations(chapter_id)
        concept_ids = []

        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node and node.type == "concept":
                    concept_ids.append(node.id)

        # 3. 获取概念详情
        concepts = []
        for cid in concept_ids:
            concept = self.kg.get_node(cid)
            if concept:
                concepts.append(concept.__dict__)

        # 4. 按顺序组织知识点
        concepts = self._organize_concepts(concepts, relations)

        # 5. 构建知识点上下文
        knowledge_context = self._build_knowledge_context(chapter, concepts)

        # 6. 生成授课文案
        lecture_data = self._generate_lecture_content(
            chapter, concepts, style, length, knowledge_context
        )

        # 7. 返回结果
        return {
            "success": True,
            "chapter": chapter.__dict__,
            "concepts": concepts,
            "lecture_data": lecture_data,
            "style": style,
            "length": length,
            "timestamp": self._get_timestamp()
        }

    def _organize_concepts(self, concepts: List[Dict], relations: List) -> List[Dict]:
        """按顺序组织知识点"""
        # 简化版：按关系中的order排序
        ordered_concepts = []

        # 创建ID到概念的映射
        concept_map = {c['id']: c for c in concepts}

        # 遍历关系，按order排序
        concept_relations = [r for r in relations if r.relation_type == "contains"]
        concept_relations.sort(key=lambda x: x.metadata.get('order', 999))

        for rel in concept_relations:
            if rel.target_id in concept_map:
                ordered_concepts.append(concept_map[rel.target_id])

        # 添加剩余的概念
        for c in concepts:
            if c not in ordered_concepts:
                ordered_concepts.append(c)

        return ordered_concepts

    def _build_knowledge_context(self, chapter, concepts: List[Dict]) -> str:
        """构建知识点上下文"""
        context = f"章节：{chapter.metadata.get('title', '未命名章节')}\n\n"

        context += "知识点列表：\n"
        for i, concept in enumerate(concepts, 1):
            title = concept['metadata'].get('title', f'知识点{i}')
            content = concept['content']
            context += f"\n{i}. {title}\n{content}\n"

        return context

    def _generate_lecture_content(self, chapter, concepts: List[Dict],
                                  style: str, length: str, knowledge_context: str) -> Dict:
        """生成授课文案内容"""
        evidence = [
            {
                "id": concept["id"],
                "label": concept["metadata"].get("title", concept["id"]),
                "type": concept.get("type", "concept"),
                "content": concept.get("content", ""),
                "source": "graph",
            }
            for concept in concepts
        ]
        learning_plan = build_learning_plan(
            query=chapter.metadata.get("title", chapter.id),
            evidence=evidence,
            learner_intent="explain",
            learning_level="beginner",
            task="lecture",
            chapter_data={
                "id": chapter.id,
                "title": chapter.metadata.get("title", "未命名章节"),
                "content": chapter.content,
            },
        )
        prompt = build_constrained_generation_prompt(
            task_title="生成授课文案",
            user_input=chapter.metadata.get("title", chapter.id),
            source_content=knowledge_context,
            learning_plan=learning_plan,
            requirements=[
                f"生成{length}长度的授课文案。",
                f"授课风格：{style}。",
                "用通俗易懂的语言讲解。",
                "互动提问必须基于图谱证据。",
                "总结重点内容，未由图谱或章节证据支持的延伸要明确标注为补充说明。",
                "英文原文、术语、公式和变量名保持英文；中文讲解只做辅助，不要改写原义。",
                "文案要连贯自然。",
            ],
        )

        # 获取知识点摘要
        concept_summaries = []
        for concept in concepts:
            summary = concept['content'][:100].replace('\n', ' ') + "..."
            concept_summaries.append({
                "title": concept['metadata'].get('title', '未命名'),
                "summary": summary
            })

        return {
            "prompt": prompt,
            "knowledge_context": knowledge_context,
            "concept_summaries": concept_summaries,
            "learning_plan": learning_plan,
            "estimated_length": self._estimate_length(length, len(concepts))
        }

    def _estimate_length(self, length: str, concept_count: int) -> int:
        """估算文案长度"""
        base_length = {
            "短": 200,
            "中等": 500,
            "长": 1000
        }
        return base_length.get(length, 500) + concept_count * 100

    def update_lecture_with_supplement(self, lecture_content: str,
                                      supplement_content: str) -> Dict:
        """
        用补充内容更新授课文案

        Args:
            lecture_content: 原授课文案
            supplement_content: 补充内容

        Returns:
            更新后的文案
        """
        prompt = f"""原授课文案：
{lecture_content}

老师补充内容：
{supplement_content}

请将补充内容自然地融入到授课文案中，保持文案的连贯性。"""

        return {
            "prompt": prompt,
            "original_length": len(lecture_content),
            "supplement_length": len(supplement_content)
        }

    def generate_lecture_outline(self, chapter_id: str) -> Dict:
        """
        生成授课大纲

        Args:
            chapter_id: 章节ID

        Returns:
            授课大纲
        """
        # 获取章节信息
        chapter = self.kg.get_node(chapter_id)
        if not chapter:
            return {"success": False, "error": "章节不存在"}

        # 获取知识点
        relations = self.kg.get_relations(chapter_id)
        concepts = []

        for rel in relations:
            if rel.relation_type == "contains":
                node = self.kg.get_node(rel.target_id)
                if node and node.type == "concept":
                    concepts.append(node.__dict__)

        # 按顺序组织
        concepts = self._organize_concepts(concepts, relations)

        # 生成大纲
        outline = {
            "chapter": chapter.metadata.get('title', '未命名章节'),
            "introduction": "课程导入，介绍本章学习目标",
            "main_points": []
        }

        for concept in concepts:
            title = concept['metadata'].get('title', '未命名')
            content = concept['content'][:50].replace('\n', ' ') + "..."
            outline["main_points"].append({
                "title": title,
                "content": content,
                "estimated_time": "5-10分钟"
            })

        outline["summary"] = "总结本章重点，布置思考题"
        outline["qa"] = "答疑环节"

        return {
            "success": True,
            "outline": outline,
            "concept_count": len(concepts)
        }

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


# CC中调用示例
def cc_lecture_generation_example():
    """
    CC中调用示例：
    通过MCP工具生成授课文案
    """
    return '''
# ============================================
# 教育模式 - 授课文案生成 - CC中调用示例
# ============================================

# 1. 获取章节信息
chapter = get_node(node_id="chapter_id")

# 2. 获取章节下的所有概念
relations = get_relations(node_id="chapter_id")
concept_ids = []

for rel in relations:
    if rel['relation_type'] == "contains":
        target_node = get_node(node_id=rel['target_id'])
        if target_node and target_node['type'] == "concept":
            concept_ids.append(target_node['id'])

# 3. 获取概念详情
concepts = []
for cid in concept_ids:
    concept = get_node(node_id=cid)
    if concept:
        concepts.append(concept)

# 4. 构建知识点上下文
knowledge_context = f"章节：{chapter['metadata']['title']}\\n\\n"
knowledge_context += "知识点列表：\\n"

for i, concept in enumerate(concepts, 1):
    title = concept['metadata'].get('title', f'知识点{i}')
    content = concept['content']
    knowledge_context += f"\\n{i}. {title}\\n{content}\\n"

# 5. 生成授课文案（CC中用Claude生成）
lecture_prompt = f"""你是老师，请基于以下知识点生成授课文案。

授课风格：引导式教学

知识点：
{knowledge_context}

要求：
1. 用通俗易懂的语言讲解
2. 适当举例说明
3. 设置互动提问
4. 总结重点内容
5. 文案要连贯自然"""

# 6. Claude生成文案
# (CC会自动处理这个prompt)

# 7. 存储生成的授课文案
lecture_note = add_memory(
    content: "生成的授课文案内容...",
    type: "observation",
    metadata: {
        "source": "ai_lecture",
        "chapter_id": "chapter_id",
        "style": "引导式教学",
        "status": "draft"
    }
)

# 8. 建立与章节的关系
add_relation(
    source_id: "chapter_id",
    target_id: lecture_note.id,
    relation_type: "contains",
    metadata: {"type": "lecture_note"}
)

# 9. 老师补充内容时更新文案
update_prompt = f"""原授课文案：\\n{original_lecture}\\n\\n补充内容：\\n{supplement}\\n\\n请将补充内容融入到授课文案中。"""
    '''


if __name__ == "__main__":
    # 测试授课文案生成
    generator = LectureGenerator()

    print("="*60)
    print("        测试授课文案生成")
    print("="*60)

    # 获取现有章节
    chapters = generator.kg.get_all_nodes("chapter")
    if not chapters:
        print("请先运行后台维护系统的测试创建章节数据")
        exit(1)

    chapter_id = chapters[0].id
    chapter_title = chapters[0].metadata.get("title", "未知章节")

    print(f"\n章节: {chapter_title}")

    # 生成授课大纲
    print("\n生成授课大纲...")
    outline_result = generator.generate_lecture_outline(chapter_id)
    if outline_result["success"]:
        outline = outline_result["outline"]
        print(f"\n章节: {outline['chapter']}")
        print(f"\n导入: {outline['introduction']}")
        print(f"\n主要知识点:")
        for i, point in enumerate(outline["main_points"], 1):
            print(f"  {i}. {point['title']}")
            print(f"     {point['content']}")
        print(f"\n总结: {outline['summary']}")
        print(f"答疑: {outline['qa']}")

    # 生成授课文案
    print("\n\n生成授课文案...")
    lecture_result = generator.generate_lecture(chapter_id)

    if lecture_result["success"]:
        print(f"授课风格: {lecture_result['style']}")
        print(f"文案长度: {lecture_result['length']}")
        print(f"知识点数量: {len(lecture_result['concepts'])}")
        print(f"\n知识点摘要:")
        for i, concept in enumerate(lecture_result['concepts'], 1):
            print(f"  {i}. {concept['metadata'].get('title', '未命名')}")
            print(f"     {concept['content'][:50]}...")

        print(f"\n生成提示:")
        print(lecture_result['lecture_data']['prompt'])

    print("\n" + "="*60)
    print("CC中调用示例:")
    print(cc_lecture_generation_example())
