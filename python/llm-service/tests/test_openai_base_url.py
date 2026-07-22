import sys
import types
from types import SimpleNamespace

openai_stub = types.ModuleType("openai")
openai_stub.AsyncOpenAI = lambda **kwargs: SimpleNamespace()
sys.modules.setdefault("openai", openai_stub)
sys.modules.setdefault("tiktoken", types.ModuleType("tiktoken"))

from llm_provider.manager import LLMManager
from llm_provider.openai_provider import OpenAIProvider


MODEL_CONFIG = {
    "api_key": "test-key",
    "models": {
        "gpt-5.5": {
            "model_id": "gpt-5.5",
            "tier": "medium",
            "context_window": 400000,
            "max_tokens": 128000,
        }
    },
}


def capture_client(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("llm_provider.openai_provider.AsyncOpenAI", fake_client)
    return captured


def test_environment_base_url_overrides_provider_config(monkeypatch):
    captured = capture_client(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://www.codex2api.com/v1/")

    OpenAIProvider({**MODEL_CONFIG, "base_url": "https://api.openai.com/v1"})

    assert captured["base_url"] == "https://www.codex2api.com/v1"


def test_provider_config_base_url_is_used_without_environment(monkeypatch):
    captured = capture_client(monkeypatch)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    OpenAIProvider({**MODEL_CONFIG, "base_url": "https://example.test/v1/"})

    assert captured["base_url"] == "https://example.test/v1"


def test_sdk_default_is_preserved_without_any_base_url(monkeypatch):
    captured = capture_client(monkeypatch)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    OpenAIProvider(MODEL_CONFIG)

    assert "base_url" not in captured


def test_unified_config_passes_openai_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    manager = LLMManager.__new__(LLMManager)
    config = {
        "model_catalog": {"openai": MODEL_CONFIG["models"]},
        "model_tiers": {},
        "provider_settings": {
            "openai": {"base_url": "https://api.openai.com/v1"}
        },
    }

    providers, _, _ = manager._translate_unified_config(config)

    assert providers["openai"]["base_url"] == "https://api.openai.com/v1"
