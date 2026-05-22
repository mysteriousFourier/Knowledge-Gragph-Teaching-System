"""
教育模式 - 问答检索与生成模块
基于知识图谱回答用户问题
"""

from KGTS.config import EduConfig
from KGTS.education.kg_constraints import build_constrained_generation_prompt, build_learning_plan
from typing import List, Dict, Optional
import json


class QAGenerator:
    """问答生成器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = EduConfig.BACKEND_DB_PATH
        self.config = EduConfig()

    def retrieve_knowledge(self, question: str, top_k: int = 5) -> List[Dict]:
        """
        检索相关知识

        Args:
            question: 用户问题
            top_k: 返回结果数量

        Returns:
            相关知识节点列表
        """
        return []

    def generate_answer(self, question: str, knowledge: List[Dict]) -> Dict:
        """
        基于知识生成答案

        Args:
            question: 用户问题
            knowledge: 检索到的相关知识

        Returns:
            生成的答案
        """
        if not knowledge:
            return {
                "prompt": "",
                "knowledge": [],
                "knowledge_summary": "很抱歉，我在知识库中没有找到相关信息。您可以尝试重新提问或联系老师。"
            }

        evidence = [
            {
                "id": item.get("node_id"),
                "label": item.get("node_id"),
                "type": item.get("type", "concept"),
                "content": item.get("content", ""),
                "source": item.get("match_type", "graph"),
            }
            for item in knowledge[:5]
        ]
        learning_plan = build_learning_plan(
            query=question,
            evidence=evidence,
            learner_intent=None,
            learning_level="beginner",
            task="qa",
        )
        prompt = build_constrained_generation_prompt(
            task_title="回答学生问题",
            user_input=question,
            learning_plan=learning_plan,
            requirements=[
                "用简洁清晰的语言回答问题。",
                "优先使用 LearningPlan.evidence 中的知识；证据只覆盖部分问题时，给出有边界的回答，不要直接拒答。",
                "不要编造具体事实、引用、公式或关系；关键事实缺失时说明需要补充证据。",
                "英文原文、术语、公式和变量名保持英文；如果翻译可能造成歧义，直接用英文回答。",
                "必要时引用依据编号。",
            ],
        )

        return {
            "prompt": prompt,
            "knowledge": knowledge,
            "learning_plan": learning_plan,
            "knowledge_summary": self._summarize_knowledge(knowledge)
        }

    def _summarize_knowledge(self, knowledge: List[Dict]) -> str:
        """总结检索到的知识"""
        if not knowledge:
            return "无相关知识"

        key_points = []
        for item in knowledge[:5]:
            summary = item['content'][:100].replace('\n', ' ')
            key_points.append(f"- {summary}...")

        return "\n".join(key_points)

    def answer_question(self, question: str) -> Dict:
        """
        完整的问答流程

        Args:
            question: 用户问题

        Returns:
            问答结果
        """
        knowledge = self.retrieve_knowledge(question)
        answer_data = self.generate_answer(question, knowledge)

        return {
            "question": question,
            "knowledge_count": len(knowledge),
            "knowledge": knowledge,
            "answer_data": answer_data,
            "timestamp": self._get_timestamp()
        }

    def get_related_questions(self, question: str, limit: int = 5) -> List[str]:
        """
        获取相关问题推荐

        Args:
            question: 当前问题
            limit: 返回数量

        Returns:
            相关问题列表
        """
        knowledge = self.retrieve_knowledge(question, top_k=limit)

        related_questions = []

        question_templates = [
            "什么是{}？",
            "{}有什么特点？",
            "如何理解{}？",
            "{}和{}有什么区别？",
            "请举例说明{}"
        ]

        for item in knowledge[:3]:
            keywords = self._extract_keywords(item['content'])

            for keyword in keywords[:2]:
                for template in question_templates[:2]:
                    if "{}" in template:
                        q = template.format(keyword)
                        if q != question and q not in related_questions:
                            related_questions.append(q)
                            if len(related_questions) >= limit:
                                break
            if len(related_questions) >= limit:
                break

        return related_questions[:limit]

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（简化版）"""
        words = text.replace('，', ' ').replace('。', ' ').split()
        keywords = [w for w in words if len(w) > 2]
        return keywords[:5]

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


def cc_qa_example():
    """
    CC中调用示例：
    通过MCP工具检索知识并生成答案
    """
    return '''
# ============================================
# 教育模式 - 问答生成 - CC中调用示例
# ============================================

# 1. 检索相关知识
# 先用关键词搜索
keyword_results = search_nodes(keyword: "向量空间", limit: 5)

# 再用语义搜索
semantic_results = semantic_search(query: "什么是向量空间", top_k: 5)

# 2. 合并结果
knowledge = []
seen_ids = set()

# 语义搜索结果优先
for result in semantic_results:
    if result['node_id'] not in seen_ids:
        seen_ids.add(result['node_id'])
        knowledge.append({
            "node_id": result['node_id'],
            "content": result['metadata']['content'],
            "type": result['metadata']['type'],
            "similarity": result['similarity']
        })

# 添加关键词搜索结果
for result in keyword_results:
    if result['id'] not in seen_ids:
        seen_ids.add(result['id'])
        knowledge.append({
            "node_id": result['id'],
            "content": result['content'],
            "type": result['type'],
            "similarity": 0.0
        })

# 3. 构建知识上下文
knowledge_context = "\\n\\n".join([
    f"知识点{i+1}: {item['content']}"
    for i, item in enumerate(knowledge[:3])
])

# 4. 生成答案（CC中用Claude生成）
answer_prompt = f"""基于以下知识回答问题：

知识：
{knowledge_context}

问题：{question}

请根据上述知识，用简洁清晰的语言回答问题。"""

# 5. Claude生成答案
# (CC会自动处理这个prompt)

# 6. 追踪知识路径（可选）
paths = trace_call_path(start_node_id=knowledge[0]['node_id'], max_depth=3)

# 7. 获取相关知识点（通过邻居）
neighbors = get_neighbors(node_id=knowledge[0]['node_id'], direction="both")

# 8. 发现弱关系
weak_relations = discover_weak_relations(node_id=knowledge[0]['node_id'])
    '''
