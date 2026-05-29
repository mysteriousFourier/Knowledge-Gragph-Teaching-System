from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from KGTS.maintenance import sync_builders
from KGTS.maintenance import sync_core
from KGTS.maintenance.book_outline import APPENDICES_PART_ID
from KGTS.maintenance.toc_fusion import build_structured_units, fuse_toc_with_structured_units
from KGTS.maintenance.sync_utils import SourceSpec, _slug_heading


class StructuredTocSyncTest(unittest.TestCase):
    def test_collect_specs_detects_nested_delivery_structured_directory(self):
        chunk_payload = {
            "id": "chapter1_001",
            "metadata": {
                "chapter": "chapter1",
                "section": "Chapter 1 Intro",
                "heading_path": ["Chapter 1 Intro"],
            },
            "blocks": [{"type": "discussion", "content": "Nested delivery content."}],
        }
        formula_payload = {
            "formulas": [
                {
                    "id": "1.1",
                    "label_format": "(1.1)",
                    "latex": "x = y",
                    "source": {"chapter": "chapter1", "unit_id": "chapter1_001", "subsection": "Chapter 1 Intro"},
                }
            ]
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            package_root = Path(tmp) / "structured"
            nested_dir = package_root / "structured"
            nested_dir.mkdir(parents=True)
            (nested_dir / "chapter1_001.json").write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")
            (nested_dir / "formula_library.json").write_text(json.dumps(formula_payload, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", package_root),
                patch.object(sync_builders, "TOC_EXPORT_DIR", Path("")),
            ):
                specs, chapters = sync_builders._collect_specs(skip_semantic=True)

        node_by_id = {node["id"]: node for spec in specs for node in spec.nodes}
        self.assertIn("chapter1", chapters)
        self.assertIn("block::chapter1_001::1", node_by_id)
        self.assertIn("formula::chapter1::1.1", node_by_id)

    def test_toc_exports_are_not_auto_discovered_by_default(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (export_dir / "1目录_toc_tree.json").write_text(
                json.dumps({"nodes": {}}, ensure_ascii=False),
                encoding="utf-8",
            )

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", Path("")),
            ):
                self.assertEqual(sync_builders._toc_export_files(), [])

    def test_toc_exports_default_to_structured_package_outline(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            package_root = root / "structured"
            structured_dir = package_root / "structured"
            export_dir = package_root / "目录树导出"
            structured_dir.mkdir(parents=True)
            export_dir.mkdir()
            toc_path = export_dir / "1目录_toc_tree.json"
            toc_path.write_text(
                json.dumps({"nodes": {}, "root_nodes": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", package_root),
                patch.object(sync_builders, "TOC_EXPORT_DIR", Path("")),
            ):
                self.assertEqual(sync_builders._toc_export_files(), [toc_path])

    def test_build_toc_source_preserves_export_tree(self):
        payload = {
            "metadata": {
                "source_title": "Test Book",
                "source_file": "data/paddle_output/toc/main.tex",
                "total_nodes": 3,
                "root_count": 1,
                "navigation_units": 1,
            },
            "root_nodes": ["toc_l0_0001"],
            "nodes": {
                "toc_l0_0001": {
                    "id": "toc_l0_0001",
                    "title": "I. INTRODUCTION",
                    "level": 0,
                    "entry_type": "part",
                    "page": 1,
                    "parent_id": None,
                    "children": ["toc_l1_0002"],
                    "unit_id": "1目录_nav_001",
                },
                "toc_l1_0002": {
                    "id": "toc_l1_0002",
                    "title": "1. CHANGES IN QUANTITATIVE TRAITS OVER TIME",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 3,
                    "parent_id": "toc_l0_0001",
                    "children": ["toc_l2_0003"],
                    "unit_id": "1目录_nav_002",
                },
                "toc_l2_0003": {
                    "id": "toc_l2_0003",
                    "title": "A Brief History",
                    "level": 2,
                    "entry_type": "section",
                    "page": 4,
                    "parent_id": "toc_l1_0002",
                    "children": [],
                    "unit_id": None,
                },
            },
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "1目录_toc_tree.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            spec = sync_builders._build_toc_source(path)

        node_by_id = {node["id"]: node for node in spec.nodes}
        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for relation in spec.relations
        }

        self.assertEqual(spec.source_key, "toc::1目录_toc_tree.json")
        self.assertIn(sync_builders.TOC_ROOT_NODE_ID, node_by_id)
        self.assertEqual(node_by_id["toc::toc_l0_0001"]["type"], "part")
        self.assertEqual(node_by_id["toc::toc_l1_0002"]["type"], "section")
        self.assertEqual(node_by_id["toc::toc_l1_0002"]["metadata"]["toc_entry_type"], "chapter")
        self.assertEqual(node_by_id["toc::toc_l1_0002"]["metadata"]["toc_page"], 3)
        self.assertEqual(
            node_by_id["toc::toc_l2_0003"]["metadata"]["toc_path"],
            [
                "I. INTRODUCTION",
                "1. CHANGES IN QUANTITATIVE TRAITS OVER TIME",
                "A Brief History",
            ],
        )
        self.assertIn((sync_builders.TOC_ROOT_NODE_ID, "contains", "toc::toc_l0_0001"), relation_keys)
        self.assertIn(("toc::toc_l0_0001", "contains", "toc::toc_l1_0002"), relation_keys)
        self.assertEqual(spec.chapters, {})

    def test_canonical_chapter_keeps_structured_headings_with_exported_toc_sections(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book", "total_nodes": 4, "root_count": 1},
            "root_nodes": ["toc_l0_0001"],
            "nodes": {
                "toc_l0_0001": {
                    "id": "toc_l0_0001",
                    "title": "II. EVOLUTION AT ONE AND TWO LOCI",
                    "level": 0,
                    "entry_type": "part",
                    "page": 1,
                    "parent_id": None,
                    "children": ["toc_l1_0002"],
                },
                "toc_l1_0002": {
                    "id": "toc_l1_0002",
                    "title": "2. NEUTRAL EVOLUTION IN ONE- AND TWO-LOCUS SYSTEMS",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 5,
                    "parent_id": "toc_l0_0001",
                    "children": ["toc_l2_0003", "toc_l2_0004"],
                },
                "toc_l2_0003": {
                    "id": "toc_l2_0003",
                    "title": "The Wright-Fisher Model",
                    "level": 2,
                    "entry_type": "section",
                    "page": 6,
                    "parent_id": "toc_l1_0002",
                    "children": [],
                },
                "toc_l2_0004": {
                    "id": "toc_l2_0004",
                    "title": "Loss of Heterozygosity by Random Genetic Drift",
                    "level": 2,
                    "entry_type": "section",
                    "page": 8,
                    "parent_id": "toc_l1_0002",
                    "children": [],
                },
            },
        }
        chunk_payload = {
            "id": "chapter2_002",
            "metadata": {
                "chapter": "chapter2",
                "section": "Neutral Evolution in One- and Two-Locus Systems: Introduction",
                "heading_path": [
                    "Neutral Evolution in One- and Two-Locus Systems: Introduction",
                    "THE WRIGHT-FISHER MODEL",
                ],
            },
            "blocks": [{"type": "discussion", "content": "Structured content."}],
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (export_dir / "1目录_toc_tree.json").write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            (structured_dir / "chapter2_002.json").write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }
        structured_section_id = (
            "section::chapter2::"
            "neutral_evolution_in_one_and_two_locus_systems_introduction__the_wright_fisher_model"
        )
        self.assertIn(("toc::toc_l1_0002", "contains", "chapter::chapter2"), relation_keys)
        self.assertIn(("toc::toc_l1_0002", "contains", "toc::toc_l2_0003"), relation_keys)
        self.assertIn(("toc::toc_l1_0002", "contains", "toc::toc_l2_0004"), relation_keys)
        self.assertNotIn(("chapter::chapter2", "contains", "toc::toc_l2_0003"), relation_keys)
        self.assertNotIn(("chapter::chapter2", "contains", "toc::toc_l2_0004"), relation_keys)
        self.assertIn(
            (
                "chapter::chapter2",
                "contains",
                "section::chapter2::neutral_evolution_in_one_and_two_locus_systems_introduction",
            ),
            relation_keys,
        )
        self.assertIn(
            ("toc::toc_l2_0003", "contains", structured_section_id),
            relation_keys,
        )
        self.assertIn((structured_section_id, "contains", "block::chapter2_002::1"), relation_keys)
        self.assertNotIn(("toc::toc_l2_0003", "contains", "block::chapter2_002::1"), relation_keys)

    def test_toc_mapped_structured_chapter_keeps_canonical_chapter_container(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book", "total_nodes": 1, "root_count": 1},
            "root_nodes": ["toc_l0_0001"],
            "nodes": {
                "toc_l0_0001": {
                    "id": "toc_l0_0001",
                    "title": "I. INTRODUCTION",
                    "level": 0,
                    "entry_type": "part",
                    "page": 1,
                    "parent_id": None,
                    "children": ["toc_l1_0002"],
                },
                "toc_l1_0002": {
                    "id": "toc_l1_0002",
                    "title": "1. CHANGES IN QUANTITATIVE TRAITS OVER TIME",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 3,
                    "parent_id": "toc_l0_0001",
                    "children": [],
                },
            },
        }
        chunk_payload = {
            "id": "chapter1_001",
            "metadata": {
                "chapter": "chapter1",
                "section": "CHANGES IN QUANTITATIVE TRAITS OVER TIME",
                "heading_path": ["CHANGES IN QUANTITATIVE TRAITS OVER TIME", "A Brief History"],
            },
            "blocks": [{"type": "discussion", "content": "Structured content."}],
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            toc_path = export_dir / "1目录_toc_tree.json"
            chunk_path = structured_dir / "chapter1_001.json"
            toc_path.write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            chunk_path.write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        node_ids = {node["id"] for spec in specs for node in spec.nodes}
        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }

        self.assertIn("chapter::chapter1", node_ids)
        self.assertIn("section::chapter1::changes_in_quantitative_traits_over_time", node_ids)
        self.assertIn(("toc::root", "contains", "toc::toc_l0_0001"), relation_keys)
        self.assertIn(("toc::toc_l0_0001", "contains", "toc::toc_l1_0002"), relation_keys)
        self.assertIn(("toc::toc_l1_0002", "contains", "chapter::chapter1"), relation_keys)
        self.assertIn(
            ("chapter::chapter1", "contains", "section::chapter1::changes_in_quantitative_traits_over_time"),
            relation_keys,
        )
        self.assertIn(
            (
                "section::chapter1::changes_in_quantitative_traits_over_time__a_brief_history",
                "contains",
                "block::chapter1_001::1",
            ),
            relation_keys,
        )
        self.assertNotIn(("toc::toc_l1_0002", "contains", "block::chapter1_001::1"), relation_keys)

    def test_toc_mapped_chunk_uses_descendant_section_when_confident(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book", "total_nodes": 3, "root_count": 1},
            "root_nodes": ["toc_l0_0001"],
            "nodes": {
                "toc_l0_0001": {
                    "id": "toc_l0_0001",
                    "title": "I. INTRODUCTION",
                    "level": 0,
                    "entry_type": "part",
                    "page": 1,
                    "parent_id": None,
                    "children": ["toc_l1_0002"],
                },
                "toc_l1_0002": {
                    "id": "toc_l1_0002",
                    "title": "1. CHANGES IN QUANTITATIVE TRAITS OVER TIME",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 3,
                    "parent_id": "toc_l0_0001",
                    "children": ["toc_l2_0003"],
                },
                "toc_l2_0003": {
                    "id": "toc_l2_0003",
                    "title": "A Brief History",
                    "level": 2,
                    "entry_type": "section",
                    "page": 4,
                    "parent_id": "toc_l1_0002",
                    "children": [],
                },
            },
        }
        chunk_payload = {
            "id": "chapter1_002",
            "metadata": {
                "chapter": "chapter1",
                "section": "A Brief History",
                "heading_path": ["A Brief History"],
            },
            "blocks": [{"type": "discussion", "content": "Structured content."}],
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (export_dir / "1目录_toc_tree.json").write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            (structured_dir / "chapter1_002.json").write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }
        node_ids = {node["id"] for spec in specs for node in spec.nodes}
        self.assertIn("chapter::chapter1", node_ids)
        self.assertIn(("toc::root", "contains", "toc::toc_l0_0001"), relation_keys)
        self.assertIn(("toc::toc_l0_0001", "contains", "toc::toc_l1_0002"), relation_keys)
        self.assertIn(("toc::toc_l0_0001", "contains", "chapter::chapter1"), relation_keys)
        self.assertIn(("chapter::chapter1", "contains", "section::chapter1::a_brief_history"), relation_keys)
        self.assertIn(("section::chapter1::a_brief_history", "contains", "block::chapter1_002::1"), relation_keys)
        self.assertNotIn(("toc::toc_l2_0003", "contains", "block::chapter1_002::1"), relation_keys)

    def test_library_resources_attach_to_structured_sections(self):
        chunk_payload = {
            "id": "chapter2_002",
            "metadata": {
                "chapter": "chapter2",
                "section": "Neutral Evolution in One- and Two-Locus Systems: Introduction",
                "heading_path": [
                    "Neutral Evolution in One- and Two-Locus Systems: Introduction",
                    "THE WRIGHT-FISHER MODEL",
                ],
            },
            "blocks": [{"type": "discussion", "content": "Structured content."}],
        }
        formula_payload = {
            "formulas": [
                {
                    "id": "2.1",
                    "label_format": "(2.1)",
                    "latex": "P_{ij}",
                    "source": {"chapter": "chapter2", "unit_id": "chapter2_block_008", "subsection": "THE WRIGHT-FISHER MODEL"},
                }
            ]
        }
        table_payload = {
            "tables": [
                {
                    "id": "inline_1",
                    "label_format": "Table inline_1",
                    "rows": [["x"]],
                    "source": {"chapter": "chapter2", "unit_id": "chapter2_002", "subsection": "THE WRIGHT-FISHER MODEL"},
                }
            ]
        }
        example_payload = {
            "examples": [
                {
                    "example_id": "2.1",
                    "chapter": "chapter2",
                    "label": "Example 2.1",
                    "source_file": "chapter2_002.json",
                    "content_plain": "Example content.",
                }
            ]
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            structured_dir = Path(tmp) / "structured"
            structured_dir.mkdir()
            (structured_dir / "chapter2_002.json").write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")
            (structured_dir / "formula_library.json").write_text(json.dumps(formula_payload, ensure_ascii=False), encoding="utf-8")
            (structured_dir / "table_library.json").write_text(json.dumps(table_payload, ensure_ascii=False), encoding="utf-8")
            (structured_dir / "example_library.json").write_text(json.dumps(example_payload, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", Path("")),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }
        section_id = "section::chapter2::neutral_evolution_in_one_and_two_locus_systems_introduction__the_wright_fisher_model"
        self.assertIn((section_id, "contains", "formula::chapter2::2.1"), relation_keys)
        self.assertIn((section_id, "contains", "table::chapter2::inline_1"), relation_keys)
        self.assertIn((section_id, "contains", "example::chapter2::2.1"), relation_keys)
        self.assertNotIn(("chapter::chapter2", "contains", "formula::chapter2::2.1"), relation_keys)

    def test_library_resources_stay_on_structured_sections_with_toc_export(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book", "total_nodes": 2, "root_count": 1},
            "root_nodes": ["toc_l0_0001"],
            "nodes": {
                "toc_l0_0001": {
                    "id": "toc_l0_0001",
                    "title": "II. EVOLUTION AT ONE AND TWO LOCI",
                    "level": 0,
                    "entry_type": "part",
                    "page": 1,
                    "parent_id": None,
                    "children": ["toc_l1_0002"],
                },
                "toc_l1_0002": {
                    "id": "toc_l1_0002",
                    "title": "2. NEUTRAL EVOLUTION IN ONE- AND TWO-LOCUS SYSTEMS",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 5,
                    "parent_id": "toc_l0_0001",
                    "children": [],
                },
            },
        }
        chunk_payload = {
            "id": "chapter2_002",
            "metadata": {
                "chapter": "chapter2",
                "section": "Neutral Evolution in One- and Two-Locus Systems: Introduction",
                "heading_path": [
                    "Neutral Evolution in One- and Two-Locus Systems: Introduction",
                    "THE WRIGHT-FISHER MODEL",
                ],
            },
            "blocks": [{"type": "discussion", "content": "Structured content."}],
        }
        formula_payload = {
            "formulas": [
                {
                    "id": "2.1",
                    "label_format": "(2.1)",
                    "latex": "P_{ij}",
                    "source": {"chapter": "chapter2", "unit_id": "chapter2_block_008", "subsection": "THE WRIGHT-FISHER MODEL"},
                }
            ]
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (structured_dir / "chapter2_002.json").write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")
            (structured_dir / "formula_library.json").write_text(json.dumps(formula_payload, ensure_ascii=False), encoding="utf-8")
            (export_dir / "1目录_toc_tree.json").write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }
        section_id = "section::chapter2::neutral_evolution_in_one_and_two_locus_systems_introduction__the_wright_fisher_model"
        self.assertIn((section_id, "contains", "formula::chapter2::2.1"), relation_keys)
        self.assertNotIn(("chapter::chapter2", "contains", "formula::chapter2::2.1"), relation_keys)

    def test_toc_mapped_chapter26_falls_back_to_canonical_chapter_for_weak_match(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book", "total_nodes": 2, "root_count": 1},
            "root_nodes": ["toc_l0_0001"],
            "nodes": {
                "toc_l0_0001": {
                    "id": "toc_l0_0001",
                    "title": "VI. POPULATION-GENETIC MODELS OF TRAIT RESPONSE",
                    "level": 0,
                    "entry_type": "part",
                    "page": 900,
                    "parent_id": None,
                    "children": ["toc_l1_0648"],
                },
                "toc_l1_0648": {
                    "id": "toc_l1_0648",
                    "title": "2. FINITE POPULATION SIZE AND MUTATION",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 953,
                    "parent_id": "toc_l0_0001",
                    "children": [],
                },
            },
        }
        chunk_payload = {
            "id": "chapter26_001",
            "metadata": {
                "chapter": "chapter26",
                "section": "Long-term Response: Introduction",
                "heading_path": ["Long-term Response: Introduction"],
            },
            "blocks": [{"type": "discussion", "content": "Structured content."}],
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (export_dir / "1目录_toc_tree.json").write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            (structured_dir / "chapter26_001.json").write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }
        self.assertIn(("chapter::chapter26", "contains", "section::chapter26::long_term_response_introduction"), relation_keys)
        self.assertIn(
            ("section::chapter26::long_term_response_introduction", "contains", "block::chapter26_001::1"),
            relation_keys,
        )
        self.assertNotIn(("toc::toc_l1_0648", "contains", "block::chapter26_001::1"), relation_keys)

    def test_canonical_outline_normalizes_part_tree_when_toc_uses_local_chapter_numbers(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book"},
            "root_nodes": ["toc_l0_0320"],
            "nodes": {
                "toc_l0_0320": {
                    "id": "toc_l0_0320",
                    "title": "IV. SHORT-TERM RESPONSE ON A SINGLE CHARACTER",
                    "level": 0,
                    "entry_type": "part",
                    "page": 479,
                    "parent_id": None,
                    "children": ["toc_l1_0321", "toc_l1_0345", "toc_l1_0355"],
                },
                "toc_l1_0321": {
                    "id": "toc_l1_0321",
                    "title": "1. THE BREEDER'S EQUATION",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 481,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
                "toc_l1_0345": {
                    "id": "toc_l1_0345",
                    "title": "2. TRUNCATION AND THRESHOLD SELECTION",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 507,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
                "toc_l1_0355": {
                    "id": "toc_l1_0355",
                    "title": "3. PERMANENT VERSUS TRANSIENT RESPONSE",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 525,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
            },
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (export_dir / "1目录_toc_tree.json").write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            for index in (13, 14, 15):
                chunk_payload = {
                    "id": f"chapter{index}_001",
                    "metadata": {
                        "chapter": f"chapter{index}",
                        "section": f"Chapter {index}",
                        "heading_path": [f"Chapter {index}"],
                    },
                    "blocks": [{"type": "discussion", "content": f"Structured chapter {index} content."}],
                }
                (structured_dir / f"chapter{index}_001.json").write_text(
                    json.dumps(chunk_payload, ensure_ascii=False),
                    encoding="utf-8",
                )

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        node_by_id = {node["id"]: node for spec in specs for node in spec.nodes}
        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }

        self.assertEqual("part", node_by_id["toc::toc_l0_0320"]["type"])
        self.assertEqual(
            "Chapter 13: Short-term Changes in the Mean: 1. The Breeder's Equation",
            node_by_id["chapter::chapter13"]["metadata"]["label"],
        )
        self.assertIn(("toc::root", "contains", "toc::toc_l0_0320"), relation_keys)
        self.assertIn(("toc::toc_l0_0320", "contains", "toc::toc_l1_0321"), relation_keys)
        self.assertIn(("toc::toc_l0_0320", "contains", "toc::toc_l1_0345"), relation_keys)
        self.assertIn(("toc::toc_l0_0320", "contains", "toc::toc_l1_0355"), relation_keys)
        self.assertIn(("toc::toc_l0_0320", "contains", "chapter::chapter13"), relation_keys)
        self.assertIn(("toc::toc_l0_0320", "contains", "chapter::chapter14"), relation_keys)
        self.assertIn(("toc::toc_l0_0320", "contains", "chapter::chapter15"), relation_keys)
        self.assertNotIn(("toc::root", "contains", "chapter::chapter13"), relation_keys)

    def test_structured_chapters_create_thirty_canonical_chapter_nodes_when_toc_has_twenty_five_chapters(self):
        toc_nodes = {
            "toc_l0_0001": {
                "id": "toc_l0_0001",
                "title": "I. PART",
                "level": 0,
                "entry_type": "part",
                "page": 1,
                "parent_id": None,
                "children": [f"toc_l1_{index:04d}" for index in range(1, 26)],
            }
        }
        for index in range(1, 26):
            toc_nodes[f"toc_l1_{index:04d}"] = {
                "id": f"toc_l1_{index:04d}",
                "title": f"{index}. Chapter {index} title",
                "level": 1,
                "entry_type": "chapter",
                "page": index * 10,
                "parent_id": "toc_l0_0001",
                "children": [],
            }
        toc_payload = {
            "metadata": {"source_title": "Test Book"},
            "root_nodes": ["toc_l0_0001"],
            "nodes": toc_nodes,
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (export_dir / "1目录_toc_tree.json").write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            for index in range(1, 31):
                chunk_payload = {
                    "id": f"chapter{index}_001",
                    "metadata": {
                        "chapter": f"chapter{index}",
                        "section": f"Chapter {index} title: Introduction",
                        "heading_path": [f"Chapter {index} title: Introduction"],
                    },
                    "blocks": [{"type": "discussion", "content": f"Structured chapter {index} content."}],
                }
                (structured_dir / f"chapter{index}_001.json").write_text(
                    json.dumps(chunk_payload, ensure_ascii=False),
                    encoding="utf-8",
                )

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, chapters = sync_builders._collect_specs(skip_semantic=True)

        nodes = [node for spec in specs for node in spec.nodes]
        node_by_id = {node["id"]: node for node in nodes}
        canonical_chapters = [
            node for node in nodes
            if node["id"].startswith("chapter::chapter") and node["type"] == "chapter"
        ]
        toc_chapter_entries = [
            node for node in nodes
            if node["id"].startswith("toc::")
            and (node.get("metadata") or {}).get("toc_entry_type") == "chapter"
        ]

        self.assertEqual({f"chapter{i}" for i in range(1, 31)}, set(chapters))
        self.assertEqual(30, len(canonical_chapters))
        for index in range(1, 31):
            self.assertIn(f"chapter::chapter{index}", node_by_id)
        self.assertEqual(25, len(toc_chapter_entries))
        self.assertTrue(all(node["type"] == "section" for node in toc_chapter_entries))
        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }
        self.assertIn(("toc::root", "contains", "part::4"), relation_keys)
        self.assertIn(("part::4", "contains", "chapter::chapter13"), relation_keys)
        self.assertIn(("toc::toc_l1_0019", "contains", "chapter::chapter30"), relation_keys)

    def test_appendix_does_not_count_as_chapter_node(self):
        chunk_payload = {
            "id": "appendix1_001",
            "metadata": {
                "chapter": "appendix1",
                "section": "Appendix material",
                "heading_path": ["Appendix material"],
            },
            "blocks": [{"type": "discussion", "content": "Appendix content."}],
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            structured_dir = Path(tmp) / "structured"
            structured_dir.mkdir()
            (structured_dir / "appendix1_001.json").write_text(json.dumps(chunk_payload, ensure_ascii=False), encoding="utf-8")
            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", Path("")),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        node_by_id = {node["id"]: node for spec in specs for node in spec.nodes}
        self.assertEqual("appendix", node_by_id["chapter::appendix1"]["type"])
        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }
        self.assertIn(("toc::root", "contains", APPENDICES_PART_ID), relation_keys)
        self.assertIn((APPENDICES_PART_ID, "contains", "chapter::appendix1"), relation_keys)
        self.assertEqual(
            [],
            [
                node for node in node_by_id.values()
                if node["type"] == "chapter" and str(node["id"]).startswith("chapter::appendix")
            ],
        )

    def test_local_part_numbering_does_not_override_chapters_13_to_15(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book"},
            "root_nodes": ["toc_l0_0320"],
            "nodes": {
                "toc_l0_0320": {
                    "id": "toc_l0_0320",
                    "title": "IV. SHORT-TERM RESPONSE ON A SINGLE CHARACTER",
                    "level": 0,
                    "entry_type": "part",
                    "page": 479,
                    "parent_id": None,
                    "children": ["toc_l1_0321", "toc_l1_0345", "toc_l1_0355"],
                },
                "toc_l1_0321": {
                    "id": "toc_l1_0321",
                    "title": "1. THE BREEDER'S EQUATION",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 481,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
                "toc_l1_0345": {
                    "id": "toc_l1_0345",
                    "title": "2. TRUNCATION AND THRESHOLD SELECTION",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 507,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
                "toc_l1_0355": {
                    "id": "toc_l1_0355",
                    "title": "3. PERMANENT VERSUS TRANSIENT RESPONSE",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 525,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
            },
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            export_dir = root / "目录树导出"
            structured_dir.mkdir()
            export_dir.mkdir()
            (export_dir / "1目录_toc_tree.json").write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            titles = {
                13: "Short-term Changes in the Mean: 1. The Breeder's Equation: Introduction",
                14: "Short-term Changes in the Mean: 2. Truncation and Threshold Selection",
                15: "Short-term Changes in the Mean: 3. Permanent Versus Transient Response",
            }
            for index, title in titles.items():
                chunk_payload = {
                    "id": f"chapter{index}_001",
                    "metadata": {
                        "chapter": f"chapter{index}",
                        "section": title,
                        "heading_path": [title],
                    },
                    "blocks": [{"type": "discussion", "content": f"Structured chapter {index} content."}],
                }
                (structured_dir / f"chapter{index}_001.json").write_text(
                    json.dumps(chunk_payload, ensure_ascii=False),
                    encoding="utf-8",
                )

            with (
                patch.object(sync_builders, "STRUCTURED_DIR", structured_dir),
                patch.object(sync_builders, "TOC_EXPORT_DIR", export_dir),
            ):
                specs, _ = sync_builders._collect_specs(skip_semantic=True)

        node_by_id = {node["id"]: node for spec in specs for node in spec.nodes}
        relation_keys = {
            (relation["source_id"], relation["relation_type"], relation["target_id"])
            for spec in specs
            for relation in spec.relations
        }

        for index, title in titles.items():
            self.assertEqual("chapter", node_by_id[f"chapter::chapter{index}"]["type"])
            section_id = f"section::chapter{index}::{_slug_heading(title)}"
            expected_parent = {
                13: "toc::toc_l1_0321",
                14: "toc::toc_l1_0345",
                15: "toc::toc_l1_0355",
            }[index]
            self.assertIn((expected_parent, "contains", f"chapter::chapter{index}"), relation_keys)
            self.assertIn((f"chapter::chapter{index}", "contains", section_id), relation_keys)
            self.assertIn((section_id, "contains", f"block::chapter{index}_001::1"), relation_keys)

    def test_toc_fusion_uses_structured_chapter_ids_for_local_part_numbering(self):
        toc_payload = {
            "metadata": {"source_title": "Test Book"},
            "root_nodes": ["toc_l0_0320"],
            "nodes": {
                "toc_l0_0320": {
                    "id": "toc_l0_0320",
                    "title": "IV. SHORT-TERM RESPONSE ON A SINGLE CHARACTER",
                    "level": 0,
                    "entry_type": "part",
                    "page": 479,
                    "parent_id": None,
                    "children": ["toc_l1_0321", "toc_l1_0345", "toc_l1_0355"],
                },
                "toc_l1_0321": {
                    "id": "toc_l1_0321",
                    "title": "1. THE BREEDER'S EQUATION",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 481,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
                "toc_l1_0345": {
                    "id": "toc_l1_0345",
                    "title": "2. TRUNCATION AND THRESHOLD SELECTION",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 507,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
                "toc_l1_0355": {
                    "id": "toc_l1_0355",
                    "title": "3. PERMANENT VERSUS TRANSIENT RESPONSE",
                    "level": 1,
                    "entry_type": "chapter",
                    "page": 525,
                    "parent_id": "toc_l0_0320",
                    "children": [],
                },
            },
        }

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            structured_dir = root / "structured"
            structured_dir.mkdir()
            toc_path = root / "1目录_toc_tree.json"
            toc_path.write_text(json.dumps(toc_payload, ensure_ascii=False), encoding="utf-8")
            titles = {
                13: "Short-term Changes in the Mean: 1. The Breeder's Equation: Introduction",
                14: "Short-term Changes in the Mean: 2. Truncation and Threshold Selection",
                15: "Short-term Changes in the Mean: 3. Permanent Versus Transient Response",
            }
            for index, title in titles.items():
                (structured_dir / f"chapter{index}_001.json").write_text(
                    json.dumps(
                        {
                            "id": f"chapter{index}_001",
                            "metadata": {
                                "chapter": f"chapter{index}",
                                "section": title,
                                "heading_path": [title],
                            },
                            "blocks": [{"type": "discussion", "content": "content"}],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

            units = build_structured_units(sorted(structured_dir.glob("*.json")))
            fusion = fuse_toc_with_structured_units(toc_path, units)

        self.assertEqual("toc_l1_0321", fusion.chapter_to_toc_id["chapter13"])
        self.assertEqual("toc_l1_0345", fusion.chapter_to_toc_id["chapter14"])
        self.assertEqual("toc_l1_0355", fusion.chapter_to_toc_id["chapter15"])
        self.assertNotIn("chapter1", fusion.chapter_to_toc_id)

    def test_scan_imports_built_package_into_graph(self):
        spec = SourceSpec(
            source_key="unit::toc",
            file_hash="hash",
            nodes=[
                {
                    "id": "toc::root",
                    "content": "Test Book",
                    "type": "part",
                    "metadata": {"id": "toc::root", "label": "Test Book", "source": "toc"},
                }
            ],
            relations=[],
            chapters={},
        )

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            manifest_path = Path(tmp) / "structured_sync_manifest.json"
            package_path = Path(tmp) / "teacher_memory_package.json"

            with (
                patch.object(sync_core, "_collect_specs", return_value=([spec], {})),
                patch.object(sync_core, "MANIFEST_PATH", manifest_path),
                patch.object(sync_core, "TEACHER_PACKAGE_PATH", package_path),
                patch.object(sync_core, "_ensure_data_dir", lambda: package_path.parent.mkdir(parents=True, exist_ok=True)),
                patch.object(sync_core, "_save_json", lambda path, payload: path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")),
                patch("KGTS.core.bridge.import_graph_payload", return_value={"nodes": {"success": 1}, "relations": {"success": 0}}) as import_graph_payload,
            ):
                result = sync_core.scan_structured_sources(force=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["graph_import"]["nodes"]["success"], 1)
        import_graph_payload.assert_called_once()
        imported = import_graph_payload.call_args.args[0]
        self.assertEqual(imported["nodes"][0]["id"], "toc::root")

    def test_removed_toc_source_is_cleaned_from_graph(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            manifest_path = Path(tmp) / "structured_sync_manifest.json"
            package_path = Path(tmp) / "teacher_memory_package.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "hashes": {
                            "toc::1目录_toc_tree.json": "old-hash",
                            "chunk::chapter1_001.json": "old-hash",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with (
                patch.object(sync_core, "_collect_specs", return_value=([], {})),
                patch.object(sync_core, "MANIFEST_PATH", manifest_path),
                patch.object(sync_core, "TEACHER_PACKAGE_PATH", package_path),
                patch.object(sync_core, "_ensure_data_dir", lambda: package_path.parent.mkdir(parents=True, exist_ok=True)),
                patch.object(sync_core, "_save_json", lambda path, payload: path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")),
                patch("KGTS.core.bridge.call_backend_tool", return_value={"nodes_deleted": 0, "relations_deleted": 0}) as call_backend_tool,
                patch("KGTS.core.bridge.import_graph_payload", return_value={"nodes": {"success": 0}, "relations": {"success": 0}}),
            ):
                result = sync_core.scan_structured_sources(force=True)

        self.assertIn("toc::1目录_toc_tree.json", result["removed"])
        cleanup_call = call_backend_tool.call_args.args
        self.assertEqual(cleanup_call[0], "delete_by_sources")
        self.assertIn("1目录_toc_tree.json", cleanup_call[1]["sources"])
        self.assertIn("chapter1_001.json", cleanup_call[1]["sources"])


if __name__ == "__main__":
    unittest.main()
