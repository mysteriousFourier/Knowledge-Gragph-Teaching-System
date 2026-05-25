"""Structured sync - re-export from modular submodules.

This module re-exports the public API for backward compatibility.
New code should import directly from the submodules:
  - KGTS.maintenance.sync_utils
  - KGTS.maintenance.sync_builders
  - KGTS.maintenance.sync_core
"""
from __future__ import annotations

from KGTS.maintenance.sync_core import (
    build_teacher_package,
    rebuild_staging_graph,
    review_search,
    scan_structured_sources,
)
from KGTS.maintenance.sync_utils import SourceSpec

__all__ = [
    "SourceSpec",
    "scan_structured_sources",
    "rebuild_staging_graph",
    "build_teacher_package",
    "review_search",
]
