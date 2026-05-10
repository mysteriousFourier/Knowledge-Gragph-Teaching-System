"""
测试后台维护系统
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-server"))

from main import BackendMaintenanceSystem
import json


def test_system():
    """测试系统功能"""
    print("="*60)
    print("        测试后台维护系统")
    print("="*60)

    system = BackendMaintenanceSystem()

    # 获取系统状态
    print("\n1. 系统状态:")
    status = system.get_system_status()
    print(f"   节点数: {status['graph_stats']['node_count']}")
    print(f"   关系数: {status['graph_stats']['relation_count']}")
    print(f"   向量模式: {status['vector_stats']['mode']}")

    # 测试导入章节
    print("\n2. 测试导入章节:")
    result = system.importer.import_chapter(
        content="测试章节：线性代数基础\n\n向量是具有大小和方向的量。",
        title="第一章：线性代数基础",
        order=1
    )
    print(f"   导入成功: {result['success']}")
    chapter_id = result['node_id']

    # 测试添加概念
    print("\n3. 测试添加概念:")
    concept = system.update.add_node(
        content="向量空间的定义和性质",
        type="concept",
        metadata={"chapter_id": chapter_id}
    )
    print(f"   概念ID: {concept['id']}")

    # 建立关系
    print("\n4. 测试建立关系:")
    relation = system.update.add_relation(
        source_id=chapter_id,
        target_id=concept['id'],
        relation_type="contains"
    )
    print(f"   关系ID: {relation['id']}")

    # 测试搜索
    print("\n5. 测试搜索:")
    results = system.search.keyword_search("向量")
    print(f"   搜索结果: {len(results)} 个")

    # 测试授课文案
    print("\n6. 测试存储授课文案:")
    lecture = system.lecture.store_lecture_note(
        content="今天我们学习向量空间的基本概念...",
        chapter_id=chapter_id
    )
    print(f"   文案ID: {lecture['note_id']}")

    # 测试老师补充
    print("\n7. 测试老师补充内容解析:")
    supplement = system.supplement.parse_and_update(
        supplement_content="关于向量空间我再补充一点：维数是基中向量的个数。",
        chapter_id=chapter_id
    )
    print(f"   创建笔记: {len(supplement['created_notes'])} 个")
    print(f"   创建节点: {len(supplement['created_nodes'])} 个")

    # 最终状态
    print("\n8. 最终系统状态:")
    final_status = system.get_system_status()
    print(f"   节点数: {final_status['graph_stats']['node_count']}")
    print(f"   关系数: {final_status['graph_stats']['relation_count']}")

    # CC可用工具
    print("\n9. CC可用的MCP工具:")
    tools = system.get_cc_mcp_tools_list()
    for category in tools:
        print(f"\n   {category['category']}:")
        for tool in category['tools']:
            print(f"     - {tool}")

    print("\n" + "="*60)
    print("测试完成！")
    print("="*60)


if __name__ == "__main__":
    test_system()
