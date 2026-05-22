"""
教育模式 - 主入口
整合所有教育模式功能
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
from qa_generator import QAGenerator
from lecture_generator import LectureGenerator
from exercise_generator import ExerciseGenerator
from knowledge_path import KnowledgePathTracker
from data_organizer import DataOrganizer
from typing import Dict, List, Optional
import json


class EducationMode:
    """教育模式 - 整合所有功能"""

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

        # 初始化各个模块
        self.qa = QAGenerator(db_path)
        self.lecture = LectureGenerator(db_path)
        self.exercise = ExerciseGenerator(db_path)
        self.path_tracker = KnowledgePathTracker(db_path)
        self.organizer = DataOrganizer(db_path)

    def get_system_status(self) -> Dict:
        """获取系统状态"""
        graph_stats = self.kg.get_graph_structure()

        return {
            "status": "running",
            "graph_stats": graph_stats["stats"],
            "vector_stats": graph_stats["vector_stats"],
            "modules": {
                "qa": "ready",
                "lecture": "ready",
                "exercise": "ready",
                "path_tracker": "ready",
                "data_organizer": "ready"
            }
        }

    # ==================== 问答功能 ====================

    def answer_question(self, question: str) -> Dict:
        """回答学生问题"""
        return self.qa.answer_question(question)

    def get_related_questions(self, question: str) -> List[str]:
        """获取相关问题"""
        return self.qa.get_related_questions(question)

    # ==================== 授课文案功能 ====================

    def generate_lecture(self, chapter_id: str, style: str = "引导式教学",
                         length: str = "中等") -> Dict:
        """生成授课文案"""
        return self.lecture.generate_lecture(chapter_id, style, length)

    def generate_lecture_outline(self, chapter_id: str) -> Dict:
        """生成授课大纲"""
        return self.lecture.generate_lecture_outline(chapter_id)

    def update_lecture_with_supplement(self, lecture_content: str,
                                       supplement_content: str) -> Dict:
        """用补充内容更新授课文案"""
        return self.lecture.update_lecture_with_supplement(lecture_content, supplement_content)

    # ==================== 练习题功能 ====================

    def generate_exercises(self, chapter_id: str,
                          exercise_types: Optional[List[str]] = None,
                          counts: Optional[Dict[str, int]] = None) -> Dict:
        """生成练习题"""
        return self.exercise.generate_exercises(chapter_id, exercise_types, counts)

    def check_exercise_answer(self, exercise_id: str, student_answer: str,
                             chapter_id: str) -> Dict:
        """检查练习题答案"""
        return self.exercise.check_answer(exercise_id, student_answer, chapter_id)

    def generate_exercise_answer(self, exercise_id: str, chapter_id: str) -> Dict:
        """生成练习题答案"""
        return self.exercise.generate_answer(exercise_id, chapter_id)

    # ==================== 知识路径功能 ====================

    def trace_learning_path(self, start_node_id: str, end_node_id: Optional[str] = None,
                           max_depth: int = 5) -> Dict:
        """追踪学习路径"""
        return self.path_tracker.trace_learning_path(start_node_id, end_node_id, max_depth)

    def get_prerequisite_knowledge(self, node_id: str) -> Dict:
        """获取前置知识点"""
        return self.path_tracker.get_prerequisite_knowledge(node_id)

    def get_follow_up_knowledge(self, node_id: str) -> Dict:
        """获取后续知识点"""
        return self.path_tracker.get_follow_up_knowledge(node_id)

    def build_knowledge_tree(self, root_node_id: str, max_depth: int = 3) -> Dict:
        """构建知识树"""
        return self.path_tracker.build_knowledge_tree(root_node_id, max_depth)

    def suggest_learning_sequence(self, chapter_id: str) -> Dict:
        """建议学习顺序"""
        return self.path_tracker.suggest_learning_sequence(chapter_id)

    # ==================== 数据组织功能 ====================

    def organize_for_frontend(self, data_type: str, **kwargs) -> Dict:
        """为前端组织数据"""
        return self.organizer.organize_for_frontend(data_type, **kwargs)

    def get_graph_for_visualization(self) -> Dict:
        """获取图谱数据用于可视化"""
        return self.organizer._organize_graph_data()

    def get_chapter_detail(self, chapter_id: str) -> Dict:
        """获取章节详情"""
        return self.organizer._organize_chapter_data(chapter_id)

    # ==================== 学生功能 ====================

    def student_view_lecture(self, chapter_id: str) -> Dict:
        """学生查看授课文案"""
        lecture_data = self.organizer._organize_lecture_data(chapter_id)

        if not lecture_data["success"]:
            return lecture_data

        return {
            "success": True,
            "chapter_title": lecture_data["chapter"]["metadata"]["title"],
            "lecture_content": lecture_data["latest_lecture"],
            "concepts": lecture_data["concepts"]
        }

    def student_do_exercises(self, chapter_id: str) -> Dict:
        """学生做练习题"""
        return self.exercise.generate_exercises(chapter_id)

    def student_ask_question(self, question: str) -> Dict:
        """学生提问"""
        return self.qa.answer_question(question)

    # ==================== 老师功能 ====================

    def teacher_generate_lecture(self, chapter_id: str, style: str = "引导式教学") -> Dict:
        """老师生成授课文案"""
        return self.lecture.generate_lecture(chapter_id, style)

    def teacher_add_supplement(self, chapter_id: str, supplement_content: str) -> Dict:
        """老师添加补充内容"""
        # 这里需要调用后台维护系统的老师补充功能
        # 返回提示供CC处理
        return {
            "success": True,
            "prompt": f"请将以下补充内容融入到授课文案中：\n{supplement_content}",
            "chapter_id": chapter_id
        }

    def teacher_view_knowledge_graph(self) -> Dict:
        """老师查看知识图谱"""
        return self.organizer._organize_graph_data()

    def get_cc_integration_guide(self) -> Dict:
        """获取CC集成指南"""
        return {
            "mcp_tools": {
                "query": ["read_graph", "get_node", "get_relations", "get_graph_schema"],
                "search": ["search_nodes", "semantic_search"],
                "update": ["add_memory", "update_memory", "delete_memory", "add_relation"],
                "advanced": ["get_neighbors", "trace_call_path", "discover_weak_relations"],
                "education": ["get_note"]
            },
            "workflow": {
                "student": [
                    "查看授课文案 -> get_note",
                    "做练习题 -> generate_exercises",
                    "提问 -> answer_question"
                ],
                "teacher": [
                    "生成授课文案 -> generate_lecture",
                    "添加补充 -> teacher_add_supplement",
                    "查看图谱 -> get_graph_for_visualization"
                ]
            }
        }


def print_system_menu():
    """打印系统菜单"""
    print("\n" + "="*60)
    print("        教育模式 - 主菜单")
    print("="*60)
    print("1. 查看系统状态")
    print("2. 问答功能")
    print("3. 授课文案生成")
    print("4. 练习题生成")
    print("5. 知识路径追踪")
    print("6. 数据组织与展示")
    print("7. 学生功能")
    print("8. 老师功能")
    print("9. 获取CC集成指南")
    print("0. 退出")
    print("="*60)


def interactive_demo():
    """交互式演示"""
    system = EducationMode()

    while True:
        print_system_menu()
        choice = input("\n请选择功能 (0-9): ").strip()

        if choice == "0":
            print("再见！")
            break

        elif choice == "1":
            status = system.get_system_status()
            print("\n系统状态:")
            print(json.dumps(status, ensure_ascii=False, indent=2))

        elif choice == "9":
            guide = system.get_cc_integration_guide()
            print("\nCC集成指南:")
            print(json.dumps(guide, ensure_ascii=False, indent=2))

        elif choice == "2":
            question = input("\n请输入问题: ").strip()
            if question:
                result = system.answer_question(question)
                print(f"\n回答:\n{result['answer_data']['knowledge_summary']}")

        else:
            print(f"\n功能 {choice} 的交互界面未实现，请运行对应的测试脚本")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("        教育模式")
    print("="*60)

    # 显示系统状态
    system = EducationMode()
    status = system.get_system_status()
    print("\n系统状态:")
    print(f"  节点数: {status['graph_stats']['node_count']}")
    print(f"  关系数: {status['graph_stats']['relation_count']}")
    print(f"  向量模式: {status['vector_stats']['mode']}")

    # 显示CC集成指南
    print("\n" + "-"*60)
    print("CC集成指南:")
    guide = system.get_cc_integration_guide()
    print(f"\nMCP工具分类:")
    for category, tools in guide['mcp_tools'].items():
        print(f"  {category}: {', '.join(tools)}")

    print(f"\n学生工作流:")
    for step in guide['workflow']['student']:
        print(f"  - {step}")

    print(f"\n老师工作流:")
    for step in guide['workflow']['teacher']:
        print(f"  - {step}")

    # 运行交互式演示
    print("\n" + "-"*60)
    input("按Enter进入交互式演示...")
    interactive_demo()
