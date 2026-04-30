"""
知识图谱数据存储层
使用SQLite存储节点、关系和元数据
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import uuid


@dataclass
class Node:
    """知识图谱节点"""
    id: str
    content: str
    type: str  # chapter, concept, note等
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str


@dataclass
class Relation:
    """知识图谱关系"""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # parent, contains, precedes等
    metadata: Dict[str, Any]
    created_at: str


class KnowledgeGraphStorage:
    """知识图谱存储"""

    def __init__(self, db_path: str):
        self.db_path = db_path
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
                FOREIGN KEY (source_id) REFERENCES nodes(id),
                FOREIGN KEY (target_id) REFERENCES nodes(id)
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id)")

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

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

        return True

    def search_nodes(self, keyword: str, node_type: Optional[str] = None, limit: int = 20) -> List[Node]:
        """搜索节点"""
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

    def add_relation(self, source_id: str, target_id: str, relation_type: str, metadata: Optional[Dict] = None) -> Relation:
        """添加关系"""
        relation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        metadata = metadata or {}

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO relations (id, source_id, target_id, relation_type, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (relation_id, source_id, target_id, relation_type, json.dumps(metadata, ensure_ascii=False), now))

        conn.commit()
        conn.close()

        return Relation(
            id=relation_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata,
            created_at=now
        )

    def get_relations(self, node_id: Optional[str] = None) -> List[Relation]:
        """获取关系"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if node_id:
            cursor.execute(
                "SELECT * FROM relations WHERE source_id = ? OR target_id = ?",
                (node_id, node_id)
            )
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
                created_at=row["created_at"]
            )
            for row in rows
        ]

    def get_graph_structure(self) -> Dict:
        """获取完整图谱结构"""
        nodes = self.get_all_nodes()
        relations = self.get_relations()

        return {
            "nodes": [asdict(node) for node in nodes],
            "relations": [asdict(relation) for relation in relations],
            "stats": {
                "node_count": len(nodes),
                "relation_count": len(relations),
                "node_types": list(set(n.type for n in nodes))
            }
        }

    def get_neighbors(self, node_id: str) -> Dict[str, List[Node]]:
        """获取节点的邻居"""
        relations = self.get_relations(node_id)
        neighbors = {"sources": [], "targets": []}

        for rel in relations:
            if rel.source_id == node_id:
                target = self.get_node(rel.target_id)
                if target:
                    neighbors["targets"].append(target)
            elif rel.target_id == node_id:
                source = self.get_node(rel.source_id)
                if source:
                    neighbors["sources"].append(source)

        return neighbors
