from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from KGTS.core.graph_service import GraphService
from KGTS.maintenance.graph_ops import get_visualization_graph


class GraphVisualizationPayloadTest(unittest.IsolatedAsyncioTestCase):
    async def test_visualization_graph_returns_limited_valid_payload(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            graph_path = Path(tmp) / "knowledge_graph.db"
            env = {
                "GRAPH_DB_PATH": str(graph_path),
                "APP_BOOTSTRAP_SEED_DATA": "0",
                "KGTS_RETRIEVAL_MODE": "graph_db",
            }
            with patch.dict(os.environ, env, clear=False):
                service = GraphService(graph_path)
                service.add_node("Chapter 1", "chapter", {"id": "chapter::chapter1", "label": "Chapter 1"})
                service.add_node("Chapter 2", "chapter", {"id": "chapter::chapter2", "label": "Chapter 2"})
                for index in range(12):
                    node_id = f"concept::{index}"
                    service.add_node(
                        f"Concept {index} detailed content",
                        "concept",
                        {
                            "id": node_id,
                            "label": f"Concept {index}",
                            "chapter": "chapter1" if index < 6 else "chapter2",
                            "unused_large_key": "x" * 1000,
                        },
                    )
                    service.add_relation("chapter::chapter1" if index < 6 else "chapter::chapter2", node_id, "contains")
                    if index:
                        service.add_relation(f"concept::{index - 1}", node_id, "precedes")

                payload = await get_visualization_graph(node_limit=10, relationship_limit=20)

        node_ids = {node["id"] for node in payload["nodes"]}
        self.assertLessEqual(len(payload["nodes"]), 10)
        self.assertLessEqual(len(payload["relationships"]), 20)
        self.assertIn("chapter::chapter1", node_ids)
        self.assertIn("chapter::chapter2", node_ids)
        self.assertTrue(payload["stats"]["truncated"])
        self.assertTrue(payload["relationships"])
        for relation in payload["relationships"]:
            self.assertIn(relation["source_id"], node_ids)
            self.assertIn(relation["target_id"], node_ids)
            self.assertIn("relation_type", relation)
            self.assertNotIn("source_node", relation)
            self.assertNotIn("target_node", relation)
        for node in payload["nodes"]:
            self.assertNotIn("unused_large_key", node["metadata"])

    async def test_visualization_graph_preserves_formula_resources_when_truncated(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            graph_path = Path(tmp) / "knowledge_graph.db"
            env = {
                "GRAPH_DB_PATH": str(graph_path),
                "APP_BOOTSTRAP_SEED_DATA": "0",
                "KGTS_RETRIEVAL_MODE": "graph_db",
            }
            with patch.dict(os.environ, env, clear=False):
                service = GraphService(graph_path)
                service.add_node("Chapter 1", "chapter", {"id": "chapter::chapter1", "label": "Chapter 1"})
                service.add_node("High degree section", "section", {"id": "section::hub", "label": "High degree section"})
                service.add_relation("chapter::chapter1", "section::hub", "contains")
                for index in range(30):
                    node_id = f"section::{index}"
                    service.add_node(f"Section {index}", "section", {"id": node_id, "label": f"Section {index}"})
                    service.add_relation("section::hub", node_id, "contains")
                    service.add_relation(node_id, "section::hub", "precedes")
                for index in range(6):
                    block_id = f"block::{index}"
                    formula_id = f"formula::chapter1::1.{index}"
                    service.add_node(f"Block {index} references formula", "derivation", {"id": block_id, "label": f"Block {index}"})
                    service.add_node(f"x_{index}=y_{index}", "formula", {"id": formula_id, "label": f"({index})"})
                    service.add_relation("section::hub", block_id, "contains")
                    service.add_relation(block_id, formula_id, "references_formula")

                payload = await get_visualization_graph(node_limit=18, relationship_limit=50)

        node_ids = {node["id"] for node in payload["nodes"]}
        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for relation in payload["relationships"]
        }

        self.assertTrue(any(node_id.startswith("formula::chapter1::") for node_id in node_ids))
        self.assertTrue(any(relation_type == "references_formula" for _, relation_type, _ in relation_keys))
        for source_id, _, target_id in relation_keys:
            self.assertIn(source_id, node_ids)
            self.assertIn(target_id, node_ids)


if __name__ == "__main__":
    unittest.main()
