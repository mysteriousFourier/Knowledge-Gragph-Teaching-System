"""Graph search module: keyword search and semantic search."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from KGTS.core.graph_manager import KnowledgeGraph


class GraphSearch:

    def __init__(self, db_path: Optional[str] = None):
        self.kg = KnowledgeGraph(db_path)

    def keyword_search(self, keyword: str, node_type: Optional[str] = None,
                      limit: int = 20) -> List[Dict]:
        nodes = self.kg.search_nodes(keyword, node_type, limit)
        return [node.__dict__ for node in nodes]

    def semantic_search(self, query: str, node_type: Optional[str] = None,
                       top_k: int = 10) -> List[Dict]:
        results = self.kg.semantic_search(query, node_type, top_k)
        return results

    def hybrid_search(self, keyword: str, node_type: Optional[str] = None,
                     limit: int = 20) -> Dict:
        keyword_results = self.keyword_search(keyword, node_type, limit)
        semantic_results = self.semantic_search(keyword, node_type, limit)

        seen_ids: set[str] = set()
        combined_results: List[Dict[str, Any]] = []

        for result in semantic_results:
            node_id = result['node_id']
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                combined_results.append({
                    "node_id": node_id,
                    "node": result['metadata'],
                    "similarity": result['similarity'],
                    "match_type": "semantic"
                })

        for result in keyword_results:
            if result['id'] not in seen_ids and len(combined_results) < limit:
                seen_ids.add(result['id'])
                combined_results.append({
                    "node_id": result['id'],
                    "node": result,
                    "similarity": 0.0,
                    "match_type": "keyword"
                })

        return {
            "total": len(combined_results),
            "results": combined_results
        }
