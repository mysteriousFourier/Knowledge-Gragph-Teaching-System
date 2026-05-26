from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from KGTS.core.graph_service import GraphService
from KGTS.core.seed import ensure_seed_graph


class SeedRuntimeTest(unittest.TestCase):
    def test_seed_graph_merges_chapter_tree_without_overwriting_existing_nodes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            graph_path = Path(tmp) / "knowledge_graph.db"
            env = {
                "GRAPH_DB_PATH": str(graph_path),
                "APP_BOOTSTRAP_SEED_DATA": "1",
                "KGTS_RETRIEVAL_MODE": "graph_db",
            }
            with patch.dict(os.environ, env, clear=False):
                service = GraphService(graph_path)
                service.add_node(
                    "custom runtime note",
                    "note",
                    {"id": "runtime::custom-note", "label": "Custom runtime note"},
                )

                ensure_seed_graph()

                graph = GraphService(graph_path).read_graph()
                nodes_by_id = {node["id"]: node for node in graph["nodes"]}
                contains_count = sum(
                    1 for relation in graph["relations"] if relation.get("relation_type") == "contains"
                )

            self.assertIn("runtime::custom-note", nodes_by_id)
            self.assertIn("toc::root", nodes_by_id)
            self.assertGreaterEqual(contains_count, 9000)


if __name__ == "__main__":
    unittest.main()
