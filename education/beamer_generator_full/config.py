"""全局配置 — 可通过环境变量覆盖"""
import os

HOST = os.getenv("BG_HOST", "0.0.0.0")
PORT = int(os.getenv("BG_PORT", "8080"))

GPT_BASE_URL = os.getenv("GPT_API_BASE", os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"))
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-5.5")

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", GPT_BASE_URL)
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", GPT_MODEL)

MAX_TOKENS = int(os.getenv("BG_MAX_TOKENS", "16000"))
TEMPERATURE = float(os.getenv("BG_TEMPERATURE", "0.7"))

CORS_ORIGINS = os.getenv("BG_CORS_ORIGINS", "*").split(",")

SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "templates", "beamer_system_prompt.txt"
)
