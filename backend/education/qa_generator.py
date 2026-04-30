"""
教育模式 - 问答检索与生成模块
基于知识图谱回答用户问题
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
from graph_search import GraphSearch
from edu_config import EduConfig
from kg_constraints import build_constrained_generation_prompt, build_learning_plan
from typing import List, Dict, Optional
import json


class QAGenerator:
    """问答生成器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = EduConfig.BACKEND_DB_PATH
        self.kg = KnowledgeGraph(db_path)
        self.search = GraphSearch(db_path)
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
        # 先进行关键词搜索
        keyword_results = self.search.keyword_search(question, limit=top_k)

        # 再进行语义搜索（如果可用）
        semantic_results = self.search.semantic_search(question, top_k=top_k)

        # 合并结果，语义搜索结果优先
        seen_ids = set()
        combined_results = []

        for result in semantic_results:
            node_id = result['node_id']
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                combined_results.append({
                    "node_id": node_id,
                    "content": result['metadata']['content'],
                    "type": result['metadata']['type'],
                    "similarity": result['similarity'],
                    "match_type": "semantic"
                })

        for result in keyword_results:
            if result['id'] not in seen_ids and len(combined_results) < top_k:
                seen_ids.add(result['id'])
                combined_results.append({
                    "node_id": result['id'],
                    "content": result['content'],
                    "type": result['type'],
                    "similarity": 0.0,
                    "match_type": "keyword"
                })

        return combined_results

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
                "只使用 LearningPlan.evidence 中的知识。",
                "如果知识不足，请明确说明当前图谱依据不足。",
                "必要时引用依据编号。",
            ],
        )

        # 返回提示和知识，供CC处理
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

        # 提取关键信息
        key_points = []
        for item in knowledge[:5]:
            # 取前100个字符作为摘要
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
        # 1. 检索知识
        knowledge = self.retrieve_knowledge(question)

        # 2. 生成答案
        answer_data = self.generate_answer(question, knowledge)

        # 3. 返回结果
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
        # 检索相关知识点
        knowledge = self.retrieve_knowledge(question, top_k=limit)

        # 基于知识点生成相关问题
        related_questions = []

        question_templates = [
            "什么是{}？",
            "{}有什么特点？",
            "如何理解{}？",
            "{}和{}有什么区别？",
            "请举例说明{}"
        ]

        for item in knowledge[:3]:
            # 提取关键词（简化版）
            keywords = self._extract_keywords(item['content'])

            for keyword in keywords[:2]:
                # 生成相关问题
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
        # 简化版：提取较长的词
        words = text.replace('，', ' ').replace('。', ' ').split()
        # 过滤掉太短的词
        keywords = [w for w in words if len(w) > 2]
        return keywords[:5]

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


# CC中调用示例
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


if __name__ == "__main__":
    # 测试问答生成
    qa = QAGenerator()

    print("="*60)
    print("        测试问答生成")
    print("="*60)

    # 测试问题
    test_question = "什么是向量空间？"

    print(f"\n问题: {test_question}")

    # 检索知识
    print("\n正在检索相关知识...")
    knowledge = qa.retrieve_knowledge(test_question)
    print(f"找到 {len(knowledge)} 个相关知识")

    for i, item in enumerate(knowledge, 1):
        print(f"\n  知识点 {i}:")
        print(f"    内容: {item['content'][:60]}...")
        print(f"    类型: {item['type']}")
        print(f"    相似度: {item['similarity']:.3f}")

    # 生成答案
    print("\n正在生成答案...")
    answer_data = qa.generate_answer(test_question, knowledge)
    print(f"\n知识摘要:\n{answer_data['knowledge_summary']}")

    print(f"\n生成提示:\n{answer_data['prompt']}")

    # 获取相关问题
    print("\n获取相关问题...")
    related = qa.get_related_questions(test_question)
    print("相关问题:")
    for i, q in enumerate(related, 1):
        print(f"  {i}. {q}")

    print("\n" + "="*60)
    print("CC中调用示例:")
    print(cc_qa_example())
