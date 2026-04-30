#!/usr/bin/env python3
"""
清除知识图谱缓存脚本

功能：
- 删除知识图谱数据库
- 清除向量索引缓存
- 移除处理节点记录
- 为重建知识图谱做准备
"""

import os
import sys
import shutil
from pathlib import Path

def clear_knowledge_graph_cache():
    """清除知识图谱缓存"""
    print("开始清除知识图谱缓存...")
    
    # 定义缓存文件路径
    current_dir = Path(__file__).parent
    knowledge_graph_db = current_dir / "knowledge_graph" / "knowledge_graph.db"
    processed_nodes = current_dir / "vector_index" / "processed_nodes.json"
    vector_index = current_dir / "vector_index" / "vector_index.faiss"
    metadata_file = current_dir / "vector_index" / "metadata.json"
    
    # 清除知识图谱数据库
    if knowledge_graph_db.exists():
        try:
            os.remove(knowledge_graph_db)
            print(f"已删除知识图谱数据库: {knowledge_graph_db}")
        except Exception as e:
            print(f"删除知识图谱数据库失败: {e}")
    else:
        print(f"知识图谱数据库不存在: {knowledge_graph_db}")
    
    # 清除处理节点记录
    if processed_nodes.exists():
        try:
            os.remove(processed_nodes)
            print(f"已删除处理节点记录: {processed_nodes}")
        except Exception as e:
            print(f"删除处理节点记录失败: {e}")
    else:
        print(f"处理节点记录不存在: {processed_nodes}")
    
    # 清除向量索引文件
    if vector_index.exists():
        try:
            os.remove(vector_index)
            print(f"已删除向量索引文件: {vector_index}")
        except Exception as e:
            print(f"删除向量索引文件失败: {e}")
    else:
        print(f"向量索引文件不存在: {vector_index}")
    
    # 清除元数据文件
    if metadata_file.exists():
        try:
            os.remove(metadata_file)
            print(f"已删除元数据文件: {metadata_file}")
        except Exception as e:
            print(f"删除元数据文件失败: {e}")
    else:
        print(f"元数据文件不存在: {metadata_file}")
    
    print("\n知识图谱缓存清除完成！")
    print("现在可以重新构建知识图谱了。")

if __name__ == "__main__":
    clear_knowledge_graph_cache()
