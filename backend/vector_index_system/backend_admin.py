#!/usr/bin/env python3
"""Start the vector_index_system backend graph management page."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import DEFAULT_BACKEND_ADMIN_PORT, get_env_int, load_root_env
from knowledge_graph.graph_viz_api import run_server


def main() -> None:
    load_root_env()
    parser = argparse.ArgumentParser(description="Start backend graph admin page")
    parser.add_argument("--port", type=int, default=get_env_int("BACKEND_ADMIN_PORT", DEFAULT_BACKEND_ADMIN_PORT))
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()
