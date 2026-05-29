from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from KGTS.core.graph_service import GraphService
from KGTS.core.seed import _cleanup_legacy_toc_content_edges, _target_graph_needs_seed, ensure_seed_graph


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

    def test_runtime_graph_needs_seed_when_heading_tree_is_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            seed_path = Path(tmp) / "seed.db"
            target_path = Path(tmp) / "target.db"

            seed = GraphService(seed_path)
            target = GraphService(target_path)
            for service in (seed, target):
                service.add_node("TOC root", "part", {"id": "toc::root", "label": "TOC root"})
                service.add_node("Chapter 1", "chapter", {"id": "chapter::chapter1", "label": "Chapter 1"})
                service.add_relation("toc::root", "chapter::chapter1", "contains")
            seed.add_node(
                "Major heading",
                "section",
                {
                    "id": "section::chapter1::major_heading",
                    "label": "Major heading",
                    "chapter": "chapter1",
                    "role": "heading",
                    "heading_depth": 1,
                },
            )
            seed.add_relation("chapter::chapter1", "section::chapter1::major_heading", "contains")
            target.add_node(
                "TOC section",
                "section",
                {
                    "id": "toc::toc_l2_0003",
                    "label": "TOC section",
                    "toc_entry_type": "section",
                },
            )
            target.add_relation("chapter::chapter1", "toc::toc_l2_0003", "contains")

            needs_seed, seed_health, target_health = _target_graph_needs_seed(seed_path, target_path)

            self.assertGreater(seed_health["heading_sections"], 0)
            self.assertEqual(target_health["heading_sections"], 0)
            self.assertTrue(needs_seed)

    def test_cleanup_legacy_toc_content_edges_keeps_structured_heading_tree(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            graph_path = Path(tmp) / "knowledge_graph.db"
            service = GraphService(graph_path)
            service.add_node("Chapter 1", "chapter", {"id": "chapter::chapter1", "label": "Chapter 1"})
            service.add_node(
                "TOC section",
                "section",
                {
                    "id": "toc::toc_l2_0003",
                    "label": "TOC section",
                    "toc_entry_type": "section",
                },
            )
            service.add_node(
                "Major heading",
                "section",
                {
                    "id": "section::chapter1::major_heading",
                    "label": "Major heading",
                    "chapter": "chapter1",
                    "role": "heading",
                },
            )
            service.add_node("Body text", "discussion", {"id": "block::chapter1_002::1", "label": "Body text"})
            service.add_relation("chapter::chapter1", "toc::toc_l2_0003", "contains")
            service.add_relation("chapter::chapter1", "section::chapter1::major_heading", "contains")
            service.add_relation("toc::toc_l2_0003", "block::chapter1_002::1", "contains")
            service.add_relation("section::chapter1::major_heading", "block::chapter1_002::1", "contains")

            cleanup = _cleanup_legacy_toc_content_edges(graph_path)
            graph = GraphService(graph_path).read_graph()
            relation_keys = {
                (relation["source_id"], relation["relation_type"], relation["target_id"])
                for relation in graph["relations"]
            }

            self.assertEqual(cleanup["toc_block_edges_deleted"], 1)
            self.assertEqual(cleanup["chapter_toc_section_edges_deleted"], 1)
            self.assertNotIn(("toc::toc_l2_0003", "contains", "block::chapter1_002::1"), relation_keys)
            self.assertNotIn(("chapter::chapter1", "contains", "toc::toc_l2_0003"), relation_keys)
            self.assertIn(("chapter::chapter1", "contains", "section::chapter1::major_heading"), relation_keys)
            self.assertIn(("section::chapter1::major_heading", "contains", "block::chapter1_002::1"), relation_keys)


if __name__ == "__main__":
    unittest.main()
