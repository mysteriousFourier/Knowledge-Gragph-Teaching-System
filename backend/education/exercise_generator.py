"""
教育模式 - 练习题生成模块
基于知识图谱生成练习题
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
from edu_config import EduConfig
from kg_constraints import build_constrained_generation_prompt, build_learning_plan
from typing import List, Dict, Optional
import json


class ExerciseGenerator:
    """练习题生成器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = EduConfig.BACKEND_DB_PATH
        self.kg = KnowledgeGraph(db_path)
        self.query = GraphQuery(db_path)
        self.config = EduConfig()

    def generate_exercises(self, chapter_id: str,
                          exercise_types: Optional[List[str]] = None,
                          counts: Optional[Dict[str, int]] = None) -> Dict:
        """
        生成练习题

        Args:
            chapter_id: 章节ID
            exercise_types: 题目类型列表
            counts: 各类型题目数量

        Returns:
            生成的练习题
        """
        exercise_types = exercise_types or self.config.EXERCISE_TYPES
        counts = counts or self.config.DEFAULT_EXERCISE_COUNT

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

        # 生成各类型题目
        exercises = {}

        for ex_type in exercise_types:
            count = counts.get(ex_type, 1)
            if ex_type == "填空题":
                exercises[ex_type] = self._generate_fill_blank_exercises(concepts, count)
            elif ex_type == "选择题":
                exercises[ex_type] = self._generate_choice_exercises(concepts, count)
            elif ex_type == "简答题":
                exercises[ex_type] = self._generate_short_answer_exercises(concepts, count)

        # 统计
        total_count = sum(len(v) for v in exercises.values())

        return {
            "success": True,
            "chapter": chapter.__dict__,
            "concepts_used": len(concepts),
            "exercises": exercises,
            "statistics": {
                "total": total_count,
                "by_type": {k: len(v) for k, v in exercises.items()}
            },
            "timestamp": self._get_timestamp()
        }

    def _generate_fill_blank_exercises(self, concepts: List[Dict], count: int) -> List[Dict]:
        """生成填空题"""
        exercises = []

        for i, concept in enumerate(concepts[:count]):
            content = concept['content']
            title = concept['metadata'].get('title', '概念')

            # 构建知识点上下文
            knowledge = f"知识点：{title}\n{content}"
            learning_plan = self._build_exercise_plan(concept, "填空题")
            prompt = build_constrained_generation_prompt(
                task_title="生成填空题",
                user_input=title,
                source_content=knowledge,
                learning_plan=learning_plan,
                requirements=[
                    "生成1道填空题。",
                    "空格处应该是 LearningPlan.allowed_concepts 中的核心概念。",
                    "提供标准答案，但标准答案必须能在 evidence 中找到依据。",
                    "不要引入图谱外概念作为答案。",
                ],
            )

            exercises.append({
                "id": f"fill_blank_{i+1}",
                "type": "填空题",
                "concept_id": concept['id'],
                "prompt": prompt,
                "knowledge": knowledge,
                "learning_plan": learning_plan,
                "answer": ""  # CC中生成
            })

        return exercises

    def _generate_choice_exercises(self, concepts: List[Dict], count: int) -> List[Dict]:
        """生成选择题"""
        exercises = []

        for i, concept in enumerate(concepts[:count]):
            content = concept['content']
            title = concept['metadata'].get('title', '概念')

            # 构建知识点上下文
            knowledge = f"知识点：{title}\n{content}"
            learning_plan = self._build_exercise_plan(concept, "选择题")
            prompt = build_constrained_generation_prompt(
                task_title="生成选择题",
                user_input=title,
                source_content=knowledge,
                learning_plan=learning_plan,
                requirements=[
                    "生成1道单选题。",
                    "提供4个选项（A、B、C、D）。",
                    "正确答案和解析必须能在 evidence 中找到依据。",
                    "干扰项可以考察误解，但不能捏造新的概念关系。",
                ],
            )

            exercises.append({
                "id": f"choice_{i+1}",
                "type": "选择题",
                "concept_id": concept['id'],
                "prompt": prompt,
                "knowledge": knowledge,
                "learning_plan": learning_plan,
                "options": [],  # CC中生成
                "answer": ""
            })

        return exercises

    def _generate_short_answer_exercises(self, concepts: List[Dict], count: int) -> List[Dict]:
        """生成简答题"""
        exercises = []

        for i, concept in enumerate(concepts[:count]):
            content = concept['content']
            title = concept['metadata'].get('title', '概念')

            # 构建知识点上下文
            knowledge = f"知识点：{title}\n{content}"
            learning_plan = self._build_exercise_plan(concept, "简答题")
            prompt = build_constrained_generation_prompt(
                task_title="生成简答题",
                user_input=title,
                source_content=knowledge,
                learning_plan=learning_plan,
                requirements=[
                    "生成1道简答题。",
                    "题目应考察 evidence 中的核心概念和关系。",
                    "参考答案和评分标准必须只使用 LearningPlan 中允许的知识点。",
                    "如果证据不足，说明需要补充图谱证据。",
                ],
            )

            exercises.append({
                "id": f"short_answer_{i+1}",
                "type": "简答题",
                "concept_id": concept['id'],
                "prompt": prompt,
                "knowledge": knowledge,
                "learning_plan": learning_plan,
                "answer": "",  # CC中生成
                "grading_criteria": ""
            })

        return exercises

    def check_answer(self, exercise_id: str, student_answer: str,
                    chapter_id: str) -> Dict:
        """
        检查学生答案

        Args:
            exercise_id: 题目ID
            student_answer: 学生答案
            chapter_id: 章节ID

        Returns:
            判分结果
        """
        # 获取题目相关的知识点
        # (实际实现需要从数据库中获取已生成的题目)
        # 这里返回提示供CC处理

        learning_plan = build_learning_plan(
            query=f"{exercise_id}\n{student_answer}",
            evidence=[],
            learner_intent="feedback",
            learning_level="beginner",
            task="feedback",
            chapter_data={"id": chapter_id, "title": chapter_id},
        )
        prompt = build_constrained_generation_prompt(
            task_title="批改学生答案",
            user_input=student_answer,
            learning_plan=learning_plan,
            requirements=[
                "如果没有题目证据或图谱证据，明确说明当前图谱依据不足。",
                "不要用常识猜测标准答案。",
                "给出正确性判断、得分、点评和改进建议。",
                "优先给提示，不要无条件泄露完整答案。",
            ],
        )

        return {
            "exercise_id": exercise_id,
            "student_answer": student_answer,
            "evaluation_prompt": prompt,
            "learning_plan": learning_plan,
            "timestamp": self._get_timestamp()
        }

    def generate_answer(self, exercise_id: str, chapter_id: str) -> Dict:
        """
        生成题目答案

        Args:
            exercise_id: 题目ID
            chapter_id: 章节ID

        Returns:
            答案
        """
        # 获取相关知识点
        # (实际实现需要从数据库中获取题目信息)

        learning_plan = build_learning_plan(
            query=exercise_id,
            evidence=[],
            learner_intent="feedback",
            learning_level="beginner",
            task="feedback",
            chapter_data={"id": chapter_id, "title": chapter_id},
        )
        prompt = build_constrained_generation_prompt(
            task_title="生成题目标准答案",
            user_input=exercise_id,
            learning_plan=learning_plan,
            requirements=[
                "仅当 LearningPlan.evidence 中包含题目相关证据时才生成标准答案。",
                "如果当前没有证据，明确说明当前图谱依据不足。",
            ],
        )

        return {
            "exercise_id": exercise_id,
            "answer_prompt": prompt,
            "learning_plan": learning_plan,
            "timestamp": self._get_timestamp()
        }

    def _build_exercise_plan(self, concept: Dict, exercise_type: str) -> Dict:
        title = concept["metadata"].get("title", concept["id"])
        evidence = [
            {
                "id": concept["id"],
                "label": title,
                "type": concept.get("type", "concept"),
                "content": concept.get("content", ""),
                "source": "graph",
            }
        ]
        return build_learning_plan(
            query=title,
            evidence=evidence,
            learner_intent="practice",
            learning_level="beginner",
            task="exercise",
            chapter_data={"id": concept["id"], "title": title, "content": concept.get("content", "")},
        )

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


