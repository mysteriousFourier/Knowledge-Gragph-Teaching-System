from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def project_local_only() -> bool:
    if env_flag("KGTS_ALLOW_EXTERNAL_PATHS", False):
        return False
    return env_flag("KGTS_PROJECT_LOCAL_ONLY", True)


def resolve_project_path(value: str | Path | None, *, default: Path | None = None) -> Path | None:
    if value is None or str(value).strip() == "":
        path = default
    else:
        path = Path(value)
    if path is None:
        return None
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def is_project_path(path: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(PROJECT_ROOT.resolve())
        return True
    except (OSError, ValueError):
        return False


def project_path_error(path: str | Path, *, label: str = "path") -> str | None:
    resolved = resolve_project_path(path)
    if resolved is None or not project_local_only() or is_project_path(resolved):
        return None
    return f"{label} is outside project root while KGTS_PROJECT_LOCAL_ONLY=1: {resolved}"


def require_project_path(path: str | Path, *, label: str = "path") -> Path:
    resolved = resolve_project_path(path)
    if resolved is None:
        raise ValueError(f"{label} is required")
    error = project_path_error(resolved, label=label)
    if error:
        raise ValueError(error)
    return resolved


def outside_project_paths(paths: Iterable[tuple[str, str | Path | None]]) -> list[dict[str, Any]]:
    if not project_local_only():
        return []
    results: list[dict[str, Any]] = []
    for label, raw_path in paths:
        resolved = resolve_project_path(raw_path)
        if resolved is None or is_project_path(resolved):
            continue
        results.append({"label": label, "path": str(resolved)})
    return results

