"""The education generation flows intentionally share one model."""
import pytest

from KGTS.education.claude_api import (
    DEFAULT_DEEPSEEK_FLASH_MODEL,
    DEFAULT_DEEPSEEK_PRO_MODEL,
    DeepSeekAPIClient,
    get_deepseek_model,
)


@pytest.mark.parametrize("kind", ["flash", "pro"])
def test_generation_model_is_unified_despite_environment(monkeypatch, kind):
    for key in ("DEEPSEEK_MODEL", "DEEPSEEK_FLASH_MODEL", "DEEPSEEK_PRO_MODEL"):
        monkeypatch.setenv(key, "legacy-model")
    assert get_deepseek_model(kind) == "deepseek-v4-flash-vision-exp"
    assert DEFAULT_DEEPSEEK_FLASH_MODEL == DEFAULT_DEEPSEEK_PRO_MODEL


@pytest.mark.parametrize("requested_model", [None, "legacy-model"])
def test_client_uses_unified_model(requested_model):
    client = DeepSeekAPIClient(api_key="test-not-a-real-key", model=requested_model)
    assert client.model == "deepseek-v4-flash-vision-exp"
