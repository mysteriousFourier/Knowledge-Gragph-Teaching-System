"""
后台维护系统 - 主入口
整合所有后台维护功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from graph_manager import KnowledgeGraph
from import_chapter import ChapterImporter
from graph_query import GraphQuery
from graph_search import GraphSearch
from graph_update import GraphUpdate
from teacher_supplement import TeacherSupplementParser
from lecture_note_manager import LectureNoteManager
from typing import Dict, List
import json


class BackendMaintenanceSystem:
    """后台维护系统 - 整合所有功能"""

    def __init__(self, db_path: str = None):
        self.kg = KnowledgeGraph(db_path)

        # 初始化各个模块
        self.importer = ChapterImporter(db_path)
        self.query = GraphQuery(db_path)
        self.search = GraphSearch(db_path)
        self.update = GraphUpdate(db_path)
        self.supplement = TeacherSupplementParser(db_path)
        self.lecture = LectureNoteManager(db_path)

    def get_system_status(self) -> Dict:
        """获取系统状态"""
        graph_stats = self.kg.get_graph_structure()

        return {
            "status": "running",
            "graph_stats": graph_stats["stats"],
            "vector_stats": graph_stats["vector_stats"],
            "modules": {
                "import": "ready",
                "query": "ready",
                "search": "ready",
                "update": "ready",
                "supplement": "ready",
                "lecture": "ready"
            }
        }

    def get_cc_mcp_tools_list(self) -> List[Dict]:
        """获取CC可用的MCP工具列表"""
        return [
            {
                "category": "图谱查询",
                "tools": [
                    "read_graph",
                    "get_node",
                    "get_relations",
                    "get_graph_schema"
                ]
            },
            {
                "category": "搜索",
                "tools": [
                    "search_nodes",
                    "semantic_search"
                ]
            },
            {
                "category": "图谱更新",
                "tools": [
                    "add_memory",
                    "update_memory",
                    "delete_memory",
                    "add_relation"
                ]
            },
            {
                "category": "高级功能",
                "tools": [
                    "get_neighbors",
                    "trace_call_path",
                    "discover_weak_relations"
                ]
            },
            {
                "category": "教育专用",
                "tools": [
                    "get_note"
                ]
            }
        ]


def print_system_menu():
    """打印系统菜单"""
    print("\n" + "="*60)
    print("        后台维护系统 - 主菜单")
    print("="*60)
    print("1. 查看系统状态")
    print("2. 导入章节")
    print("3. 图谱查询")
    print("4. 图谱搜索")
    print("5. 图谱更新")
    print("6. 老师补充内容解析")
    print("7. 授课文案管理")
    print("8. 获取CC可用的MCP工具列表")
    print("9. 运行所有模块测试")
    print("0. 退出")
    print("="*60)


def interactive_demo():
    """交互式演示"""
    system = BackendMaintenanceSystem()

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

        elif choice == "8":
            tools = system.get_cc_mcp_tools_list()
            print("\nCC可用的MCP工具:")
            for category in tools:
                print(f"\n{category['category']}:")
                for tool in category['tools']:
                    print(f"  - {tool}")

        elif choice == "9":
            print("\n运行所有模块测试...")
            print("请分别运行以下测试脚本:")
            print("  1. python import_chapter.py")
            print("  2. python graph_query.py")
            print("  3. python graph_search.py")
            print("  4. python graph_update.py")
            print("  5. python teacher_supplement.py")
            print("  6. python lecture_note_manager.py")

        else:
            print(f"\n功能 {choice} 的交互界面未实现，请运行对应的测试脚本")


# CC中调用示例
def cc_integration_example():
    """
    CC中完整调用示例：
    展示如何在CC中使用后台维护系统的所有功能
    """
    return '''
# ============================================
# 后台维护系统 - CC中完整调用示例
# ============================================

# 1. 导入章节
# -------------------
chapter_node = add_memory(
  content: "第三章：向量空间的主要内容...",
  type: "chapter",
  metadata: {
    "title": "第三章：向量空间",
    "order": 3,
    "parent_id": "root_chapter_id"
  }
)

# 2. 查询图谱
# -------------------
# 获取完整图谱结构
graph = read_graph()

# 获取节点详情
node = get_node(node_id=chapter_node.id)

# 获取图谱统计
schema = get_graph_schema()

# 获取邻居
neighbors = get_neighbors(node_id=chapter_node.id, direction="out")

# 3. 搜索
# -------------------
# 关键词搜索
results = search_nodes(keyword: "向量", node_type: "concept", limit: 10)

# 语义搜索
semantic_results = semantic_search(query: "什么是向量空间", top_k: 5)

# 4. 更新图谱
# -------------------
# 添加概念节点
concept = add_memory(
  content: "向量是具有大小和方向的量...",
  type: "concept",
  metadata: {"chapter_id": chapter_node.id}
)

# 添加关系
relation = add_relation(
  source_id:chapter_node.id,
  target_id:concept.id,
  relation_type:"contains"
)

# 更新节点
update_memory(node_id:concept.id, content:"更新后的内容...")

# 5. 老师补充内容
# -------------------
# 存储补充笔记
supplement = add_memory(
  content: "关于向量空间我再补充一点...",
  type: "note",
  metadata: {
    "source": "teacher_supplement",
    "teacher_id": "teacher_001",
    "chapter_id": chapter_node.id
  }
)

# 建立关系
add_relation(source_id:chapter_node.id, target_id:supplement.id, relation_type:"contains")

# 6. 授课文案管理
# -------------------
# 存储AI生成的授课文案
lecture = add_memory(
  content: "今天我们学习向量空间...",
  type: "observation",
  metadata: {
    "source": "ai_lecture",
    "teacher_id": "teacher_001",
    "chapter_id": chapter_node.id,
    "status": "draft"
  }
)

# 建立关系
add_relation(source_id:chapter_node.id, target_id:lecture.id, relation_type:"contains")

# 老师修改授课文案
update_memory(
  node_id:lecture.id,
  content:"修改后的授课文案...",
  metadata:{"status": "approved"}
)

# 学生查询授课文案
notes = get_note(node_id:lecture.id)

# 7. 高级功能
# -------------------
# 追踪知识路径
paths = trace_call_path(start_node_id:chapter_node.id, max_depth=3)

# 发现弱关系
weak_relations = discover_weak_relations(node_id:concept.id, threshold:0.4)

# 获取关系
relations = get_relations(node_id:chapter_node.id)
    '''


if __name__ == "__main__":
    print("\n" + "="*60)
    print("        后台维护系统")
    print("="*60)

    # 显示系统状态
    system = BackendMaintenanceSystem()
    status = system.get_system_status()
    print("\n系统状态:")
    print(f"  节点数: {status['graph_stats']['node_count']}")
    print(f"  关系数: {status['graph_stats']['relation_count']}")
    print(f"  向量模式: {status['vector_stats']['mode']}")
    print("\n各模块状态:", ", ".join([f"{k}: {v}" for k, v in status['modules'].items()]))

    # 显示CC可用的MCP工具
    print("\n" + "-"*60)
    print("CC可用的MCP工具:")
    tools = system.get_cc_mcp_tools_list()
    for category in tools:
        print(f"\n{category['category']}:")
        for tool in category['tools']:
            print(f"  - {tool}")

    # 运行交互式演示
    print("\n" + "-"*60)
    input("按Enter进入交互式演示...")
    interactive_demo()

    # 显示CC集成示例
    print("\n" + "="*60)
    print("CC中完整调用示例:")
    print("="*60)
    print(cc_integration_example())