# CC中调用示例
def cc_exercise_generation_example():
    """
    CC中调用示例：
    通过MCP工具生成练习题
    """
    return '''
# ============================================
# 教育模式 - 练习题生成 - CC中调用示例
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

# 4. 生成填空题
fill_blank_exercises = []
for i, concept in enumerate(concepts[:3]):
    knowledge = f"知识点：{concept['metadata']['title']}\\n{concept['content']}"

    prompt = f"""基于以下知识点生成1道填空题：

{knowledge}

要求：
1. 题目要清晰明确
2. 空格处应该是核心概念
3. 提供标准答案
4. 答案要准确简洁"""

    # CC生成题目
    fill_blank_exercises.append({
        "id": f"fill_blank_{i+1}",
        "type": "填空题",
        "prompt": prompt,
        "knowledge": knowledge
    })

# 5. 生成选择题
choice_exercises = []
for i, concept in enumerate(concepts[:3]):
    knowledge = f"知识点：{concept['metadata']['title']}\\n{concept['content']}"

    prompt = f"""基于以下知识点生成1道选择题（单选题）：

{knowledge}

要求：
1. 题目要清晰明确
2. 提供4个选项（A、B、C、D）
3. 标注正确答案
4. 选项要有迷惑性"""

    # CC生成题目
    choice_exercises.append({
        "id": f"choice_{i+1}",
        "type": "选择题",
        "prompt": prompt,
        "knowledge": knowledge
    })

# 6. 生成简答题
short_answer_exercises = []
for i, concept in enumerate(concepts[:2]):
    knowledge = f"知识点：{concept['metadata']['title']}\\n{concept['content']}"

    prompt = f"""基于以下知识点生成1道简答题：

{knowledge}

要求：
1. 题目要有一定的思考性
2. 答案要点要清晰
3. 提供参考答案和评分标准
4. 答案要全面准确"""

    # CC生成题目
    short_answer_exercises.append({
        "id": f"short_answer_{i+1}",
        "type": "简答题",
        "prompt": prompt,
        "knowledge": knowledge
    })

# 7. 检查学生答案
evaluation_prompt = f"""请评判以下学生答案：

学生答案：{student_answer}

请根据知识点判断答案的正确性，并给出：
1. 正确性判断（正确/部分正确/错误）
2. 得分（0-100分）
3. 详细点评
4. 改进建议"""

# 8. 生成题目答案
answer_prompt = f"""请为题目生成标准答案：

题目ID：{exercise_id}

请根据相关知识点，生成准确、完整的标准答案。"""
    '''


