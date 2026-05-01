#!/usr/bin/env python3
"""Dynamic provider registry and fallback-capable memory orchestration."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
MEMORY_SYSTEMS_DIR = PROJECT_ROOT / "memory_systems"


PROVIDER_NAME_ALIASES: Dict[str, Tuple[str, ...]] = {
    "mem0": ("mem0",),
    "openclaw-engram": ("openclaw", "openclaw-engram"),
    "microsoft-graphrag": ("microsoft-graphrag", "microsoft_graphrag", "graphrag"),
    "aws_graphrag": ("aws_graphrag", "aws-graphrag"),
    "graphrag_hybrid": ("graphrag_hybrid", "graphrag-hybrid"),
}


_DISCOVERED_PROVIDER_SPECS: Optional[Dict[str, "ProviderSpec"]] = None
_DISCOVERED_PROVIDER_ALIASES: Optional[Dict[str, str]] = None
_DISCOVERY_ERRORS: Optional[Dict[str, str]] = None


def load_global_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def resolve_memory_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source = config or load_global_config()
    memory_section = source.get("memory")
    if isinstance(memory_section, dict):
        providers = memory_section.get("providers")
        if isinstance(providers, list) and providers:
            return {
                "default_provider": str(memory_section.get("default_provider") or providers[0]),
                "providers": [str(item) for item in providers],
                "fallback_enabled": bool(memory_section.get("fallback_enabled", True)),
            }

    legacy = source.get("memory_system")
    if legacy:
        return {
            "default_provider": str(legacy),
            "providers": [str(legacy)],
            "fallback_enabled": True,
        }

    return {
        "default_provider": "mem0",
        "providers": ["mem0", "openclaw"],
        "fallback_enabled": True,
    }


def save_memory_config(memory_config: Dict[str, Any]) -> Dict[str, Any]:
    raw = load_global_config()
    raw["memory"] = {
        "default_provider": memory_config["default_provider"],
        "providers": list(memory_config["providers"]),
        "fallback_enabled": bool(memory_config.get("fallback_enabled", True)),
    }
    raw.pop("memory_system", None)
    CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    aliases: Tuple[str, ...]
    kind: str
    capabilities: Tuple[str, ...]
    factory: Callable[[Optional[Dict[str, Any]]], Any]
    path: Path
    class_name: str


def _canonical_name(directory_name: str) -> Tuple[str, Tuple[str, ...]]:
    aliases = PROVIDER_NAME_ALIASES.get(directory_name)
    if aliases:
        return aliases[0], aliases
    normalized = directory_name.strip().replace(" ", "_")
    return normalized, (normalized, directory_name)


def _load_module(module_name: str, module_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load provider module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pick_provider_class(module: Any) -> Optional[type]:
    candidates: List[type] = []
    for attribute_name in dir(module):
        attribute = getattr(module, attribute_name)
        if not isinstance(attribute, type):
            continue
        if getattr(attribute, "__module__", None) != getattr(module, "__name__", None):
            continue
        candidates.append(attribute)

    scored: List[Tuple[int, type]] = []
    for candidate in candidates:
        score = 0
        if candidate.__name__.endswith("Access"):
            score += 5
        if hasattr(candidate, "get_status"):
            score += 3
        if hasattr(candidate, "add_memory") or hasattr(candidate, "store_memory"):
            score += 2
        if hasattr(candidate, "search_memory") or hasattr(candidate, "recall_memory") or hasattr(candidate, "query"):
            score += 2
        scored.append((score, candidate))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _provider_capabilities(provider_class: type) -> Tuple[str, ...]:
    capabilities: List[str] = []
    if hasattr(provider_class, "get_status"):
        capabilities.append("status")
    if hasattr(provider_class, "get_stats"):
        capabilities.append("stats")
    if hasattr(provider_class, "add_memory") or hasattr(provider_class, "store_memory"):
        capabilities.append("add")
    if hasattr(provider_class, "search_memory") or hasattr(provider_class, "recall_memory") or hasattr(provider_class, "query"):
        capabilities.append("search")
    if hasattr(provider_class, "process_document"):
        capabilities.append("document")
    return tuple(capabilities)


def _build_factory(provider_name: str, module_path: Path, class_name: str) -> Callable[[Optional[Dict[str, Any]]], Any]:
    def factory(config: Optional[Dict[str, Any]] = None) -> Any:
        module = _load_module(f"kgts_provider_{provider_name}", module_path)
        provider_class = getattr(module, class_name)
        return provider_class(config=config)

    return factory


def discover_provider_specs(force_refresh: bool = False) -> Dict[str, ProviderSpec]:
    global _DISCOVERED_PROVIDER_SPECS, _DISCOVERED_PROVIDER_ALIASES, _DISCOVERY_ERRORS
    if _DISCOVERED_PROVIDER_SPECS is not None and not force_refresh:
        return _DISCOVERED_PROVIDER_SPECS

    specs: Dict[str, ProviderSpec] = {}
    aliases: Dict[str, str] = {}
    errors: Dict[str, str] = {}

    if not MEMORY_SYSTEMS_DIR.exists():
        _DISCOVERED_PROVIDER_SPECS = specs
        _DISCOVERED_PROVIDER_ALIASES = aliases
        _DISCOVERY_ERRORS = {"memory_systems": f"{MEMORY_SYSTEMS_DIR} does not exist"}
        return specs

    for directory in sorted(MEMORY_SYSTEMS_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not directory.is_dir():
            continue
        module_path = directory / "access_entry.py"
        if not module_path.exists():
            continue

        provider_name, provider_aliases = _canonical_name(directory.name)
        try:
            module = _load_module(f"kgts_discovery_{provider_name}", module_path)
            provider_class = _pick_provider_class(module)
            if provider_class is None:
                errors[provider_name] = "No provider class discovered in access_entry.py"
                continue

            capabilities = _provider_capabilities(provider_class)
            spec = ProviderSpec(
                name=provider_name,
                aliases=provider_aliases,
                kind="memory",
                capabilities=capabilities,
                factory=_build_factory(provider_name, module_path, provider_class.__name__),
                path=directory,
                class_name=provider_class.__name__,
            )
            specs[provider_name] = spec
            for alias in provider_aliases:
                aliases[alias] = provider_name
        except Exception as exc:
            errors[provider_name] = str(exc)

    _DISCOVERED_PROVIDER_SPECS = specs
    _DISCOVERED_PROVIDER_ALIASES = aliases
    _DISCOVERY_ERRORS = errors
    return specs


def provider_aliases() -> Dict[str, str]:
    discover_provider_specs()
    return dict(_DISCOVERED_PROVIDER_ALIASES or {})


def normalize_provider_name(name: str) -> str:
    alias_map = provider_aliases()
    return alias_map.get(name, name)


def discover_provider_candidates() -> List[Dict[str, Any]]:
    specs = discover_provider_specs()
    errors = _DISCOVERY_ERRORS or {}
    candidates: List[Dict[str, Any]] = []

    if not MEMORY_SYSTEMS_DIR.exists():
        return candidates

    for directory in sorted(MEMORY_SYSTEMS_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not directory.is_dir():
            continue
        module_path = directory / "access_entry.py"
        if not module_path.exists():
            continue

        provider_name, aliases = _canonical_name(directory.name)
        spec = specs.get(provider_name)
        error = errors.get(provider_name)
        candidates.append(
            {
                "name": provider_name,
                "directory": directory.name,
                "aliases": list(aliases),
                "path": str(directory),
                "exists": True,
                "compatible": spec is not None,
                "capabilities": list(spec.capabilities) if spec else [],
                "class_name": spec.class_name if spec else None,
                "reason": "discovered" if spec else error or "discovery_failed",
            }
        )
    return candidates


class MemoryService:
    """Multi-provider memory service with ordered fallback."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.memory_config = resolve_memory_config(config)
        self.provider_specs = discover_provider_specs()
        self._providers: Dict[str, Any] = {}

    def _instantiate_provider(self, name: str) -> Optional[Any]:
        normalized = normalize_provider_name(name)
        if normalized in self._providers:
            return self._providers[normalized]

        spec = self.provider_specs.get(normalized)
        if spec is None or not spec.path.exists():
            return None

        try:
            provider = spec.factory(None)
        except Exception:
            return None
        self._providers[normalized] = provider
        return provider

    def configured_provider_names(self) -> List[str]:
        names: List[str] = []
        for raw_name in self.memory_config.get("providers", []):
            normalized = normalize_provider_name(str(raw_name))
            if normalized in self.provider_specs and normalized not in names:
                names.append(normalized)

        default_provider = normalize_provider_name(str(self.memory_config.get("default_provider", "")))
        if default_provider in self.provider_specs:
            if default_provider in names:
                names.remove(default_provider)
            names.insert(0, default_provider)

        if names:
            return names

        if "mem0" in self.provider_specs:
            return ["mem0"]
        if "openclaw" in self.provider_specs:
            return ["openclaw"]
        return list(self.provider_specs.keys())

    def _provider_attempt_order(self, action: str) -> Iterable[str]:
        configured = []
        for provider_name in self.configured_provider_names():
            spec = self.provider_specs.get(provider_name)
            if spec is None:
                continue
            if action == "add" and "add" not in spec.capabilities:
                continue
            if action == "search" and "search" not in spec.capabilities:
                continue
            configured.append(provider_name)

        if not self.memory_config.get("fallback_enabled", True) and configured:
            return configured[:1]
        return configured

    def _is_success(self, result: Dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False
        if result.get("error"):
            return False
        status = str(result.get("status", "ready")).lower()
        return status not in {"error", "not_available", "failed", "missing", "not_supported"}

    def _invoke_add(self, provider: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(provider, "add_memory"):
            return provider.add_memory(payload)
        if hasattr(provider, "store_memory"):
            return provider.store_memory(payload)
        if hasattr(provider, "process_document") and payload.get("document_path"):
            return provider.process_document(str(payload["document_path"]))
        return {
            "status": "not_supported",
            "error": f"{provider.__class__.__name__} does not support add_memory/store_memory",
        }

    def _invoke_search(self, provider: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        query = str(payload.get("query", ""))
        k = int(payload.get("k", 5))
        if hasattr(provider, "search_memory"):
            return provider.search_memory(query, k=k)
        if hasattr(provider, "recall_memory"):
            return provider.recall_memory(query, k=k)
        if hasattr(provider, "query"):
            result = provider.query(query)
            if isinstance(result, dict):
                return result
            return {"status": "ready", "results": result}
        return {
            "status": "not_supported",
            "error": f"{provider.__class__.__name__} does not support search/query methods",
        }

    def _call_memory_method(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        attempts: List[Dict[str, Any]] = []
        for provider_name in self._provider_attempt_order(action):
            provider = self._instantiate_provider(provider_name)
            if provider is None:
                attempts.append({"provider": provider_name, "status": "missing"})
                continue

            try:
                if action == "add":
                    result = self._invoke_add(provider, payload)
                elif action == "search":
                    result = self._invoke_search(provider, payload)
                else:
                    raise ValueError(f"Unsupported action: {action}")
            except Exception as exc:
                result = {"status": "error", "error": str(exc)}

            if not isinstance(result, dict):
                result = {"status": "ready", "result": result}

            attempt = {"provider": provider_name, "status": result.get("status", "unknown")}
            if result.get("error"):
                attempt["error"] = result["error"]
            attempts.append(attempt)

            if self._is_success(result):
                result["provider_used"] = provider_name
                result["fallback_used"] = attempts[0]["provider"] != provider_name if attempts else False
                result["provider_attempts"] = attempts
                return result

        return {
            "status": "error",
            "error": f"No provider succeeded for action '{action}'",
            "provider_attempts": attempts,
        }

    def add_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._call_memory_method("add", payload)

    def search_memory(self, query: str, k: int = 5) -> Dict[str, Any]:
        return self._call_memory_method("search", {"query": query, "k": k})

    def get_status(self) -> Dict[str, Any]:
        provider_statuses: List[Dict[str, Any]] = []
        for provider_name in self.configured_provider_names():
            spec = self.provider_specs.get(provider_name)
            provider = self._instantiate_provider(provider_name)
            if provider is None:
                provider_statuses.append(
                    {
                        "provider": provider_name,
                        "status": "missing",
                        "configured": True,
                        "capabilities": list(spec.capabilities) if spec else [],
                    }
                )
                continue

            try:
                status = provider.get_status() if hasattr(provider, "get_status") else {"status": "ready"}
            except Exception as exc:
                status = {"status": "error", "error": str(exc)}
            status["configured"] = True
            status["capabilities"] = list(spec.capabilities) if spec else []
            provider_statuses.append(status)

        return {
            "status": "ready",
            "config": self.memory_config,
            "configured_providers": self.configured_provider_names(),
            "available_candidates": discover_provider_candidates(),
            "providers": provider_statuses,
        }

    def get_stats(self) -> Dict[str, Any]:
        stats: List[Dict[str, Any]] = []
        for provider_name in self.configured_provider_names():
            spec = self.provider_specs.get(provider_name)
            provider = self._instantiate_provider(provider_name)
            if provider is None:
                stats.append(
                    {
                        "provider": provider_name,
                        "status": "missing",
                        "capabilities": list(spec.capabilities) if spec else [],
                    }
                )
                continue

            try:
                provider_stats = provider.get_stats() if hasattr(provider, "get_stats") else {"status": "ready"}
            except Exception as exc:
                provider_stats = {"status": "error", "error": str(exc)}
            provider_stats["provider"] = provider_name
            provider_stats["capabilities"] = list(spec.capabilities) if spec else []
            stats.append(provider_stats)

        return {
            "status": "ready",
            "providers": stats,
            "config": self.memory_config,
            "available_candidates": discover_provider_candidates(),
        }
