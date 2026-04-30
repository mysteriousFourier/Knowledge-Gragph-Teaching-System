#!/usr/bin/env python3
"""
知识图谱与向量检索集成模块

功能：
- 将知识图谱中的节点添加到向量索引
- 实现基于向量的知识图谱搜索
- 提供混合检索功能（向量+结构）
- 支持知识图谱的向量增强
"""

import os
import sys
import json
import sqlite3
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from vector_retrieval import VectorRetriever

class GraphVectorIntegration:
    """知识图谱与向量检索集成"""
    
    def __init__(self, db_path: str = "./knowledge_graph/knowledge_graph.db", vector_index_path: str = "./vector_index"):
        """
        初始化知识图谱与向量检索集成
        
        Args:
            db_path: 知识图谱数据库路径
            vector_index_path: 向量索引存储路径
        """
        self.db_path = Path(db_path)
        self.vector_index_path = Path(vector_index_path)
        
        # 初始化向量检索器
        self.retriever = VectorRetriever(index_path=str(vector_index_path))
        
        # 检查数据库是否存在
        if not self.db_path.exists():
            print(f"警告: 知识图谱数据库 {db_path} 不存在")
        
        # 增量更新相关
        self.processed_nodes_file = self.vector_index_path / "processed_nodes.json"
        self.processed_nodes = self._load_processed_nodes()
        
    def _load_processed_nodes(self):
        """
        加载已处理的节点ID
        
        Returns:
            已处理的节点ID集合
        """
        if self.processed_nodes_file.exists():
            try:
                with open(self.processed_nodes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return set(data.get('processed_nodes', []))
            except Exception as e:
                print(f"加载已处理节点失败: {e}")
                return set()
        return set()
    
    def _save_processed_nodes(self):
        """
        保存已处理的节点ID
        """
        try:
            data = {
                'processed_nodes': list(self.processed_nodes),
                'last_updated': time.time()
            }
            with open(self.processed_nodes_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"已保存 {len(self.processed_nodes)} 个已处理节点")
        except Exception as e:
            print(f"保存已处理节点失败: {e}")
    
    def _get_db_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(str(self.db_path))
    
    def index_knowledge_graph(self, batch_size: int = 50, limit: int = None):
        """
        增量更新方式分批次添加知识图谱索引
        
        Args:
            batch_size: 每批次处理的节点数量
            limit: 本次处理的节点总数限制
        """
        print("开始增量索引知识图谱...")
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 检查数据库连接
            print(f"数据库路径: {self.db_path}")
            print(f"数据库是否存在: {self.db_path.exists()}")
            print(f"已处理节点数: {len(self.processed_nodes)}")
            
            # 获取未处理的节点
            print("执行SQL查询获取未处理节点...")
            
            # 构建查询条件
            if self.processed_nodes:
                # 使用占位符处理多个参数
                placeholders = ','.join(['?'] * len(self.processed_nodes))
                query = f"SELECT id, label, type, content FROM nodes WHERE id NOT IN ({placeholders})"
                cursor.execute(query, list(self.processed_nodes))
            else:
                query = "SELECT id, label, type, content FROM nodes"
                cursor.execute(query)
            
            nodes = cursor.fetchall()
            total_nodes = len(nodes)
            print(f"发现 {total_nodes} 个未处理节点")
            
            # 应用限制
            if limit:
                nodes = nodes[:limit]
                print(f"限制处理 {len(nodes)} 个节点")
            
            # 分批次处理
            total_processed = 0
            for i in range(0, len(nodes), batch_size):
                batch_nodes = nodes[i:i+batch_size]
                batch_size_actual = len(batch_nodes)
                print(f"\n处理批次 {i//batch_size + 1}/{(len(nodes) + batch_size - 1)//batch_size}")
                print(f"处理 {batch_size_actual} 个节点")
                
                # 准备批次数据
                texts = []
                metadatas = []
                batch_node_ids = []
                
                for j, (node_id, label, node_type, content) in enumerate(batch_nodes):
                    # 使用节点的标签和内容作为文本
                    text = f"{label}: {content}" if content else label
                    metadata = {
                        'node_id': node_id,
                        'type': node_type,
                        'label': label
                    }
                    texts.append(text)
                    metadatas.append(metadata)
                    batch_node_ids.append(node_id)
                    
                    # 每10个节点打印一次进度
                    if (j + 1) % 10 == 0:
                        print(f"  处理节点 {j + 1}/{batch_size_actual}")
                
                # 添加到向量索引
                if texts:
                    print(f"  添加 {len(texts)} 个节点到向量索引...")
                    self.retriever.add_batch(texts, metadatas)
                    
                    # 更新已处理节点
                    for node_id in batch_node_ids:
                        self.processed_nodes.add(node_id)
                    
                    # 保存已处理节点
                    self._save_processed_nodes()
                    
                    total_processed += len(texts)
                    print(f"  已处理 {total_processed}/{len(nodes)} 个节点")
                
                # 短暂休息，避免系统负载过高
                if i + batch_size < len(nodes):
                    print("  休息1秒...")
                    time.sleep(1)
            
            print(f"\n知识图谱增量索引完成")
            print(f"本次处理 {total_processed} 个节点")
            print(f"累计处理 {len(self.processed_nodes)} 个节点")
            
        except Exception as e:
            print(f"索引知识图谱时出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            conn.close()
    
    def search_knowledge_graph(self, query: str, k: int = 5, include_relationships: bool = False) -> List[Dict[str, Any]]:
        """
        搜索知识图谱
        
        Args:
            query: 查询文本
            k: 返回的结果数量
            include_relationships: 是否包含关系信息
        
        Returns:
            搜索结果列表
        """
        print(f"搜索知识图谱: {query}")
        
        # 1. 向量搜索
        vector_results = self.retriever.search(query, k=k)
        
        # 2. 处理搜索结果
        results = []
        for text, similarity, metadata in vector_results:
            node_id = metadata.get('node_id')
            node_type = metadata.get('type')
            label = metadata.get('label')
            
            result = {
                'node_id': node_id,
                'label': label,
                'type': node_type,
                'similarity': similarity,
                'text': text
            }
            
            # 如果需要包含关系信息
            if include_relationships and node_id:
                relationships = self._get_node_relationships(node_id)
                result['relationships'] = relationships
            
            results.append(result)
        
        return results
    
    def _get_node_relationships(self, node_id: str) -> List[Dict[str, Any]]:
        """
        获取节点的关系
        
        Args:
            node_id: 节点ID
        
        Returns:
            关系列表
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        relationships = []
        
        try:
            # 获取以该节点为源的关系
            cursor.execute("""
                SELECT r.id, r.target_node, r.type, r.strength, r.description, n.label 
                FROM relationships r
                LEFT JOIN nodes n ON r.target_node = n.id
                WHERE r.source_node = ?
            """, (node_id,))
            
            for rel_id, target_node, rel_type, strength, description, target_label in cursor.fetchall():
                relationships.append({
                    'id': rel_id,
                    'type': rel_type,
                    'target_node': target_node,
                    'target_label': target_label,
                    'strength': strength,
                    'description': description,
                    'direction': 'outgoing'
                })
            
            # 获取以该节点为目标的关系
            cursor.execute("""
                SELECT r.id, r.source_node, r.type, r.strength, r.description, n.label 
                FROM relationships r
                LEFT JOIN nodes n ON r.source_node = n.id
                WHERE r.target_node = ?
            """, (node_id,))
            
            for rel_id, source_node, rel_type, strength, description, source_label in cursor.fetchall():
                relationships.append({
                    'id': rel_id,
                    'type': rel_type,
                    'source_node': source_node,
                    'source_label': source_label,
                    'strength': strength,
                    'description': description,
                    'direction': 'incoming'
                })
                
        except Exception as e:
            print(f"获取节点关系时出错: {e}")
        finally:
            conn.close()
        
        return relationships
    
    def hybrid_search(self, query: str, k: int = 5, structure_weight: float = 0.3) -> List[Dict[str, Any]]:
        """
        混合搜索（向量+结构）
        
        Args:
            query: 查询文本
            k: 返回的结果数量
            structure_weight: 结构权重
        
        Returns:
            搜索结果列表
        """
        # 1. 向量搜索
        vector_results = self.retriever.search(query, k=k * 2)  # 获取更多结果
        
        # 2. 结构增强
        results = []
        for text, similarity, metadata in vector_results:
            node_id = metadata.get('node_id')
            
            # 计算结构分数（基于关系数量）
            relationships = self._get_node_relationships(node_id)
            structure_score = min(len(relationships) / 10, 1.0)  # 关系数量归一化
            
            # 混合分数
            hybrid_score = similarity * (1 - structure_weight) + structure_score * structure_weight
            
            result = {
                'node_id': node_id,
                'label': metadata.get('label'),
                'type': metadata.get('type'),
                'similarity': similarity,
                'structure_score': structure_score,
                'hybrid_score': hybrid_score,
                'text': text,
                'relationships_count': len(relationships)
            }
            
            results.append(result)
        
        # 按混合分数排序
        results.sort(key=lambda x: x['hybrid_score'], reverse=True)
        
        return results[:k]
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """
        获取知识图谱和向量索引的统计信息
        
        Returns:
            统计信息
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        try:
            # 知识图谱统计
            cursor.execute("SELECT COUNT(*) FROM nodes")
            stats['nodes_count'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM relationships")
            stats['relationships_count'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type")
            node_types = {}
            for node_type, count in cursor.fetchall():
                node_types[node_type] = count
            stats['node_types'] = node_types
            
            # 向量索引统计
            vector_stats = self.retriever.get_stats()
            stats['vector_index'] = vector_stats
            
        except Exception as e:
            print(f"获取统计信息时出错: {e}")
        finally:
            conn.close()
        
        return stats
    
    def update_vector_index(self):
        """
        更新向量索引
        """
        print("更新向量索引...")
        self.index_knowledge_graph()
        print("向量索引更新完成")

if __name__ == "__main__":
    # 测试知识图谱与向量检索集成
    integration = GraphVectorIntegration(
        db_path="./knowledge_graph/knowledge_graph.db",
        vector_index_path="./vector_index"
    )
    
    # 索引知识图谱
    integration.index_knowledge_graph()
    
    # 测试搜索
    print("\n测试向量搜索:")
    query = "人工智能"
    results = integration.search_knowledge_graph(query, k=3)
    
    print(f"查询: {query}")
    print("结果:")
    for i, result in enumerate(results, 1):
        print(f"{i}. 相似度: {result['similarity']:.4f}, 标签: {result['label']}, 类型: {result['type']}")
    
    # 测试混合搜索
    print("\n测试混合搜索:")
    hybrid_results = integration.hybrid_search(query, k=3)
    
    print(f"查询: {query}")
    print("结果:")
    for i, result in enumerate(hybrid_results, 1):
        print(f"{i}. 混合分数: {result['hybrid_score']:.4f}, 相似度: {result['similarity']:.4f}, 结构分数: {result['structure_score']:.4f}, 标签: {result['label']}")
    
    # 打印统计信息
    print("\n统计信息:")
    stats = integration.get_graph_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
