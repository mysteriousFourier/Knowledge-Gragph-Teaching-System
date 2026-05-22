from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


_THIS_FILE = Path(__file__).resolve()
ROOT_DIR = _THIS_FILE.parent
ROOT_ENV_FILE = ROOT_DIR / ".env"

DEFAULT_APP_SCHEME = "http"
DEFAULT_APP_HOST = "127.0.0.1"
DEFAULT_APP_BIND_HOST = "0.0.0.0"
DEFAULT_LOOPBACK_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 3000
DEFAULT_EDUCATION_API_PORT = 8001
DEFAULT_MAINTENANCE_API_PORT = 8002
DEFAULT_BACKEND_ADMIN_PORT = 8080

DEFAULT_STUDENT_USERNAME = "student"
DEFAULT_STUDENT_PASSWORD = ""
DEFAULT_STUDENT_ID = "student_001"
DEFAULT_TEACHER_USERNAME = "teacher"
DEFAULT_TEACHER_PASSWORD = ""
DEFAULT_TEACHER_ID = "teacher_001"


def load_root_env(*, override: bool = False) -> Path:
    if ROOT_ENV_FILE.exists():
        load_dotenv(ROOT_ENV_FILE, override=override)
    return ROOT_ENV_FILE


def get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def build_service_base_url(explicit_name: str, port_name: str, default_port: int) -> str:
    explicit = get_env(explicit_name, "")
    if explicit:
        return _normalize_base_url(explicit)

    scheme = get_env("APP_SCHEME", DEFAULT_APP_SCHEME)
    host = get_env("APP_HOST", DEFAULT_APP_HOST)
    port = get_env_int(port_name, default_port)
    return f"{scheme}://{host}:{port}"


def get_bind_host(service_env_name: str = "APP_BIND_HOST") -> str:
    return get_env(service_env_name, get_env("APP_BIND_HOST", DEFAULT_APP_BIND_HOST))


def get_loopback_host() -> str:
    return get_env("APP_LOOPBACK_HOST", DEFAULT_LOOPBACK_HOST)


def get_auth_config(role: str) -> dict[str, str]:
    prefix = f"APP_{role.upper()}"
    defaults = {
        "student": {
            "username": DEFAULT_STUDENT_USERNAME,
            "password": DEFAULT_STUDENT_PASSWORD,
            "user_id": DEFAULT_STUDENT_ID,
        },
        "teacher": {
            "username": DEFAULT_TEACHER_USERNAME,
            "password": DEFAULT_TEACHER_PASSWORD,
            "user_id": DEFAULT_TEACHER_ID,
        },
    }
    fallback = defaults[role]
    return {
        "username": get_env(f"{prefix}_USERNAME", fallback["username"]),
        "password": get_env(f"{prefix}_PASSWORD", fallback["password"]),
        "user_id": get_env(f"{prefix}_ID", fallback["user_id"]),
    }


def build_frontend_runtime_config() -> dict[str, Any]:
    return {
        "educationApiBaseUrl": build_service_base_url(
            "EDUCATION_API_BASE_URL",
            "EDUCATION_API_PORT",
            DEFAULT_EDUCATION_API_PORT,
        ),
        "maintenanceApiBaseUrl": build_service_base_url(
            "MAINTENANCE_API_BASE_URL",
            "MAINTENANCE_API_PORT",
            DEFAULT_MAINTENANCE_API_PORT,
        ),
        "backendAdminBaseUrl": build_service_base_url(
            "BACKEND_ADMIN_BASE_URL",
            "BACKEND_ADMIN_PORT",
            DEFAULT_BACKEND_ADMIN_PORT,
        ),
    }


def write_frontend_runtime_config(output_path: Path) -> dict[str, Any]:
    config = build_frontend_runtime_config()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        (
            "// Auto-generated from the repository root .env file.\n"
            f"window.__APP_CONFIG__ = Object.freeze({json.dumps(config, ensure_ascii=False, indent=2)});\n"
        ),
        encoding="utf-8",
    )
    return config


def write_frontend_json_cache(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class EduConfig:
    BACKEND_DB_PATH = str(ROOT_DIR / "backend" / "mcp-server" / "data" / "knowledge_graph.db")

    LECTURE_STYLE = "引导式教学"
    LECTURE_LENGTH = "中等"
    LECTURE_LANGUAGE = "中文"

    ANSWER_MAX_LENGTH = 500
    ANSWER_INCLUDE_EXAMPLES = True

    EXERCISE_TYPES = ["填空题", "选择题", "简答题"]
    DEFAULT_EXERCISE_COUNT = {
        "填空题": 3,
        "选择题": 3,
        "简答题": 2,
    }

    MAX_PATH_DEPTH = 5
    MIN_PATH_NODES = 2

    LOG_LEVEL = "INFO"


config = EduConfig()
