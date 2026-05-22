#!/usr/bin/env python3
"""Unified CLI for Knowledge-Gragph-Teaching-System memory and graph operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from graph_service import GraphService
from memory_runtime import MemoryService, resolve_memory_config, save_memory_config


PROJECT_ROOT = Path(__file__).resolve().parent


def _service_graph(db_path: Optional[str] = None) -> GraphService:
    return GraphService(db_path=db_path)


def _service_memory() -> MemoryService:
    return MemoryService()


def _rag_answer(query: str, graph: GraphService, memory: MemoryService, limit: int = 5) -> Dict[str, Any]:
    semantic_hits = graph.semantic_search(query, top_k=limit)
    keyword_hits = graph.search_nodes(query, limit=limit)
    memory_hits = memory.search_memory(query, k=limit)

    context_lines = []
    seen = set()
    for hit in semantic_hits:
        label = hit["metadata"].get("label") or hit["node_id"]
        if label in seen:
            continue
        seen.add(label)
        context_lines.append(f"- {label}")
    for hit in keyword_hits:
        label = hit["metadata"].get("label") or hit["id"]
        if label in seen:
            continue
        seen.add(label)
        context_lines.append(f"- {label}")

    if context_lines:
        answer = "Relevant graph context:\n" + "\n".join(context_lines[:limit])
    else:
        answer = "No relevant graph context was found."

    return {
        "status": "ready",
        "query": query,
        "answer": answer,
        "graph_hits": semantic_hits,
        "keyword_hits": keyword_hits,
        "memory_hits": memory_hits,
    }


def dispatch_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
    args = arguments or {}
    graph = _service_graph(args.get("db_path"))
    memory = _service_memory()

    if name == "read_graph":
        return graph.read_graph()
    if name == "get_node":
        return graph.get_node(args["node_id"]) or {}
    if name == "search_nodes":
        return graph.search_nodes(args.get("keyword", ""), args.get("node_type"), int(args.get("limit", 20)))
    if name == "semantic_search":
        return graph.semantic_search(args.get("query", ""), args.get("node_type"), int(args.get("top_k", 10)))
    if name == "add_memory":
        created = graph.add_node(args.get("content", ""), args.get("type", "concept"), args.get("metadata"))
        memory.add_memory(
            {
                "content": created.get("content", ""),
                "metadata": created.get("metadata", {}),
                "type": created.get("type", "concept"),
            }
        )
        return created
    if name == "update_memory":
        return graph.update_node(args["node_id"], args.get("content"), args.get("metadata"))
    if name == "delete_memory":
        return graph.delete_node(args["node_id"])
    if name == "add_relation":
        return graph.add_relation(
            args["source_id"],
            args["target_id"],
            args["relation_type"],
            args.get("metadata"),
            args.get("similarity"),
        )
    if name == "get_relations":
        return graph.get_relations(args.get("node_id"), args.get("relation_type"))
    if name == "get_relation":
        return graph.get_relation(args["relation_id"]) or {}
    if name == "get_neighbors":
        return graph.get_neighbors(args["node_id"], args.get("direction", "both"))
    if name == "get_graph_schema":
        graph_data = graph.read_graph()
        return {
            "stats": graph_data.get("stats", {}),
            "vector_stats": graph_data.get("vector_stats", {}),
            "node_types": list(graph_data.get("stats", {}).get("node_types", {}).keys()),
            "relation_types": sorted({relation["relation_type"] for relation in graph_data.get("relations", [])}),
        }
    if name == "batch_import_graph":
        return graph.batch_import_graph(args.get("nodes", []), args.get("relations", []))
    if name == "update_relation":
        return graph.update_relation(
            args["relation_id"],
            args.get("source_id"),
            args.get("target_id"),
            args.get("relation_type"),
            args.get("metadata"),
            args.get("similarity"),
        )
    if name == "delete_relation":
        return graph.delete_relation(args["relation_id"])
    if name == "get_graph_statistics":
        return graph.get_graph_statistics()
    if name == "get_subgraph_by_type":
        return graph.get_subgraph_by_type(args["node_type"])
    if name == "get_k_hop_neighbors":
        return graph.get_k_hop_neighbors(args["node_id"], int(args.get("k", 2)))
    if name == "get_prerequisites":
        return graph.get_prerequisites(args["node_id"], int(args.get("max_depth", 3)))
    if name == "get_follow_up":
        return graph.get_follow_up(args["node_id"], int(args.get("max_depth", 3)))
    if name == "get_note":
        return graph.get_note(args.get("node_id"))
    if name == "trace_call_path":
        return graph.get_follow_up(args["start_node_id"], int(args.get("max_depth", 5)))
    if name == "discover_weak_relations":
        node = graph.get_node(args["node_id"])
        query = (node or {}).get("content") or args["node_id"]
        return graph.semantic_search(query, top_k=10)

    return {"status": "error", "error": f"Unknown tool: {name}"}


def _print_json(payload: Any) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    if isinstance(payload, dict):
        return 0 if payload.get("status") != "error" and not payload.get("error") else 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Knowledge-Gragph-Teaching-System unified CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tool_parser = subparsers.add_parser("tool", help="Invoke a compatibility tool")
    tool_parser.add_argument("name")
    tool_parser.add_argument("--args", default="{}", help="JSON object of tool arguments")

    memory_parser = subparsers.add_parser("memory", help="Memory provider operations")
    memory_sub = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_sub.add_parser("status")
    memory_add = memory_sub.add_parser("add")
    memory_add.add_argument("content")
    memory_add.add_argument("--type", default="note")
    memory_add.add_argument("--metadata", default="{}")
    memory_search = memory_sub.add_parser("search")
    memory_search.add_argument("query")
    memory_search.add_argument("--k", type=int, default=5)
    memory_sub.add_parser("stats")
    memory_config = memory_sub.add_parser("configure")
    memory_config.add_argument("--default-provider", required=True)
    memory_config.add_argument("--providers", nargs="+", required=True)
    memory_config.add_argument("--fallback-enabled", choices=["true", "false"], default="true")

    graph_parser = subparsers.add_parser("graph", help="Graph operations")
    graph_sub = graph_parser.add_subparsers(dest="graph_command", required=True)
    graph_sub.add_parser("read")
    graph_search = graph_sub.add_parser("search")
    graph_search.add_argument("query")
    graph_search.add_argument("--node-type")
    graph_search.add_argument("--limit", type=int, default=20)
    graph_semantic = graph_sub.add_parser("semantic-search")
    graph_semantic.add_argument("query")
    graph_semantic.add_argument("--node-type")
    graph_semantic.add_argument("--top-k", type=int, default=10)
    graph_hybrid = graph_sub.add_parser("hybrid-search")
    graph_hybrid.add_argument("query")
    graph_hybrid.add_argument("--top-k", type=int, default=10)
    graph_stats = graph_sub.add_parser("stats")
    graph_stats.add_argument("--node-type")

    rag_parser = subparsers.add_parser("rag", help="RAG operations")
    rag_sub = rag_parser.add_subparsers(dest="rag_command", required=True)
    rag_ask = rag_sub.add_parser("ask")
    rag_ask.add_argument("query")
    rag_ask.add_argument("--limit", type=int, default=5)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "tool":
        return _print_json(dispatch_tool(args.name, json.loads(args.args)))

    if args.command == "memory":
        memory = _service_memory()
        if args.memory_command == "status":
            return _print_json(memory.get_status())
        if args.memory_command == "add":
            return _print_json(
                memory.add_memory(
                    {
                        "content": args.content,
                        "type": args.type,
                        "metadata": json.loads(args.metadata),
                    }
                )
            )
        if args.memory_command == "search":
            return _print_json(memory.search_memory(args.query, k=args.k))
        if args.memory_command == "stats":
            return _print_json(memory.get_stats())
        if args.memory_command == "configure":
            payload = {
                "default_provider": args.default_provider,
                "providers": list(args.providers),
                "fallback_enabled": args.fallback_enabled == "true",
            }
            save_memory_config(payload)
            return _print_json({"status": "ready", "config": resolve_memory_config({"memory": payload})})

    if args.command == "graph":
        graph = _service_graph()
        if args.graph_command == "read":
            return _print_json(graph.read_graph())
        if args.graph_command == "search":
            return _print_json(
                {
                    "status": "ready",
                    "results": graph.search_nodes(args.query, args.node_type, args.limit),
                }
            )
        if args.graph_command == "semantic-search":
            return _print_json(
                {
                    "status": "ready",
                    "results": graph.semantic_search(args.query, args.node_type, args.top_k),
                }
            )
        if args.graph_command == "hybrid-search":
            return _print_json(
                {
                    "status": "ready",
                    "results": graph.semantic_search(args.query, top_k=args.top_k),
                }
            )
        if args.graph_command == "stats":
            if args.node_type:
                return _print_json({"status": "ready", "data": graph.get_subgraph_by_type(args.node_type)})
            return _print_json({"status": "ready", "data": graph.get_graph_statistics()})

    if args.command == "rag":
        graph = _service_graph()
        memory = _service_memory()
        if args.rag_command == "ask":
            return _print_json(_rag_answer(args.query, graph=graph, memory=memory, limit=args.limit))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
