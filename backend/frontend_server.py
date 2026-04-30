from __future__ import annotations

import functools
import http.server
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import DEFAULT_FRONTEND_PORT, get_bind_host, get_env_int, get_loopback_host, load_root_env


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main() -> None:
    load_root_env()

    port = int(sys.argv[1]) if len(sys.argv) > 1 else get_env_int("FRONTEND_PORT", DEFAULT_FRONTEND_PORT)
    directory = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path.cwd()
    handler = functools.partial(NoCacheHandler, directory=str(directory))
    bind_host = get_bind_host("FRONTEND_BIND_HOST")

    with http.server.ThreadingHTTPServer((bind_host, port), handler) as server:
        print(f"Serving {directory} at http://{get_loopback_host()}:{port} with no-cache headers")
        server.serve_forever()


if __name__ == "__main__":
    main()
