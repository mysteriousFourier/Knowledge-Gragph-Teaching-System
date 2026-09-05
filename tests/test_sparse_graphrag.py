from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from KGTS.core.graph_service import GraphService
from KGTS.core.graph_context import build_graphrag_context, build_node_contexts


@pytest.fixture
def graph(tmp_path, monkeypatch):
    monkeypatch.setenv("KGTS_RETRIEVAL_MODE", "sparse_hybrid")
    monkeypatch.setenv("GRAPH_DB_PATH", str(tmp_path / "graph.db"))
    return GraphService()


def node(graph, key, text, kind="concept"):
    return graph.add_node(text, kind, {"id": key, "label": text, "source_file": "lesson.md"})


def test_chinese_english_and_scope_before_limit(graph):
    node(graph, "cn", "矩阵乘法与线性变换")
    node(graph, "en", "Matrix multiplication and linear transformation")
    for i in range(40):
        node(graph, str(i), "Matrix")
    assert graph.semantic_search("如何计算矩阵乘法")[0]["node_id"] == "cn"
    assert graph.semantic_search("matrix", top_k=1, allowed_node_ids=["en"])[0]["node_id"] == "en"
    assert graph.semantic_search("matrix", allowed_node_ids=[]) == []
    assert graph.semantic_search("matrix", node_type="formula") == []
    assert graph.semantic_search('" OR * NOT ()') == []
    assert graph.semantic_search("matrix", top_k=0) == []


def test_raw_database_edits_and_restarts_are_indexed(graph):
    node(graph, "a", "originalterm")
    assert graph.semantic_search("originalterm")
    with graph._connection() as conn:
        conn.execute("UPDATE nodes SET label='replacementterm',content='replacementterm' WHERE id='a'")
    restarted = GraphService(graph.db_path)
    assert restarted.semantic_search("originalterm") == []
    assert restarted.semantic_search("replacementterm")[0]["node_id"] == "a"
    with graph._connection() as conn:
        conn.execute("DELETE FROM nodes WHERE id='a'")
    assert restarted.semantic_search("replacementterm") == []
    assert restarted._vector_stats()["pending_updates"] == 0


def test_search_includes_nodes_beyond_old_5000_limit(graph):
    with graph._connection() as conn:
        conn.executemany("INSERT INTO nodes(id,label,type,content,created_at,updated_at) VALUES (?,?,'concept',?,0,?)",
                         ((str(i), "needle" if i == 0 else "other", "body", i) for i in range(6000)))
    with patch.object(graph, "_fetch_node_rows", side_effect=AssertionError("full scan")):
        assert graph.semantic_search("needle")[0]["node_id"] == "0"
    assert graph._vector_stats()["index_size"] == 6000
    assert graph.rebuild_vector_index()["mode"] == "sparse_hybrid"
    assert graph.vector_index is None


def test_two_hop_evidence_reaches_prompt_without_full_graph(graph):
    node(graph, "a", "specificterm")
    node(graph, "b", "first derivation", "formula")
    node(graph, "c", "second result")
    graph.add_relation("a", "b", "derives")
    graph.add_relation("b", "c", "depends_on")
    with patch.object(GraphService, "read_graph", side_effect=AssertionError("full graph loaded")):
        rag = build_graphrag_context("specificterm", limit=1)
    assert {v["id"] for v in rag["expanded_nodes"]} == {"a", "b", "c"}
    assert "second result" in str(rag["llm_context"])
    assert "depends_on" in str(rag["llm_context"])
    assert rag["evidence"][0]["source_file"] == "lesson.md"
    assert rag["retrieval_stats"]["provider"] == "sqlite-fts5-bm25"
    from KGTS.core.bridge import build_rag_context
    with patch("KGTS.core.bridge.search_memory", return_value={}):
        bridged = build_rag_context("specificterm", limit=1)
    assert "second result" in str(bridged["llm_context"])


def test_scope_intersection_and_contains_cycles(graph):
    node(graph, "root", "chapter", "chapter")
    node(graph, "a", "matrix")
    node(graph, "outside", "matrix")
    graph.add_relation("root", "a", "contains")
    graph.add_relation("a", "root", "contains")
    graph.add_relation("a", "outside", "related")
    context = build_node_contexts(["root"])
    assert {v["id"] for v in context["nodes"]} == {"root", "a"}
    rag = build_graphrag_context("matrix", seed_node_ids=["root"])
    assert "outside" not in {v["id"] for v in rag["expanded_nodes"]}
    empty = build_graphrag_context("matrix", seed_node_ids=["root"], allowed_node_ids=["outside"])
    assert empty["expanded_nodes"] == []
    assert build_graphrag_context("matrix", allowed_node_ids=[])["expanded_nodes"] == []


def test_high_degree_graph_has_bounded_context(graph):
    node(graph, "root", "specificterm")
    for i in range(50):
        node(graph, str(i), "unrelated text")
        graph.add_relation("root", str(i), "related")
    rag = build_graphrag_context("specificterm", expansion_limit=8)
    assert len(rag["expanded_nodes"]) == 8
    assert len(rag["relations"]) <= 64


def test_selected_scope_retains_semantic_edges(graph):
    node(graph, "root", "chapter", "chapter")
    node(graph, "a", "specificterm")
    node(graph, "b", "prerequisite evidence")
    graph.add_relation("root", "a", "contains")
    graph.add_relation("root", "b", "contains")
    graph.add_relation("a", "b", "depends_on")
    rag = build_graphrag_context("specificterm", seed_node_ids=["root"], limit=1)
    assert {v["id"] for v in rag["expanded_nodes"]} == {"a", "b"}
    assert "depends_on" in str(rag["llm_context"])


def test_concurrent_first_queries_and_warm_reuse(graph):
    from concurrent.futures import ThreadPoolExecutor
    node(graph, "a", "specificterm")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: GraphService(graph.db_path).semantic_search("specificterm"), range(3)))
    assert all(result[0]["node_id"] == "a" for result in results)
    from KGTS.core import sparse_index
    with patch.object(sparse_index, "tokens", wraps=sparse_index.tokens) as tokenize:
        graph.semantic_search("specificterm")
    assert tokenize.call_count == 1  # Only the query is tokenized after a restart.


def test_renamed_node_removes_old_index_entry(graph):
    node(graph, "old", "specificterm")
    graph.semantic_search("specificterm")
    with graph._connection() as conn:
        conn.execute("UPDATE nodes SET id='new' WHERE id='old'")
    assert graph.semantic_search("specificterm")[0]["node_id"] == "new"
    assert graph._vector_stats()["index_size"] == 1
