#!/usr/bin/env python3
"""RAG-style LLM integration built on the unified graph and memory runtime."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from graph_service import GraphService
from memory_runtime import MemoryService, load_global_config, resolve_memory_config


class LLMIntegration:
    """Graph + memory backed answer generation with optional OpenAI-compatible clients."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        global_config = load_global_config()
        merged_config = dict(global_config)
        merged_config.update(config or {})

        self.config = merged_config
        self.deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", self.config.get("deepseek_api_key", ""))
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", self.config.get("openai_api_key", ""))

        self.graph_service = GraphService(db_path=self.config.get("db_path"))
        self.memory_service = MemoryService(config=self.config)
        self.memory_config = resolve_memory_config(self.config)
        self.memory_client = self.memory_service
        self.memory_system = self.memory_config.get("default_provider", "none")
        self.llm_client = self._init_llm_client()

    def _init_llm_client(self) -> Optional[Any]:
        try:
            from openai import OpenAI
        except ImportError:
            return None

        if self.deepseek_api_key:
            return OpenAI(api_key=self.deepseek_api_key, base_url="https://api.deepseek.com")
        if self.openai_api_key:
            return OpenAI(api_key=self.openai_api_key)
        return None

    def retrieve_context(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        semantic_hits = self.graph_service.semantic_search(query, top_k=k)
        keyword_hits = self.graph_service.search_nodes(query, limit=k)

        combined: List[Dict[str, Any]] = []
        seen_ids = set()

        for hit in semantic_hits:
            node_id = hit.get("node_id")
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            combined.append(
                {
                    "id": node_id,
                    "text": hit.get("metadata", {}).get("content") or "",
                    "label": hit.get("metadata", {}).get("label") or node_id,
                    "type": hit.get("metadata", {}).get("type") or "concept",
                    "similarity": hit.get("similarity", 0.0),
                    "source": "semantic_search",
                }
            )

        for hit in keyword_hits:
            node_id = hit.get("id")
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            metadata = hit.get("metadata") or {}
            combined.append(
                {
                    "id": node_id,
                    "text": hit.get("content") or metadata.get("description") or "",
                    "label": metadata.get("label") or hit.get("label") or node_id,
                    "type": hit.get("type") or "concept",
                    "similarity": 1.0,
                    "source": "keyword_search",
                }
            )

        return combined[:k]

    def _build_rag_prompt(self, query: str, retrieved_results: List[Dict[str, Any]]) -> str:
        if not retrieved_results:
            context_block = "No relevant graph context was found."
        else:
            lines = []
            for index, item in enumerate(retrieved_results, start=1):
                lines.append(
                    f"[{index}] {item['label']} ({item['type']}, score={item['similarity']:.4f})\n{item['text']}"
                )
            context_block = "\n\n".join(lines)

        return (
            "You are answering based on the current knowledge graph.\n\n"
            f"Context:\n{context_block}\n\n"
            f"Question:\n{query}\n\n"
            "Answer clearly. If the context is insufficient, say so."
        )

    def _fallback_answer(self, query: str, retrieved_results: List[Dict[str, Any]]) -> str:
        if not retrieved_results:
            return f"No graph context was found for: {query}"

        summary_lines = []
        for item in retrieved_results[:4]:
            snippet = item["text"].strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            summary_lines.append(f"- {item['label']}: {snippet}")

        return "Relevant graph context:\n" + "\n".join(summary_lines)

    def _call_llm(self, model: str, prompt: str, query: str, retrieved_results: List[Dict[str, Any]]) -> str:
        if self.llm_client is None:
            return self._fallback_answer(query, retrieved_results)

        try:
            response = self.llm_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception:
            return self._fallback_answer(query, retrieved_results)

    def _store_to_memory_system(self, query: str, response: str) -> Dict[str, Any]:
        return self.memory_service.add_memory(
            {
                "type": "conversation",
                "content": f"Q: {query}\nA: {response}",
                "metadata": {
                    "query": query,
                    "response": response,
                    "timestamp": time.time(),
                },
            }
        )

    def generate_with_rag(self, query: str, k: int = 5, model: str = "deepseek-chat") -> Dict[str, Any]:
        start_time = time.time()
        retrieved_results = self.retrieve_context(query, k=k)
        prompt = self._build_rag_prompt(query, retrieved_results)
        response = self._call_llm(model, prompt, query, retrieved_results)
        memory_result = self._store_to_memory_system(query, response)

        return {
            "query": query,
            "response": response,
            "retrieved_results": retrieved_results,
            "time_taken": time.time() - start_time,
            "model": model,
            "memory_result": memory_result,
        }

    def batch_process(self, queries: List[str], k: int = 5, model: str = "deepseek-chat") -> List[Dict[str, Any]]:
        return [self.generate_with_rag(query, k=k, model=model) for query in queries]

    def get_system_status(self) -> Dict[str, Any]:
        graph_stats = self.graph_service.get_graph_statistics()
        memory_status = self.memory_service.get_status()
        llm_status = "ready" if self.llm_client else "mock"

        return {
            "system_status": "ready",
            "llm_status": llm_status,
            "graph_stats": graph_stats,
            "memory_status": memory_status,
            "config": {
                "deepseek_api_key_set": bool(self.deepseek_api_key),
                "openai_api_key_set": bool(self.openai_api_key),
                "memory": self.memory_config,
            },
        }


if __name__ == "__main__":
    integration = LLMIntegration()
    print(integration.get_system_status())
