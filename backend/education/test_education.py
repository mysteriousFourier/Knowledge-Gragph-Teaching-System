"""
测试教育模式
"""
import sys
import os

# 设置路径 - 注意顺序很重要
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)  # 当前目录必须最前
sys.path.insert(1, os.path.join(current_dir, "..", "mcp-server"))
sys.path.insert(2, os.path.join(current_dir, "..", "maintenance"))

# 清除可能的缓存
for key in list(sys.modules.keys()):
    if any(x in key for x in ['qa_generator', 'lecture_generator', 'exercise_generator', 'knowledge_path', 'data_organizer', 'main', 'config']):
        del sys.modules[key]

# 直接导入
from main import EducationMode
import json


def test_education_mode():
    """测试教育模式功能"""
    print("="*60)
    print("        测试教育模式")
    print("="*60)

    system = EducationMode()

    # 获取系统状态
    print("\n1. 系统状态:")
    status = system.get_system_status()
    print(f"   节点数: {status['graph_stats']['node_count']}")
    print(f"   关系数: {status['graph_stats']['relation_count']}")
    print(f"   向量模式: {status['vector_stats']['mode']}")

    # 获取现有章节
    chapters = system.kg.get_all_nodes("chapter")
    if not chapters:
        print("\n请先运行后台维护系统的测试创建数据")
        return

    chapter_id = chapters[0].id
    chapter_title = chapters[0].metadata.get("title", "未知章节")

    # 测试问答功能
    print("\n2. 测试问答功能:")
    question = "什么是向量空间？"
    print(f"   问题: {question}")
    qa_result = system.answer_question(question)
    print(f"   找到相关知识: {qa_result['knowledge_count']} 个")
    print(f"   知识摘要:\n{qa_result['answer_data']['knowledge_summary']}")

    # 获取相关问题
    print("\n3. 获取相关问题:")
    related = system.get_related_questions(question)
    print(f"   相关问题:")
    for i, q in enumerate(related, 1):
        print(f"     {i}. {q}")

    # 测试授课文案生成
    print("\n4. 测试授课文案生成:")
    print(f"   章节: {chapter_title}")
    lecture_result = system.generate_lecture(chapter_id)
    if lecture_result["success"]:
        print(f"   授课风格: {lecture_result['style']}")
        print(f"   知识点数量: {len(lecture_result['concepts'])}")
        print(f"   生成提示（前200字符）:")
        print(f"   {lecture_result['lecture_data']['prompt'][:200]}...")

    # 测试授课大纲
    print("\n5. 测试授课大纲:")
    outline_result = system.generate_lecture_outline(chapter_id)
    if outline_result["success"]:
        outline = outline_result["outline"]
        print(f"   章节: {outline['chapter']}")
        print(f"   主要知识点: {len(outline['main_points'])} 个")
        for point in outline["main_points"]:
            print(f"     - {point['title']}")

    # 测试练习题生成
    print("\n6. 测试练习题生成:")
    exercise_result = system.generate_exercises(chapter_id)
    if exercise_result["success"]:
        print(f"   题目统计:")
        for ex_type, count in exercise_result["statistics"]["by_type"].items():
            print(f"     {ex_type}: {count} 道")

    # 测试知识路径追踪
    print("\n7. 测试知识路径追踪:")
    path_result = system.trace_learning_path(chapter_id, max_depth=2)
    print(f"   找到路径: {path_result['total_paths']} 条")
    for path in path_result['path_summaries'][:2]:
        print(f"     {' -> '.join(path['node_titles'])}")

    # 测试数据组织
    print("\n8. 测试数据组织:")
    graph_data = system.get_graph_for_visualization()
    print(f"   节点数: {len(graph_data['nodes'])}")
    print(f"   边数: {len(graph_data['edges'])}")

    # 测试章节数据组织
    chapter_detail = system.get_chapter_detail(chapter_id)
    if chapter_detail["success"]:
        print(f"   章节详情:")
        print(f"     概念: {chapter_detail['stats']['concepts']} 个")
        print(f"     笔记: {chapter_detail['stats']['notes']} 个")
        print(f"     授课文案: {chapter_detail['stats']['lectures']} 个")

    # 测试学生功能
    print("\n9. 测试学生功能 - 查看授课文案:")
    student_view = system.student_view_lecture(chapter_id)
    if student_view["success"]:
        print(f"   章节标题: {student_view['chapter_title']}")
        if student_view["lecture_content"]:
            print(f"   授课文案ID: {student_view['lecture_content']['id']}")
        else:
            print(f"   暂无授课文案")

    print("\n10. 测试学生功能 - 做练习题:")
    student_exercises = system.student_do_exercises(chapter_id)
    if student_exercises["success"]:
        print(f"    生成题目: {student_exercises['statistics']['total']} 道")

    # 测试老师功能
    print("\n11. 测试老师功能 - 查看知识图谱:")
    teacher_graph = system.teacher_view_knowledge_graph()
    print(f"    节点数: {teacher_graph['stats']['node_count']}")
    print(f"    关系数: {teacher_graph['stats']['relation_count']}")

    # CC集成指南
    print("\n12. CC集成指南:")
    guide = system.get_cc_integration_guide()
    print(f"    学生工作流:")
    for step in guide['workflow']['student']:
        print(f"      - {step}")

    print("\n" + "="*60)
    print("教育模式测试完成！")
    print("="*60)


if __name__ == "__main__":
    test_education_mode()
