from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from KGTS.core.graph_service import GraphService


def _service(tmp_path: Path, mode: str = "graph_db") -> GraphService:
    return GraphService(tmp_path / "graph.db")


def _seed_graph(service: GraphService) -> tuple[str, str]:
    a = service.add_node(
        "Matrix multiplication combines rows and columns.",
        "concept",
        {"label": "Matrix multiplication", "id": "matrix"},
    )
    b = service.add_node(
        "Eigenvalues describe linear transformations.",
        "concept",
        {"label": "Eigenvalue", "id": "eigenvalue"},
    )
    service.add_relation(a["id"], b["id"], "related", {"description": "linear algebra relation"})
    return a["id"], b["id"]


class FakeVectorIndex:
    def __init__(self):
        self.last_error = None
        self.ensure_calls = 0
        self.rebuild_calls = 0

    def ensure_index(self, nodes):
        self.ensure_calls += 1
        self.nodes = list(nodes)
        return self.get_stats()

    def search(self, query, top_k=10, node_type=None):
        return [
            {
                "node_id": "eigenvalue",
                "similarity": 0.9,
                "vector_score": 0.9,
                "metadata": {"label": "Eigenvalue", "type": "concept", "content": "Eigenvalues"},
            },
            {
                "node_id": "matrix",
                "similarity": 0.6,
                "vector_score": 0.6,
                "metadata": {"label": "Matrix multiplication", "type": "concept", "content": "Matrix"},
            },
        ]

    def rebuild(self, nodes):
        self.rebuild_calls += 1
        self.nodes = list(nodes)
        return self.get_stats()

    def reset(self):
        return self.get_stats()

    def get_stats(self):
        return {
            "enabled": True,
            "mode": "hybrid",
            "index_size": len(getattr(self, "nodes", [])),
            "embedding_dimension": 3,
            "model": "fake",
            "index_path": "fake",
            "last_error": self.last_error,
        }


class BrokenVectorIndex(FakeVectorIndex):
    def ensure_index(self, nodes):
        raise RuntimeError("boom")


class GraphHybridRetrievalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self.tmp.name)
        self.env_patch = patch.dict(
            os.environ,
            {
                "KGTS_RETRIEVAL_MODE": "graph_db",
                "KGTS_VECTOR_INDEX_DIR": str(self.tmp_path / "vectors"),
            },
        )
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp.cleanup()

    def test_default_semantic_search_uses_graph_db_mode(self):
        service = _service(self.tmp_path)
        matrix_id, _ = _seed_graph(service)

        results = service.semantic_search("matrix", top_k=3)
        stats = service.get_graph_statistics()["vector_stats"]

        self.assertTrue(results)
        self.assertEqual(results[0]["node_id"], matrix_id)
        self.assertNotIn("hybrid_score", results[0])
        self.assertEqual(stats["mode"], "graph-db")
        self.assertFalse(stats["enabled"])

    def test_hybrid_search_combines_vector_text_and_graph_scores(self):
        with patch.dict(os.environ, {"KGTS_RETRIEVAL_MODE": "hybrid"}):
            service = _service(self.tmp_path)
        service.vector_index = FakeVectorIndex()
        _seed_graph(service)

        results = service.semantic_search("matrix", top_k=2)

        by_id = {result["node_id"]: result for result in results}
        self.assertEqual(set(by_id), {"eigenvalue", "matrix"})
        self.assertEqual(by_id["eigenvalue"]["retrieval_source"], "hybrid")
        self.assertEqual(by_id["eigenvalue"]["vector_score"], 0.9)
        self.assertIn("text_score", by_id["eigenvalue"])
        self.assertIn("graph_score", by_id["eigenvalue"])

    def test_sparse_hybrid_search_uses_standard_library_scores(self):
        with patch.dict(os.environ, {"KGTS_RETRIEVAL_MODE": "sparse_hybrid"}):
            service = _service(self.tmp_path)
        _seed_graph(service)

        results = service.semantic_search("matrix multiplication", top_k=2)
        stats = service.get_graph_statistics()["vector_stats"]

        self.assertTrue(results)
        self.assertEqual(results[0]["retrieval_source"], "sparse_hybrid")
        self.assertIn("sparse_score", results[0])
        self.assertIn("graph_score", results[0])
        self.assertEqual(stats["mode"], "sparse_hybrid")
        self.assertEqual(stats["provider"], "standard-library-sparse")

    def test_hybrid_search_falls_back_to_text_search_on_vector_error(self):
        with patch.dict(os.environ, {"KGTS_RETRIEVAL_MODE": "hybrid"}):
            service = _service(self.tmp_path)
        matrix_id, _ = _seed_graph(service)
        service.vector_index = BrokenVectorIndex()

        results = service.semantic_search("matrix", top_k=3)
        stats = service.get_graph_statistics()["vector_stats"]

        self.assertTrue(results)
        self.assertEqual(results[0]["node_id"], matrix_id)
        self.assertNotIn("hybrid_score", results[0])
        self.assertIn("boom", stats["last_error"])

    def test_rebuild_vector_index_uses_current_graph_nodes(self):
        with patch.dict(os.environ, {"KGTS_RETRIEVAL_MODE": "hybrid"}):
            service = _service(self.tmp_path)
        fake_index = FakeVectorIndex()
        service.vector_index = fake_index
        _seed_graph(service)

        stats = service.rebuild_vector_index()

        self.assertEqual(fake_index.rebuild_calls, 1)
        self.assertEqual(stats["index_size"], 2)

    def test_graph_database_schema_remains_sqlite_source_of_truth(self):
        service = _service(self.tmp_path)
        _seed_graph(service)

        with sqlite3.connect(service.db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }

        self.assertTrue({"nodes", "relationships"}.issubset(tables))


if __name__ == "__main__":
    unittest.main()
