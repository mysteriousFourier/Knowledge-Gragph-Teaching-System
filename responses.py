from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import HTTPException

def success_response(data: Any = None, **kwargs) -> Dict[str, Any]:
    result: Dict[str, Any] = {"success": True, **kwargs}
    if data is not None:
        result["data"] = data
    return result

def timestamped_response(data: Any = None, **kwargs) -> Dict[str, Any]:
    return success_response(data, timestamp=datetime.now().isoformat(), **kwargs)

def error_response(detail: str, status_code: int = 500) -> None:
    raise HTTPException(status_code=status_code, detail=detail)

def normalize_frontend_node(node: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return node
    metadata = node.get("metadata") or {}
    return {
        "id": node.get("id"),
        "label": metadata.get("label") or node.get("label") or node.get("id"),
        "type": node.get("type"),
        "content": node.get("content"),
        "source": metadata.get("source"),
        "confidence": metadata.get("confidence", 1.0),
        "created_at": node.get("created_at"),
        "updated_at": node.get("updated_at"),
        "reviewed": bool(metadata.get("reviewed")),
        "metadata": metadata,
    }

def normalize_frontend_relation(relation: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(relation, dict):
        return relation
    metadata = relation.get("metadata") or {}
    source_id = relation.get("source_id") or relation.get("source_node")
    target_id = relation.get("target_id") or relation.get("target_node")
    relation_type = relation.get("relation_type") or relation.get("type") or "related"
    return {
        "id": relation.get("id"),
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "similarity": relation.get("similarity", 1.0),
        "description": metadata.get("description", ""),
        "source_file": metadata.get("source"),
        "created_at": relation.get("created_at"),
        "updated_at": relation.get("updated_at"),
        "reviewed": bool(metadata.get("reviewed")),
        "metadata": metadata,
    }
