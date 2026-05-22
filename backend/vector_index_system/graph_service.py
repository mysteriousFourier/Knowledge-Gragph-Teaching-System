"""Backward-compatibility shim: re-export from KGTS.core.graph_service."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from KGTS.core.graph_service import *  # noqa: F401,F403
