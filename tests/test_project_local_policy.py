from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from KGTS.core.path_policy import PROJECT_ROOT
from KGTS.core.tts_service import DEFAULT_GPT_SOVITS_ROOT, get_tts_status
from KGTS.core.vector_index_service import GraphVectorIndex


class FakeNumpyArray:
    ndim = 2
    shape = (1, 3)

    def __eq__(self, other):
        return self

    def __setitem__(self, key, value):
        pass

    def reshape(self, *args):
        return self

    def __truediv__(self, other):
        return self


class FakeNumpy:
    float32 = "float32"

    def zeros(self, shape, dtype=None):
        return FakeNumpyArray()

    def empty(self, shape, dtype=None):
        return FakeNumpyArray()

    def asarray(self, value, dtype=None):
        return value

    class linalg:
        @staticmethod
        def norm(value, axis=None, keepdims=False):
            return FakeNumpyArray()


class FakeSentenceTransformer:
    def __init__(self, *args, **kwargs):
        pass

    def encode(self, texts, convert_to_numpy=True, show_progress_bar=False):
        return FakeNumpyArray()


class FakeFaissIndex:
    d = 3
    metric_type = 0
    ntotal = 1

    def search(self, query_embedding, limit):
        return [[0.7]], [[0]]


class FakeFaiss:
    def __init__(self):
        self.read_calls = 0
        self.read_index_result = FakeFaissIndex()

    def read_index(self, path):
        self.read_calls += 1
        return self.read_index_result


class ProjectLocalPolicyTest(unittest.TestCase):
    def test_default_gpt_sovits_root_is_project_local(self):
        self.assertTrue(str(DEFAULT_GPT_SOVITS_ROOT).startswith(str(PROJECT_ROOT)))
        self.assertNotIn("D:\\download", str(DEFAULT_GPT_SOVITS_ROOT))

    def test_tts_status_reports_outside_project_path(self):
        with patch.dict(
            os.environ,
            {
                "KGTS_PROJECT_LOCAL_ONLY": "1",
                "KGTS_ALLOW_EXTERNAL_PATHS": "0",
                "KGTS_TTS_ENABLED": "1",
                "KGTS_TTS_PROVIDER": "genie",
                "KGTS_TTS_MODEL_DIR": r"D:\outside\shu",
            },
            clear=False,
        ):
            status = get_tts_status()

        self.assertFalse(status["available"])
        self.assertEqual(status["path_policy"], "project_local")
        self.assertTrue(status["outside_project_paths"])
        self.assertIn("outside project root", status["detail"])

    def test_vector_index_uses_project_local_cache_by_default(self):
        with patch.dict(
            os.environ,
            {
                "KGTS_PROJECT_LOCAL_ONLY": "1",
                "KGTS_ALLOW_EXTERNAL_PATHS": "0",
                "KGTS_VECTOR_INDEX_DIR": ".runtime/test-vector-policy",
                "KGTS_EMBEDDING_CACHE_DIR": ".runtime/huggingface",
            },
            clear=False,
        ):
            index = GraphVectorIndex()
            stats = index.get_stats()

        self.assertEqual(stats["path_policy"], "project_local")
        self.assertTrue(stats["embedding_cache_path"].startswith(str(PROJECT_ROOT)))
        self.assertEqual(stats["outside_project_paths"], [])

    def test_vector_index_model_load_failure_can_use_hashing_fallback(self):
        class BrokenSentenceTransformer:
            def __init__(self, *args, **kwargs):
                raise AttributeError("'NoneType' object has no attribute 'endswith'")

        with (
            patch.dict(
                os.environ,
                {
                    "KGTS_PROJECT_LOCAL_ONLY": "1",
                    "KGTS_ALLOW_EXTERNAL_PATHS": "0",
                    "KGTS_VECTOR_INDEX_DIR": ".runtime/test-vector-policy",
                    "KGTS_EMBEDDING_CACHE_DIR": ".runtime/huggingface",
                    "KGTS_VECTOR_HASH_FALLBACK": "1",
                },
                clear=False,
            ),
            patch("KGTS.core.vector_index_service._load_vector_dependencies", return_value=(object(), object(), BrokenSentenceTransformer)),
        ):
            index = GraphVectorIndex()
            index._ensure_dependencies()

        self.assertEqual(index._provider, "hashing-fallback")
        self.assertIn("embedding model load failed", index.last_error or "")

    def test_existing_vector_index_probe_does_not_load_embedding_model(self):
        fake_faiss = FakeFaiss()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            index_dir = Path(tmp)
            (index_dir / "vector_index.faiss").write_bytes(b"fake")
            (index_dir / "metadata.json").write_text(
                """
                {
                  "model_name": "fake-model",
                  "format": "kgts-vector-v1",
                  "metric_type": 0,
                  "entries": [
                    {
                      "node_id": "node-1",
                      "label": "Node 1",
                      "type": "concept",
                      "content": "content",
                      "content_hash": "hash",
                      "updated_at": 1
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            with (
                patch.dict(
                    os.environ,
                    {
                        "KGTS_VECTOR_INDEX_DIR": str(index_dir),
                        "KGTS_EMBEDDING_MODEL": "fake-model",
                        "KGTS_ALLOW_EXTERNAL_PATHS": "1",
                    },
                    clear=False,
                ),
                patch("KGTS.core.vector_index_service._load_faiss", return_value=fake_faiss),
                patch("KGTS.core.vector_index_service._load_vector_dependencies") as load_vector_dependencies,
            ):
                index = GraphVectorIndex()
                stats = index.get_stats()

        self.assertEqual(stats["index_size"], 1)
        self.assertFalse(stats["model_loaded"])
        self.assertEqual(fake_faiss.read_calls, 1)
        load_vector_dependencies.assert_not_called()

    def test_vector_query_can_unload_embedding_model_after_search(self):
        fake_faiss = FakeFaiss()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            index_dir = Path(tmp)
            (index_dir / "vector_index.faiss").write_bytes(b"fake")
            (index_dir / "metadata.json").write_text(
                """
                {
                  "model_name": "fake-model",
                  "format": "kgts-vector-v1",
                  "metric_type": 0,
                  "entries": [
                    {
                      "node_id": "node-1",
                      "label": "Node 1",
                      "type": "concept",
                      "content": "content",
                      "content_hash": "hash",
                      "updated_at": 1
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            with (
                patch.dict(
                    os.environ,
                    {
                        "KGTS_VECTOR_INDEX_DIR": str(index_dir),
                        "KGTS_EMBEDDING_MODEL": "fake-model",
                        "KGTS_VECTOR_UNLOAD_AFTER_QUERY": "1",
                        "KGTS_ALLOW_EXTERNAL_PATHS": "1",
                    },
                    clear=False,
                ),
                patch("KGTS.core.vector_index_service._load_faiss", return_value=fake_faiss),
                patch(
                    "KGTS.core.vector_index_service._load_vector_dependencies",
                    return_value=(fake_faiss, FakeNumpy(), FakeSentenceTransformer),
                ),
            ):
                index = GraphVectorIndex()
                results = index.search("content", top_k=1)
                stats = index.get_stats()

        self.assertEqual(results[0]["node_id"], "node-1")
        self.assertFalse(stats["model_loaded"])
        self.assertTrue(stats["unload_after_query"])


if __name__ == "__main__":
    unittest.main()
