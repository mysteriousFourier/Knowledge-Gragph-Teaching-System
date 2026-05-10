from __future__ import annotations
from fastapi.middleware.cors import CORSMiddleware
from typing import List

def setup_cors(app, allow_origins: List[str] | None = None) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
