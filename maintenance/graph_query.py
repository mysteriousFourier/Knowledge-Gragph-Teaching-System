"""Graph query module: query operations for the knowledge graph."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from KGTS.core.graph_manager import KnowledgeGraph


class GraphQuery:

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def get_graph_structure(self) -> Dict:
        return self.kg.get_graph_structure()

    def get_graph_schema(self) -> Dict:
        return self.kg.get_graph_schema()

    def get_node(self, node_id: str) -> Optional[Dict]:
        node = self.kg.get_node(node_id)
        if node:
            return node.__dict__
        return None

    def get_nodes_by_type(self, node_type: str) -> List[Dict]:
        nodes = self.kg.get_all_nodes(node_type)
        return [node.__dict__ for node in nodes]

    def get_relations(self, node_id: Optional[str] = None,
                     relation_type: Optional[str] = None) -> List[Dict]:
        relations = self.kg.get_relations(node_id, relation_type)
        return [r.__dict__ for r in relations]

    def get_neighbors(self, node_id: str, direction: str = "both") -> Dict[str, List[Dict]]:
        neighbors = self.kg.get_neighbors(node_id, direction)
        return {
            "in": [n.__dict__ for n in neighbors["in"]],
            "out": [n.__dict__ for n in neighbors["out"]]
        }

    def trace_call_path(self, start_node_id: str, max_depth: int = 5) -> List[Dict]:
        return self.kg.trace_call_path(start_node_id, max_depth)

    def discover_weak_relations(self, node_id: str, threshold: float = 0.3) -> List[Dict]:
        return self.kg.discover_weak_relations(node_id, threshold)
