"""Tests for the per-role chat model factory."""
import pytest

from app import llm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_PROVIDER_ADVISER", "LLM_PROVIDER_INTENT", "LLM_PROVIDER_COMPACTION",
                 "QWEN_ENABLE_THINKING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("QWEN_BASE_URL", "http://vllm:8001/v1")
    monkeypatch.setenv("QWEN_MODEL", "adviser-lora")


def test_default_provider_is_gemini():
    assert llm.provider_for("adviser") == "gemini"
    assert type(llm.get_chat_model("adviser")).__name__ == "ChatGoogleGenerativeAI"


def test_google_is_an_alias_for_gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    assert llm.provider_for("intent") == "gemini"


def test_role_override_beats_global(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_PROVIDER_COMPACTION", "qwen")
    assert llm.provider_for("compaction") == "qwen"
    assert llm.provider_for("adviser") == "gemini"


def test_qwen_model_targets_lora_on_vllm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    model = llm.get_chat_model("adviser")
    assert type(model).__name__ == "ChatOpenAI"
    assert model.model_name == "adviser-lora"
    assert str(model.openai_api_base) == "http://vllm:8001/v1"
    assert model.extra_body["chat_template_kwargs"]["enable_thinking"] is True
    # Low-thinking roles switch Qwen3's thinking off
    assert llm.get_chat_model("intent").extra_body["chat_template_kwargs"]["enable_thinking"] is False


def test_qwen_requires_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.delenv("QWEN_BASE_URL")
    with pytest.raises(ValueError, match="QWEN_BASE_URL"):
        llm.get_chat_model("adviser")


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        llm.provider_for("adviser")
