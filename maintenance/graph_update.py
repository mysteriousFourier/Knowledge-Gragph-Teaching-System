"""Graph update module: CRUD operations for nodes and relations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from KGTS.core.graph_manager import KnowledgeGraph


class GraphUpdate:

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def add_node(self, content: str, type: str, metadata: Optional[Dict] = None) -> Dict:
        node = self.kg.add_node(content, type, metadata)
        return node.__dict__

    def update_node(self, node_id: str, content: Optional[str] = None,
                   metadata: Optional[Dict] = None) -> Dict:
        success = self.kg.update_node(node_id, content, metadata)
        return {"success": success, "node_id": node_id}

    def delete_node(self, node_id: str) -> Dict:
        success = self.kg.delete_node(node_id)
        return {"success": success, "node_id": node_id}

    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                    metadata: Optional[Dict] = None, similarity: Optional[float] = None) -> Dict:
        relation = self.kg.add_relation(source_id, target_id, relation_type, metadata, similarity)
        return relation.__dict__

    def delete_relation(self, relation_id: str) -> Dict:
        success = self.kg.delete_relation(relation_id)
        return {"success": success, "relation_id": relation_id}

    def batch_add_nodes(self, nodes: List[Dict]) -> List[Dict]:
        results = []
        for node in nodes:
            result = self.add_node(
                content=node.get("content", ""),
                type=node.get("type", "concept"),
                metadata=node.get("metadata", {})
            )
            results.append(result)
        return results

    def batch_add_relations(self, relations: List[Dict]) -> List[Dict]:
        results = []
        for rel in relations:
            result = self.add_relation(
                source_id=rel.get("source_id", ""),
                target_id=rel.get("target_id", ""),
                relation_type=rel.get("relation_type", "related"),
                metadata=rel.get("metadata", {}),
                similarity=rel.get("similarity")
            )
            results.append(result)
        return results
