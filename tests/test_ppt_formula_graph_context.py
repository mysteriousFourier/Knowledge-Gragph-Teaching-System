from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from KGTS.education.kg_constraints import (
    check_generation_consistency,
    formula_context_for_text,
    graph_paths_for_evidence,
)
from KGTS.education.router import _build_ppt_learning_plan
from KGTS.core.graph_context import build_graphrag_context


class PptFormulaGraphContextTest(unittest.TestCase):
    def test_ppt_learning_plan_keeps_slide_content_and_matching_graph_evidence(self):
        graph = {
            "nodes": [
                {
                    "id": "price",
                    "label": "Price equation",
                    "type": "formula",
                    "content": "Price's theorem uses covariance between fitness and trait value.",
                },
                {
                    "id": "fisher",
                    "label": "Fisher theorem",
                    "type": "theorem",
                    "content": "Fisher's theorem connects response in mean fitness and additive variance.",
                },
            ],
            "relations": [
                {
                    "id": "r1",
                    "source_id": "price",
                    "target_id": "fisher",
                    "relation_type": "derives",
                    "description": "Price equation motivates Fisher theorem.",
                }
            ],
        }

        plan = _build_ppt_learning_plan(
            chapter_title="Fisher theorem",
            chapter_content="This slide explains the Price equation and Fisher theorem.",
            graph_data=graph,
        )

        evidence_ids = {item["id"] for item in plan["evidence"]}
        self.assertTrue(any(str(item).startswith("ppt_slide::") for item in evidence_ids))
        self.assertIn("price", evidence_ids)
        self.assertIn("fisher", evidence_ids)
        self.assertEqual(plan["learning_intent_graph"]["edges"][0]["type"], "derives")

    def test_graphrag_context_uses_scoped_vector_hits_and_graph_expansion(self):
        graph = {
            "nodes": [
                {"id": "root", "label": "Root", "type": "chapter", "content": "Root"},
                {"id": "formula", "label": "Equation 6.18g", "type": "formula", "content": "Equation 6.18g"},
                {"id": "outside", "label": "Outside", "type": "concept", "content": "Outside keyword"},
            ],
            "relations": [
                {"source_id": "root", "target_id": "formula", "relation_type": "contains"},
            ],
            "vector_stats": {"mode": "hybrid", "model": "fake", "index_size": 3},
        }

        def fake_semantic_search(query, node_type=None, top_k=10, allowed_node_ids=None):
            self.assertIn("formula", allowed_node_ids)
            self.assertNotIn("outside", allowed_node_ids)
            return [
                {
                    "node_id": "formula",
                    "similarity": 0.9,
                    "retrieval_source": "hybrid",
                    "metadata": {"label": "Equation 6.18g", "type": "formula", "content": "Equation 6.18g"},
                }
            ]

        import KGTS.core.graph_context as graph_context

        old_build = graph_context.build_frontend_graph
        old_semantic = graph_context.semantic_search
        old_search = graph_context.search_nodes
        try:
            graph_context.build_frontend_graph = lambda raw_graph=None: graph
            graph_context.semantic_search = fake_semantic_search
            graph_context.search_nodes = lambda query, node_type=None, limit=20: []

            context = build_graphrag_context("Equation 6.18g", seed_node_ids=["root"], limit=4)
        finally:
            graph_context.build_frontend_graph = old_build
            graph_context.semantic_search = old_semantic
            graph_context.search_nodes = old_search

        self.assertEqual(context["retrieval_mode"], "hybrid")
        self.assertEqual(context["scope_mode"], "subtree")
        self.assertEqual(context["vector_hits"][0]["node_id"], "formula")
        self.assertTrue(any(node["id"] == "formula" for node in context["expanded_nodes"]))

    def test_ppt_learning_plan_prioritizes_selected_graph_subtree(self):
        graph = {
            "nodes": [
                {
                    "id": "selected_root",
                    "label": "Selected chapter",
                    "type": "chapter",
                    "content": "Selected subtree explains the chapter teaching scope.",
                },
                {
                    "id": "selected_formula",
                    "label": "Selected formula",
                    "type": "formula",
                    "content": "Selected formula evidence should guide the PPT lecture.",
                },
                {
                    "id": "outside",
                    "label": "Outside match",
                    "type": "concept",
                    "content": "PPT slide keyword appears here but this is outside the selected subtree.",
                },
            ],
            "relations": [
                {
                    "source_id": "selected_root",
                    "target_id": "selected_formula",
                    "relation_type": "contains",
                }
            ],
        }
        selected_evidence = [
            {
                "id": "selected_root",
                "label": "Selected chapter",
                "type": "chapter",
                "content": "Selected subtree explains the chapter teaching scope.",
                "source": "selected_graph_subtree",
            },
            {
                "id": "selected_formula",
                "label": "Selected formula",
                "type": "formula",
                "content": "Selected formula evidence should guide the PPT lecture.",
                "source": "selected_graph_subtree",
            },
        ]

        plan = _build_ppt_learning_plan(
            chapter_title="PPT keyword",
            chapter_content="This slide mentions PPT keyword and should augment the selected subtree.",
            graph_data=graph,
            selected_evidence=selected_evidence,
        )

        evidence = plan["evidence"]
        self.assertEqual(evidence[0]["id"], "selected_root")
        self.assertEqual(evidence[1]["id"], "selected_formula")
        self.assertEqual(evidence[0]["source"], "selected_graph_subtree")
        self.assertTrue(any(str(item["id"]).startswith("ppt_slide::") for item in evidence))

    def test_graph_paths_for_evidence_returns_relation_path_labels(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "type": "concept", "content": "A"},
                {"id": "b", "label": "B", "type": "concept", "content": "B"},
            ],
            "relations": [{"source_id": "a", "target_id": "b", "relation_type": "depends_on"}],
        }

        paths = graph_paths_for_evidence(graph, [{"id": "a"}, {"id": "b"}])

        self.assertEqual(paths[0]["source_label"], "A")
        self.assertEqual(paths[0]["target_label"], "B")
        self.assertEqual(paths[0]["type"], "depends_on")

    def test_formula_context_infers_derivation_and_scoped_symbols(self):
        formulas = formula_context_for_text("Equation 6.18g", limit=1)

        self.assertEqual(formulas[0]["id"], "6.18g")
        self.assertIn("6.18c", formulas[0]["derives_from"])
        self.assertIn("6.18f", formulas[0]["derives_from"])
        self.assertTrue(any(symbol["symbol"] == "p" for symbol in formulas[0]["symbols"]))
        p_symbol = next(symbol for symbol in formulas[0]["symbols"] if symbol["symbol"] == "p")
        self.assertEqual(p_symbol["unit_id"], "chapter6_block_063")
        self.assertIn("scope", p_symbol["meaning"])

    def test_lecture_consistency_ignores_plain_chinese_phrases_as_entities(self):
        plan = {
            "subject": {"id": "main", "name": "Price equation", "type": "formula"},
            "slots": [{"entities": [{"id": "main", "name": "Price equation"}]}],
            "allowed_concepts": [
                {"id": "main", "name": "Price equation", "type": "formula"},
                {"id": "support", "name": "Fisher theorem", "type": "theorem"},
                {"id": "long_note", "name": "这个中文段落只是普通讲解语句，不应该被当作必须逐字覆盖的实体", "type": "note"},
            ],
            "evidence": [{"id": "main"}, {"id": "support"}, {"id": "long_note"}],
        }

        report = check_generation_consistency(
            "本节先用直观方式讲 Price equation，再通过课堂提问说明选择响应。",
            plan,
            task="lecture",
        )

        self.assertEqual(report["missing_entities"], [])
        self.assertEqual(report["unsupported_entities"], [])
        self.assertEqual(report["entity_hallucination_rate"], 0.0)
        self.assertEqual(report["knowledge_support_ratio"], 1.0)

    def test_lecture_support_ratio_uses_core_entities_not_all_evidence(self):
        plan = {
            "subject": {"id": "core", "name": "Price equation", "type": "formula"},
            "slots": [{"entities": [{"id": "core", "name": "Price equation"}]}],
            "allowed_concepts": [
                {"id": "core", "name": "Price equation", "type": "formula"},
                *[
                    {"id": f"context_{index}", "name": f"Context node {index}", "type": "concept"}
                    for index in range(20)
                ],
            ],
            "evidence": [{"id": "core"}, *[{"id": f"context_{index}"} for index in range(20)]],
        }

        report = check_generation_consistency(
            "Price equation is the anchor for this lesson; other graph nodes are used only as context.",
            plan,
            task="lecture",
        )

        self.assertEqual(report["entity_recall"], 1.0)
        self.assertEqual(report["knowledge_support_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
