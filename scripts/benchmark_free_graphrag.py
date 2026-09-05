"""Measure retrieval on an isolated snapshot; never alter the source database."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data/seed/knowledge_graph.db")
    parser.add_argument("--queries", nargs="+", default=["Price equation", "genetic variance", "selection response"])
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error("source database does not exist")
    with tempfile.TemporaryDirectory(prefix="kgts-rag-") as temp:
        snapshot = Path(temp) / "graph.db"
        source = sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
        finally:
            source.close()
            destination.close()
        os.environ["KGTS_RETRIEVAL_MODE"] = "sparse_hybrid"
        os.environ["GRAPH_DB_PATH"] = str(snapshot)
        from KGTS.core.graph_service import GraphService
        from KGTS.core.graph_context import build_graphrag_context
        graph = GraphService(snapshot)
        before = snapshot.stat().st_size
        started = time.perf_counter()
        stats = graph.rebuild_vector_index()
        index_seconds = time.perf_counter() - started
        timings = []
        samples = []
        for query in args.queries:
            for _ in range(max(1, args.repeats)):
                started = time.perf_counter()
                rag = build_graphrag_context(query)
                timings.append((time.perf_counter() - started) * 1000)
            samples.append({"query": query, "hits": len(rag["vector_hits"]),
                            "nodes": len(rag["expanded_nodes"]), "relations": len(rag["relations"]),
                            "labels": [hit["metadata"]["label"] for hit in rag["vector_hits"][:3]]})
        report = {"source_db": str(args.db), "nodes": stats["index_size"],
                  "index_seconds": round(index_seconds, 3),
                  "index_growth_mb": round((snapshot.stat().st_size - before) / 1024**2, 2),
                  "query_median_ms": round(statistics.median(timings), 2),
                  "query_max_ms": round(max(timings), 2), "samples": samples,
                  "heavy_modules_loaded": [name for name in ("torch", "sentence_transformers", "faiss") if name in sys.modules]}
        if sys.platform != "win32":
            import resource
            report["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
