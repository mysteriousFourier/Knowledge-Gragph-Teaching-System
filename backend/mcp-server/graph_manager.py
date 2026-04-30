"""
知识图谱数据模型和管理类
与OpenClaw Memory系统交互的接口层
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, asdict
import uuid
from vector_index import get_vector_index
from config import config


@dataclass
class Node:
    """知识图谱节点"""
    id: str
    content: str
    type: str  # chapter, concept, note, observation等
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str


@dataclass
class Relation:
    """知识图谱关系"""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # parent, contains, precedes, semantic_weak等
    metadata: Dict[str, Any]
    created_at: str
    similarity: Optional[float] = None  # 用于弱关系的相似度


class KnowledgeGraph:
    """知识图谱管理类"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.MEMORY_DB_PATH
        self.vector_index = get_vector_index()
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 节点表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # 关系表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT,
                similarity REAL,
                FOREIGN KEY (source_id) REFERENCES nodes(id),
                FOREIGN KEY (target_id) REFERENCES nodes(id)
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type)")

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== 节点操作 ====================

    def add_node(self, content: str, type: str, metadata: Optional[Dict] = None) -> Node:
        """添加节点"""
        node_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        metadata = metadata or {}

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO nodes (id, content, type, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (node_id, content, type, json.dumps(metadata, ensure_ascii=False), now, now))

        conn.commit()
        conn.close()

        # 添加到向量索引
        self.vector_index.add_node(node_id, content, type, metadata)

        return Node(id=node_id, content=content, type=type, metadata=metadata, created_at=now, updated_at=now)

    def get_node(self, node_id: str) -> Optional[Node]:
        """获取单个节点"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return Node(
                id=row["id"],
                content=row["content"],
                type=row["type"],
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
        return None

    def update_node(self, node_id: str, content: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
        """更新节点"""
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if content is not None:
            updates.append("content = ?")
            params.append(content)

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata, ensure_ascii=False))

        if not updates:
            conn.close()
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(node_id)

        cursor.execute(f"UPDATE nodes SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        conn.close()

        # 更新向量索引
        if content:
            node = self.get_node(node_id)
            if node:
                self.vector_index.add_node(node_id, content, node.type, node.metadata)

        return cursor.rowcount > 0

    def delete_node(self, node_id: str) -> bool:
        """删除节点"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 先删除相关关系
        cursor.execute("DELETE FROM relations WHERE source_id = ? OR target_id = ?", (node_id, node_id))
        # 删除节点
        cursor.execute("DELETE FROM nodes WHERE id = ?", (node_id,))

        conn.commit()
        conn.close()

        # 从向量索引中删除
        self.vector_index.delete_node(node_id)

        return True

    # ==================== 搜索操作 ====================

    def search_nodes(self, keyword: str, node_type: Optional[str] = None, limit: int = 20) -> List[Node]:
        """关键词搜索节点"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM nodes WHERE content LIKE ?"
        params = [f"%{keyword}%"]

        if node_type:
            query += " AND type = ?"
            params.append(node_type)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            Node(
                id=row["id"],
                content=row["content"],
                type=row["type"],
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in rows
        ]

    def semantic_search(self, query: str, node_type: Optional[str] = None, top_k: int = 10) -> List[Dict]:
        """语义搜索（基于向量）"""
        return self.vector_index.search(query, top_k=top_k, node_type=node_type)

    # ==================== 关系操作 ====================

    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                     metadata: Optional[Dict] = None, similarity: Optional[float] = None) -> Relation:
        """添加关系"""
        relation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        metadata = metadata or {}

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO relations (id, source_id, target_id, relation_type, metadata, created_at, similarity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (relation_id, source_id, target_id, relation_type,
              json.dumps(metadata, ensure_ascii=False), now, similarity))

        conn.commit()
        conn.close()

        return Relation(
            id=relation_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata,
            created_at=now,
            similarity=similarity
        )

    def get_relations(self, node_id: Optional[str] = None,
                      relation_type: Optional[str] = None) -> List[Relation]:
        """获取关系"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if node_id:
            if relation_type:
                cursor.execute(
                    "SELECT * FROM relations WHERE (source_id = ? OR target_id = ?) AND relation_type = ?",
                    (node_id, node_id, relation_type)
                )
            else:
                cursor.execute(
                    "SELECT * FROM relations WHERE source_id = ? OR target_id = ?",
                    (node_id, node_id)
                )
        else:
            if relation_type:
                cursor.execute("SELECT * FROM relations WHERE relation_type = ?", (relation_type,))
            else:
                cursor.execute("SELECT * FROM relations")

        rows = cursor.fetchall()
        conn.close()

        return [
            Relation(
                id=row["id"],
                source_id=row["source_id"],
                target_id=row["target_id"],
                relation_type=row["relation_type"],
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                similarity=row["similarity"]
            )
            for row in rows
        ]

    def delete_relation(self, relation_id: str) -> bool:
        """删除关系"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM relations WHERE id = ?", (relation_id,))

        conn.commit()
        conn.close()

        return cursor.rowcount > 0

    # ==================== 图谱查询 ====================

    def get_graph_structure(self) -> Dict:
        """获取完整图谱结构"""
        nodes = self.get_all_nodes()
        relations = self.get_relations()

        # 统计节点类型
        node_types = {}
        for node in nodes:
            node_types[node.type] = node_types.get(node.type, 0) + 1

        return {
            "nodes": [asdict(node) for node in nodes],
            "relations": [asdict(rel) for rel in relations],
            "stats": {
                "node_count": len(nodes),
                "relation_count": len(relations),
                "node_types": node_types
            },
            "vector_stats": self.vector_index.get_statistics()
        }

    def get_neighbors(self, node_id: str, direction: str = "both") -> Dict[str, List[Node]]:
        """获取节点的邻居

        Args:
            node_id: 节点ID
            direction: "in"（指向该节点）, "out"（该节点指向）, "both"（双向）
        """
        relations = self.get_relations(node_id)
        neighbors = {"in": [], "out": []}

        for rel in relations:
            if direction in ["in", "both"] and rel.target_id == node_id:
                source = self.get_node(rel.source_id)
                if source:
                    neighbors["in"].append(source)
            if direction in ["out", "both"] and rel.source_id == node_id:
                target = self.get_node(rel.target_id)
                if target:
                    neighbors["out"].append(target)

        return neighbors

    def trace_call_path(self, start_node_id: str, max_depth: int = 5) -> List[Dict]:
        """BFS追踪调用链（知识路径）"""
        visited = set()
        queue = [(start_node_id, 0, [])]  # (node_id, depth, path)
        paths = []

        while queue:
            node_id, depth, path = queue.pop(0)

            if node_id in visited or depth > max_depth:
                continue

            visited.add(node_id)
            current_path = path + [node_id]

            node = self.get_node(node_id)
            if node:
                paths.append({
                    "node_id": node_id,
                    "depth": depth,
                    "path": current_path,
                    "node": asdict(node)
                })

            # 获取出边邻居
            neighbors = self.get_neighbors(node_id, direction="out")
            for neighbor in neighbors.get("out", []):
                if neighbor.id not in visited:
                    queue.append((neighbor.id, depth + 1, current_path))

        return paths

    def discover_weak_relations(self, node_id: str, threshold: float = 0.3) -> List[Dict]:
        """发现弱关系（基于向量相似度）"""
        return self.vector_index.find_weak_relations(node_id, threshold)

    def get_all_nodes(self, node_type: Optional[str] = None) -> List[Node]:
        """获取所有节点"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if node_type:
            cursor.execute("SELECT * FROM nodes WHERE type = ? ORDER BY created_at", (node_type,))
        else:
            cursor.execute("SELECT * FROM nodes ORDER BY created_at")

        rows = cursor.fetchall()
        conn.close()

        return [
            Node(
                id=row["id"],
                content=row["content"],
                type=row["type"],
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in rows
        ]

    # ==================== 批量操作 ====================

    def batch_add_nodes(self, nodes_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量添加节点

        Args:
            nodes_data: 节点数据列表，每个元素包含 content, type, metadata

        Returns:
            导入结果统计
        """
        success_count = 0
        failed_count = 0
        errors = []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            for node_data in nodes_data:
                try:
                    node_id = node_data.get("id") or str(uuid.uuid4())
                    content = node_data.get("content", "")
                    node_type = node_data.get("type", "concept")
                    metadata = node_data.get("metadata", {})
                    now = datetime.now().isoformat()

                    cursor.execute("""
                        INSERT OR REPLACE INTO nodes (id, content, type, metadata, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (node_id, content, node_type, json.dumps(metadata, ensure_ascii=False), now, now))

                    success_count += 1

                    # 添加到向量索引（异步或批量）
                    self.vector_index.add_node(node_id, content, node_type, metadata)

                except Exception as e:
                    failed_count += 1
                    errors.append(f"Node {node_data.get('id', 'unknown')}: {str(e)}")

            conn.commit()

        except Exception as e:
            conn.rollback()
            errors.append(f"Batch operation failed: {str(e)}")
        finally:
            conn.close()

        return {
            "total": len(nodes_data),
            "success": success_count,
            "failed": failed_count,
            "errors": errors
        }

    def batch_add_relations(self, relations_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量添加关系

        Args:
            relations_data: 关系数据列表，每个元素包含 source_id, target_id, relation_type, metadata

        Returns:
            导入结果统计
        """
        success_count = 0
        failed_count = 0
        errors = []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            for rel_data in relations_data:
                try:
                    relation_id = rel_data.get("id") or str(uuid.uuid4())
                    source_id = rel_data.get("source_id")
                    target_id = rel_data.get("target_id")
                    relation_type = rel_data.get("relation_type", "related")
                    metadata = rel_data.get("metadata", {})
                    similarity = rel_data.get("similarity")
                    now = datetime.now().isoformat()

                    if not source_id or not target_id:
                        raise ValueError("Missing source_id or target_id")

                    cursor.execute("""
                        INSERT OR REPLACE INTO relations (id, source_id, target_id, relation_type, metadata, created_at, similarity)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (relation_id, source_id, target_id, relation_type,
                          json.dumps(metadata, ensure_ascii=False), now, similarity))

                    success_count += 1

                except Exception as e:
                    failed_count += 1
                    errors.append(f"Relation {rel_data.get('source_id', 'unknown')}->{rel_data.get('target_id', 'unknown')}: {str(e)}")

            conn.commit()

        except Exception as e:
            conn.rollback()
            errors.append(f"Batch operation failed: {str(e)}")
        finally:
            conn.close()

        return {
            "total": len(relations_data),
            "success": success_count,
            "failed": failed_count,
            "errors": errors
        }

    def batch_import_graph(self, nodes_data: List[Dict[str, Any]], relations_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量导入完整图谱

        Args:
            nodes_data: 节点数据列表
            relations_data: 关系数据列表

        Returns:
            导入结果统计
        """
        nodes_result = self.batch_add_nodes(nodes_data)
        relations_result = self.batch_add_relations(relations_data)

        return {
            "nodes": nodes_result,
            "relations": relations_result,
            "total_nodes": len(nodes_data),
            "total_relations": len(relations_data),
            "imported_at": datetime.now().isoformat()
        }

    # ==================== 图谱分析 ====================

    def get_graph_statistics(self) -> Dict[str, Any]:
        """获取图谱统计信息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 节点统计
        cursor.execute("SELECT COUNT(*) FROM nodes")
        total_nodes = cursor.fetchone()[0]

        cursor.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type")
        node_type_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 关系统计
        cursor.execute("SELECT COUNT(*) FROM relations")
        total_relations = cursor.fetchone()[0]

        cursor.execute("SELECT relation_type, COUNT(*) FROM relations GROUP BY relation_type")
        relation_type_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 连接性统计
        cursor.execute("""
            SELECT COUNT(DISTINCT source_id || '-' || target_id) as unique_connections
            FROM relations
        """)
        unique_connections = cursor.fetchone()[0]

        # 计算平均连接度
        avg_degree = 0
        if total_nodes > 0:
            avg_degree = (total_relations * 2) / total_nodes

        conn.close()

        return {
            "nodes": {
                "total": total_nodes,
                "by_type": node_type_counts
            },
            "relations": {
                "total": total_relations,
                "by_type": relation_type_counts
            },
            "connectivity": {
                "unique_connections": unique_connections,
                "average_degree": round(avg_degree, 2),
                "density": round(total_relations / (total_nodes * (total_nodes - 1) / 2) if total_nodes > 1 else 0, 4)
            },
            "vector_stats": self.vector_index.get_statistics()
        }

    def get_subgraph_by_type(self, node_type: str) -> Dict[str, Any]:
        """按类型获取子图

        Args:
            node_type: 节点类型

        Returns:
            子图数据
        """
        nodes = self.get_all_nodes(node_type)
        node_ids = {node.id for node in nodes}

        # 获取这些节点之间的关系
        relations = []
        for rel in self.get_relations():
            if rel.source_id in node_ids and rel.target_id in node_ids:
                relations.append(rel)

        return {
            "type": node_type,
            "nodes": [asdict(node) for node in nodes],
            "relations": [asdict(rel) for rel in relations],
            "stats": {
                "node_count": len(nodes),
                "relation_count": len(relations)
            }
        }

    def get_k_hop_neighbors(self, node_id: str, k: int = 2) -> Dict[str, Any]:
        """获取k跳邻居

        Args:
            node_id: 起始节点ID
            k: 跳数

        Returns:
            按层级组织的邻居节点
        """
        visited = {node_id}
        layers = {0: [node_id]}
        result = {0: [asdict(self.get_node(node_id))]}

        for i in range(1, k + 1):
            layer_nodes = []
            layer_data = []

            for prev_node_id in layers[i - 1]:
                neighbors = self.get_neighbors(prev_node_id, direction="both")
                for neighbor in neighbors["in"] + neighbors["out"]:
                    if neighbor.id not in visited:
                        visited.add(neighbor.id)
                        layer_nodes.append(neighbor.id)
                        layer_data.append(asdict(neighbor))

            if layer_nodes:
                layers[i] = layer_nodes
                result[i] = layer_data
            else:
                break

        return result


# 全局知识图谱实例
_knowledge_graph = None


def get_knowledge_graph() -> KnowledgeGraph:
    """获取全局知识图谱实例"""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph
