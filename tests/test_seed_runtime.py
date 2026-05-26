from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from KGTS.core.graph_service import GraphService
from KGTS.core.seed import _target_graph_needs_seed, ensure_seed_graph


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

    def test_complete_toc_runtime_graph_does_not_remerge_larger_seed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            seed_path = Path(tmp) / "seed.db"
            target_path = Path(tmp) / "target.db"
            for path in (seed_path, target_path):
                service = GraphService(path)
                service.add_node("TOC root", "section", {"id": "toc::root", "label": "TOC root"})
                for index in range(1, 31):
                    chapter_id = f"chapter::chapter{index}"
                    section_id = f"toc::chapter{index}::section1"
                    service.add_node(f"Chapter {index}", "chapter", {"id": chapter_id, "label": f"Chapter {index}"})
                    service.add_node(
                        f"Section {index}",
                        "section",
                        {
                            "id": section_id,
                            "label": f"Section {index}",
                            "heading_level": 1,
                        },
                    )
                    service.add_relation(chapter_id, section_id, "contains")

            with sqlite3.connect(str(seed_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO nodes (id, label, type, content, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        "section::seed_extra",
                        "Seed extra",
                        "section",
                        "Seed extra",
                        json.dumps({"id": "section::seed_extra", "label": "Seed extra"}),
                    ),
                )
                conn.commit()

            needs_seed, seed, target = _target_graph_needs_seed(seed_path, target_path)

            self.assertGreater(seed["nodes"], target["nodes"])
            self.assertEqual(target["toc_root"], 1)
            self.assertEqual(target["chapter_roots"], 30)
            self.assertFalse(needs_seed)


if __name__ == "__main__":
    unittest.main()
