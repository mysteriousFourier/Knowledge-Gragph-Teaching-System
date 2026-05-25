"""全局配置 — 可通过环境变量覆盖"""
import os

HOST = os.getenv("BG_HOST", "0.0.0.0")
PORT = int(os.getenv("BG_PORT", "8080"))

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

MAX_TOKENS = int(os.getenv("BG_MAX_TOKENS", "8192"))
TEMPERATURE = float(os.getenv("BG_TEMPERATURE", "0.7"))

CORS_ORIGINS = os.getenv("BG_CORS_ORIGINS", "*").split(",")

SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "templates", "beamer_system_prompt.txt"
)