if __name__ == "__main__":
    # 测试练习题生成
    generator = ExerciseGenerator()

    print("="*60)
    print("        测试练习题生成")
    print("="*60)

    # 获取现有章节
    chapters = generator.kg.get_all_nodes("chapter")
    if not chapters:
        print("请先运行后台维护系统的测试创建章节数据")
        exit(1)

    chapter_id = chapters[0].id
    chapter_title = chapters[0].metadata.get("title", "未知章节")

    print(f"\n章节: {chapter_title}")

    # 生成练习题
    print("\n生成练习题...")
    result = generator.generate_exercises(chapter_id)

    if result["success"]:
        print(f"\n使用知识点数量: {result['concepts_used']}")
        print(f"\n题目统计:")
        for ex_type, count in result["statistics"]["by_type"].items():
            print(f"  {ex_type}: {count} 道")

        print(f"\n各类型题目示例:")

        # 填空题
        if "填空题" in result["exercises"]:
            print(f"\n【填空题】")
            for ex in result["exercises"]["填空题"][:1]:
                print(f"  ID: {ex['id']}")
                print(f"  知识点: {ex['knowledge'][:50]}...")
                print(f"  生成提示: {ex['prompt'][:100]}...")

        # 选择题
        if "选择题" in result["exercises"]:
            print(f"\n【选择题】")
            for ex in result["exercises"]["选择题"][:1]:
                print(f"  ID: {ex['id']}")
                print(f"  知识点: {ex['knowledge'][:50]}...")
                print(f"  生成提示: {ex['prompt'][:100]}...")

        # 简答题
        if "简答题" in result["exercises"]:
            print(f"\n【简答题】")
            for ex in result["exercises"]["简答题"][:1]:
                print(f"  ID: {ex['id']}")
                print(f"  知识点: {ex['knowledge'][:50]}...")
                print(f"  生成提示: {ex['prompt'][:100]}...")

    # 测试答案检查
    print("\n\n测试答案检查...")
    check_result = generator.check_answer("choice_1", "A", chapter_id)
    print(f"判分提示: {check_result['evaluation_prompt'][:100]}...")

    print("\n" + "="*60)
    print("CC中调用示例:")
    print(cc_exercise_generation_example())
