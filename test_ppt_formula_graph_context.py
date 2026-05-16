from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from KGTS.education.kg_constraints import (
    formula_context_for_text,
    graph_paths_for_evidence,
)
from KGTS.education.router import _build_ppt_learning_plan


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
        self.assertEqual(p_symbol["unit_id"], "chapter6_007")
        self.assertIn("scope", p_symbol["meaning"])


if __name__ == "__main__":
    unittest.main()
