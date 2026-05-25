from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from KGTS.core.path_policy import PROJECT_ROOT
from KGTS.core.tts_service import DEFAULT_GPT_SOVITS_ROOT, get_tts_status
from KGTS.core.vector_index_service import GraphVectorIndex


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


if __name__ == "__main__":
    unittest.main()
