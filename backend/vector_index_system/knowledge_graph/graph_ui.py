#!/usr/bin/env python3
"""
知识图谱管理系统交互式界面

功能：
- 知识图谱审查机制
- 人工可编辑的知识图谱提取功能
- 知识图谱可视化界面
- 知识节点和关系管理
"""

import os
import sys
import json
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge_graph.graph_manager import KnowledgeGraphManager

class KnowledgeGraphUI:
    """知识图谱管理系统交互式界面"""
    
    def __init__(self, data_dir: str, storage_path: str = "./knowledge_graph"):
        """
        初始化知识图谱UI
        
        Args:
            data_dir: 结构化数据目录
            storage_path: 知识图谱存储路径
        """
        self.data_dir = data_dir
        self.storage_path = storage_path
        self.manager = KnowledgeGraphManager(data_dir, storage_path)
        self.reviewer = "admin"  # 默认审查员
        
        print("知识图谱管理系统交互式界面")
        print(f"数据目录: {data_dir}")
        print(f"存储路径: {storage_path}")
    
    def show_main_menu(self):
        """显示主菜单"""
        print("\n" + "="*60)
        print("知识图谱管理系统")
        print("="*60)
        print("1. 从结构化数据提取知识图谱")
        print("2. 管理知识节点")
        print("3. 管理关系")
        print("4. 审查知识图谱")
        print("5. 导出/导入知识图谱")
        print("6. 查看统计信息")
        print("7. 退出系统")
        print("="*60)
    
    def run(self):
        """运行主循环"""
        while True:
            self.show_main_menu()
            
            try:
                choice = input("请输入选项编号: ")
                
                if choice == "1":
                    self.extract_knowledge_graph()
                elif choice == "2":
                    self.manage_nodes()
                elif choice == "3":
                    self.manage_relationships()
                elif choice == "4":
                    self.review_knowledge_graph()
                elif choice == "5":
                    self.export_import_graph()
                elif choice == "6":
                    self.view_statistics()
                elif choice == "7":
                    print("退出系统...")
                    break
                else:
                    print("无效选项，请重新输入")
                    
            except KeyboardInterrupt:
                print("\n操作被用户中断")
                break
            except Exception as e:
                print(f"操作失败: {str(e)}")
                import traceback
                traceback.print_exc()
    
    def extract_knowledge_graph(self):
        """从结构化数据提取知识图谱"""
        print("\n从结构化数据提取知识图谱")
        print("="*50)
        
        start_time = time.time()
        success = self.manager.extract_from_structured_data()
        end_time = time.time()
        
        if success:
            print(f"\n提取完成，用时 {end_time - start_time:.2f} 秒")
        else:
            print("\n提取失败")
        
        input("按Enter键返回主菜单...")
    
    def manage_nodes(self):
        """管理知识节点"""
        while True:
            print("\n管理知识节点")
            print("="*50)
            print("1. 查看节点列表")
            print("2. 查看节点详情")
            print("3. 添加节点")
            print("4. 更新节点")
            print("5. 删除节点")
            print("6. 返回主菜单")
            print("="*50)
            
            choice = input("请输入选项编号: ")
            
            if choice == "1":
                self.view_nodes()
            elif choice == "2":
                self.view_node_detail()
            elif choice == "3":
                self.add_node()
            elif choice == "4":
                self.update_node()
            elif choice == "5":
                self.delete_node()
            elif choice == "6":
                break
            else:
                print("无效选项，请重新输入")
    
    def view_nodes(self):
        """查看节点列表"""
        node_type = input("请输入节点类型 (留空查看所有类型): ")
        limit = input("请输入显示数量 (默认100): ")
        limit = int(limit) if limit else 100
        
        nodes = self.manager.get_nodes(type=node_type if node_type else None, limit=limit)
        
        print(f"\n节点列表 (共 {len(nodes)} 个):")
        print("="*80)
        print(f"{'ID':<20} {'标签':<30} {'类型':<15} {'审查状态':<10}")
        print("="*80)
        
        for node in nodes:
            reviewed = "已审查" if node['reviewed'] else "未审查"
            print(f"{node['id']:<20} {node['label'][:28]:<30} {node['type']:<15} {reviewed:<10}")
        
        input("按Enter键返回...")
    
    def view_node_detail(self):
        """查看节点详情"""
        node_id = input("请输入节点ID: ")
        if not node_id:
            print("节点ID不能为空")
            input("按Enter键返回...")
            return
        
        node = self.manager.get_node(node_id)
        if node:
            print("\n节点详情:")
            print("="*50)
            print(f"ID: {node['id']}")
            print(f"标签: {node['label']}")
            print(f"类型: {node['type']}")
            print(f"内容: {node['content'][:200]}...")
            print(f"来源: {node['source']}")
            print(f"置信度: {node['confidence']}")
            print(f"创建时间: {time.ctime(node['created_at'])}")
            print(f"更新时间: {time.ctime(node['updated_at'])}")
            print(f"审查状态: {'已审查' if node['reviewed'] else '未审查'}")
        else:
            print("节点不存在")
        
        input("按Enter键返回...")
    
    def add_node(self):
        """添加节点"""
        label = input("请输入节点标签: ")
        if not label:
            print("标签不能为空")
            input("按Enter键返回...")
            return
        
        node_type = input("请输入节点类型: ")
        content = input("请输入节点内容: ")
        source = input("请输入来源 (默认manual): ") or "manual"
        
        node_id = self.manager.add_node(label, node_type, content, source)
        print(f"\n节点添加成功，ID: {node_id}")
        input("按Enter键返回...")
    
    def update_node(self):
        """更新节点"""
        node_id = input("请输入节点ID: ")
        if not node_id:
            print("节点ID不能为空")
            input("按Enter键返回...")
            return
        
        node = self.manager.get_node(node_id)
        if not node:
            print("节点不存在")
            input("按Enter键返回...")
            return
        
        updates = {}
        
        new_label = input(f"请输入新标签 (当前: {node['label']}): ")
        if new_label:
            updates['label'] = new_label
        
        new_type = input(f"请输入新类型 (当前: {node['type']}): ")
        if new_type:
            updates['type'] = new_type
        
        new_content = input(f"请输入新内容 (当前: {node['content'][:50]}...): ")
        if new_content:
            updates['content'] = new_content
        
        new_confidence = input(f"请输入新置信度 (当前: {node['confidence']}): ")
        if new_confidence:
            try:
                updates['confidence'] = float(new_confidence)
            except:
                print("置信度必须是数字")
        
        if updates:
            success = self.manager.update_node(node_id, updates)
            if success:
                print("节点更新成功")
            else:
                print("节点更新失败")
        else:
            print("没有要更新的内容")
        
        input("按Enter键返回...")
    
    def delete_node(self):
        """删除节点"""
        node_id = input("请输入节点ID: ")
        if not node_id:
            print("节点ID不能为空")
            input("按Enter键返回...")
            return
        
        confirm = input("确定要删除该节点吗？(y/n): ")
        if confirm.lower() == "y":
            success = self.manager.delete_node(node_id)
            if success:
                print("节点删除成功")
            else:
                print("节点删除失败")
        
        input("按Enter键返回...")
    
    def manage_relationships(self):
        """管理关系"""
        while True:
            print("\n管理关系")
            print("="*50)
            print("1. 查看关系列表")
            print("2. 查看关系详情")
            print("3. 添加关系")
            print("4. 更新关系")
            print("5. 删除关系")
            print("6. 返回主菜单")
            print("="*50)
            
            choice = input("请输入选项编号: ")
            
            if choice == "1":
                self.view_relationships()
            elif choice == "2":
                self.view_relationship_detail()
            elif choice == "3":
                self.add_relationship()
            elif choice == "4":
                self.update_relationship()
            elif choice == "5":
                self.delete_relationship()
            elif choice == "6":
                break
            else:
                print("无效选项，请重新输入")
    
    def view_relationships(self):
        """查看关系列表"""
        rel_type = input("请输入关系类型 (留空查看所有类型): ")
        limit = input("请输入显示数量 (默认100): ")
        limit = int(limit) if limit else 100
        
        relationships = self.manager.get_relationships(type=rel_type if rel_type else None, limit=limit)
        
        print(f"\n关系列表 (共 {len(relationships)} 个):")
        print("="*100)
        print(f"{'ID':<20} {'源节点':<20} {'目标节点':<20} {'类型':<15} {'审查状态':<10}")
        print("="*100)
        
        for rel in relationships:
            reviewed = "已审查" if rel['reviewed'] else "未审查"
            print(f"{rel['id']:<20} {rel['source_node'][:18]:<20} {rel['target_node'][:18]:<20} {rel['type']:<15} {reviewed:<10}")
        
        input("按Enter键返回...")
    
    def view_relationship_detail(self):
        """查看关系详情"""
        rel_id = input("请输入关系ID: ")
        if not rel_id:
            print("关系ID不能为空")
            input("按Enter键返回...")
            return
        
        rel = self.manager.get_relationship(rel_id)
        if rel:
            print("\n关系详情:")
            print("="*50)
            print(f"ID: {rel['id']}")
            print(f"源节点: {rel['source_node']}")
            print(f"目标节点: {rel['target_node']}")
            print(f"类型: {rel['type']}")
            print(f"强度: {rel['strength']}")
            print(f"描述: {rel['description']}")
            print(f"来源: {rel['source']}")
            print(f"创建时间: {time.ctime(rel['created_at'])}")
            print(f"更新时间: {time.ctime(rel['updated_at'])}")
            print(f"审查状态: {'已审查' if rel['reviewed'] else '未审查'}")
        else:
            print("关系不存在")
        
        input("按Enter键返回...")
    
    def add_relationship(self):
        """添加关系"""
        source_node = input("请输入源节点ID: ")
        target_node = input("请输入目标节点ID: ")
        rel_type = input("请输入关系类型: ")
        description = input("请输入关系描述: ")
        source = input("请输入来源 (默认manual): ") or "manual"
        
        if not source_node or not target_node or not rel_type:
            print("源节点、目标节点和关系类型不能为空")
            input("按Enter键返回...")
            return
        
        rel_id = self.manager.add_relationship(source_node, target_node, rel_type, description, source)
        print(f"\n关系添加成功，ID: {rel_id}")
        input("按Enter键返回...")
    
    def update_relationship(self):
        """更新关系"""
        rel_id = input("请输入关系ID: ")
        if not rel_id:
            print("关系ID不能为空")
            input("按Enter键返回...")
            return
        
        rel = self.manager.get_relationship(rel_id)
        if not rel:
            print("关系不存在")
            input("按Enter键返回...")
            return
        
        updates = {}
        
        new_type = input(f"请输入新关系类型 (当前: {rel['type']}): ")
        if new_type:
            updates['type'] = new_type
        
        new_strength = input(f"请输入新强度 (当前: {rel['strength']}): ")
        if new_strength:
            try:
                updates['strength'] = float(new_strength)
            except:
                print("强度必须是数字")
        
        new_description = input(f"请输入新描述 (当前: {rel['description']}): ")
        if new_description:
            updates['description'] = new_description
        
        if updates:
            success = self.manager.update_relationship(rel_id, updates)
            if success:
                print("关系更新成功")
            else:
                print("关系更新失败")
        else:
            print("没有要更新的内容")
        
        input("按Enter键返回...")
    
    def delete_relationship(self):
        """删除关系"""
        rel_id = input("请输入关系ID: ")
        if not rel_id:
            print("关系ID不能为空")
            input("按Enter键返回...")
            return
        
        confirm = input("确定要删除该关系吗？(y/n): ")
        if confirm.lower() == "y":
            success = self.manager.delete_relationship(rel_id)
            if success:
                print("关系删除成功")
            else:
                print("关系删除失败")
        
        input("按Enter键返回...")
    
    def review_knowledge_graph(self):
        """审查知识图谱"""
        while True:
            print("\n审查知识图谱")
            print("="*50)
            print("1. 审查节点")
            print("2. 审查关系")
            print("3. 返回主菜单")
            print("="*50)
            
            choice = input("请输入选项编号: ")
            
            if choice == "1":
                self.review_nodes()
            elif choice == "2":
                self.review_relationships()
            elif choice == "3":
                break
            else:
                print("无效选项，请重新输入")
    
    def review_nodes(self):
        """审查节点"""
        nodes = self.manager.get_unreviewed_entities("node", limit=10)
        
        if not nodes:
            print("没有未审查的节点")
            input("按Enter键返回...")
            return
        
        print(f"\n未审查节点列表 (共 {len(nodes)} 个):")
        print("="*80)
        print(f"{'ID':<20} {'标签':<30} {'类型':<15}")
        print("="*80)
        
        for node in nodes:
            print(f"{node['id']:<20} {node['label'][:28]:<30} {node['type']:<15}")
        
        node_id = input("\n请输入要审查的节点ID: ")
        if not node_id:
            input("按Enter键返回...")
            return
        
        action = input("请输入审查动作 (approve/reject/modify): ")
        comments = input("请输入审查意见: ")
        
        success = self.manager.review_entity("node", node_id, self.reviewer, action, comments)
        if success:
            print("节点审查成功")
        else:
            print("节点审查失败")
        
        input("按Enter键返回...")
    
    def review_relationships(self):
        """审查关系"""
        relationships = self.manager.get_unreviewed_entities("relationship", limit=10)
        
        if not relationships:
            print("没有未审查的关系")
            input("按Enter键返回...")
            return
        
        print(f"\n未审查关系列表 (共 {len(relationships)} 个):")
        print("="*100)
        print(f"{'ID':<20} {'源节点':<20} {'目标节点':<20} {'类型':<15}")
        print("="*100)
        
        for rel in relationships:
            print(f"{rel['id']:<20} {rel['source_node'][:18]:<20} {rel['target_node'][:18]:<20} {rel['type']:<15}")
        
        rel_id = input("\n请输入要审查的关系ID: ")
        if not rel_id:
            input("按Enter键返回...")
            return
        
        action = input("请输入审查动作 (approve/reject/modify): ")
        comments = input("请输入审查意见: ")
        
        success = self.manager.review_entity("relationship", rel_id, self.reviewer, action, comments)
        if success:
            print("关系审查成功")
        else:
            print("关系审查失败")
        
        input("按Enter键返回...")
    
    def export_import_graph(self):
        """导出/导入知识图谱"""
        while True:
            print("\n导出/导入知识图谱")
            print("="*50)
            print("1. 导出为JSON")
            print("2. 导出为GraphML")
            print("3. 导入知识图谱")
            print("4. 返回主菜单")
            print("="*50)
            
            choice = input("请输入选项编号: ")
            
            if choice == "1":
                self.export_json()
            elif choice == "2":
                self.export_graphml()
            elif choice == "3":
                self.import_graph()
            elif choice == "4":
                break
            else:
                print("无效选项，请重新输入")
    
    def export_json(self):
        """导出为JSON"""
        output_file = input("请输入输出文件路径 (默认: knowledge_graph.json): ") or "knowledge_graph.json"
        
        graph = self.manager.export_graph("json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
        
        print(f"\n知识图谱已导出到: {output_file}")
        print(f"节点数: {len(graph['nodes'])}")
        print(f"关系数: {len(graph['relationships'])}")
        
        input("按Enter键返回...")
    
    def export_graphml(self):
        """导出为GraphML"""
        output_file = input("请输入输出文件路径 (默认: knowledge_graph.graphml): ") or "knowledge_graph.graphml"
        
        graphml = self.manager.export_graph("graphml")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(graphml)
        
        print(f"\n知识图谱已导出到: {output_file}")
        
        input("按Enter键返回...")
    
    def import_graph(self):
        """导入知识图谱"""
        input_file = input("请输入输入文件路径: ")
        if not input_file:
            print("文件路径不能为空")
            input("按Enter键返回...")
            return
        
        if not os.path.exists(input_file):
            print("文件不存在")
            input("按Enter键返回...")
            return
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            success = self.manager.import_graph(data)
            if success:
                print("知识图谱导入成功")
            else:
                print("知识图谱导入失败")
        except Exception as e:
            print(f"导入失败: {e}")
        
        input("按Enter键返回...")
    
    def view_statistics(self):
        """查看统计信息"""
        stats = self.manager.get_stats()
        
        print("\n知识图谱统计信息")
        print("="*50)
        print(f"总节点数: {stats.get('total_nodes', 0)}")
        print(f"已审查节点数: {stats.get('reviewed_nodes', 0)}")
        print(f"总关系数: {stats.get('total_relationships', 0)}")
        print(f"已审查关系数: {stats.get('reviewed_relationships', 0)}")
        
        print("\n节点类型分布:")
        for node_type, count in stats.get('node_types', {}).items():
            print(f"  {node_type}: {count}")
        
        print("\n关系类型分布:")
        for rel_type, count in stats.get('relationship_types', {}).items():
            print(f"  {rel_type}: {count}")
        
        input("按Enter键返回...")

if __name__ == "__main__":
    # 测试知识图谱UI
    ui = KnowledgeGraphUI("../../structured")
    ui.run()
