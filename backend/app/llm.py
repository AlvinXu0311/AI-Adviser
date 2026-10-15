"""
Chat model factory: every backend LLM call goes through get_chat_model(role).

Providers
- gemini (default): Google Gemini via langchain-google-genai.
- qwen: a self-hosted Qwen3-8B (base model + LoRA adapter) behind an OpenAI-compatible
  server such as vLLM, e.g.

      vllm serve Qwen/Qwen3-8B --enable-lora \\
          --lora-modules adviser-lora=/path/to/lora \\
          --enable-auto-tool-choice --tool-call-parser hermes \\
          --reasoning-parser qwen3

  The reasoning parser keeps Qwen3's <think> blocks out of the answer text.

  QWEN_MODEL selects what the server should run: the LoRA module name ("adviser-lora")
  or the base model name to skip the adapter.

The provider is chosen per role, so the fine-tuned model can take over one job (say,
compaction or intent) while Gemini keeps the others:
    LLM_PROVIDER_<ROLE>  →  LLM_PROVIDER  →  "gemini"
"""
import logging
import os
from typing import Any, Dict

from langchain_core.language_models.chat_models import BaseChatModel

from .config import gemini_model

logger = logging.getLogger(__name__)

GEMINI = "gemini"
QWEN = "qwen"
PROVIDERS = (GEMINI, QWEN)
ALIASES = {"google": GEMINI}

DEFAULT_QWEN_MODEL = "adviser-lora"

# Per-role generation settings. "thinking" maps to Gemini's thinking_level and to
# Qwen3's hybrid thinking switch (enable_thinking).
ROLE_SETTINGS: Dict[str, Dict[str, Any]] = {
    # Main tool-calling adviser; thought summaries feed the "agent process" panel in the UI
    "adviser": {"temperature": 0.3, "max_tokens": 4096, "thinking": "medium", "include_thoughts": True},
    # JSON intent classification; must stay inside INTENT_AGENT_TIMEOUT
    "intent": {"temperature": 0, "max_tokens": 256, "thinking": "low"},
    # Rolling summary of older chat turns (see services/context_compaction.py)
    "compaction": {"temperature": 0, "max_tokens": 1024, "thinking": "low"},
}


def provider_for(role: str) -> str:
    """Provider configured for a role: LLM_PROVIDER_<ROLE>, then LLM_PROVIDER, then gemini."""
    provider = (
        os.getenv(f"LLM_PROVIDER_{role.upper()}")
        or os.getenv("LLM_PROVIDER")
        or GEMINI
    ).strip().lower()
    provider = ALIASES.get(provider, provider)
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown LLM provider '{provider}' for role '{role}'; expected one of {PROVIDERS}")
    return provider


def model_name_for(role: str) -> str:
    """Model name the role's provider will call (for logs and status checks)."""
    if provider_for(role) == QWEN:
        return os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL)
    return gemini_model()


def get_chat_model(role: str) -> BaseChatModel:
    """Build the chat model for a role ("adviser", "intent" or "compaction")."""
    if role not in ROLE_SETTINGS:
        raise ValueError(f"Unknown LLM role '{role}'; expected one of {list(ROLE_SETTINGS)}")
    settings = ROLE_SETTINGS[role]
    provider = provider_for(role)
    logger.info("LLM role '%s' → %s (%s)", role, provider, model_name_for(role))
    if provider == QWEN:
        return _qwen_chat_model(settings)
    return _gemini_chat_model(settings)


def _gemini_chat_model(settings: Dict[str, Any]) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is required for the gemini provider")
    kwargs: Dict[str, Any] = {
        "model": gemini_model(),
        "temperature": settings["temperature"],
        "max_output_tokens": settings["max_tokens"],
        "thinking_level": settings["thinking"],
        "api_key": api_key,
    }
    if settings.get("include_thoughts"):
        kwargs["include_thoughts"] = True  # "low" thinking returns no thought summaries
    return ChatGoogleGenerativeAI(**kwargs)


def _qwen_chat_model(settings: Dict[str, Any]) -> BaseChatModel:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ImportError("The qwen provider needs langchain-openai (pip install langchain-openai)") from exc

    base_url = os.getenv("QWEN_BASE_URL")
    if not base_url:
        raise ValueError("QWEN_BASE_URL is required for the qwen provider (e.g. http://vllm:8001/v1)")

    # Qwen3 hybrid thinking: only worth its latency on the adviser; QWEN_ENABLE_THINKING overrides
    thinking_env = os.getenv("QWEN_ENABLE_THINKING")
    enable_thinking = (
        thinking_env.lower() == "true" if thinking_env is not None else settings["thinking"] != "low"
    )
    return ChatOpenAI(
        model=os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL),
        base_url=base_url,
        api_key=os.getenv("QWEN_API_KEY", "EMPTY"),  # vLLM accepts any key unless --api-key is set
        temperature=settings["temperature"],
        max_tokens=settings["max_tokens"],
        timeout=float(os.getenv("QWEN_TIMEOUT", "60")),
        extra_body={"chat_template_kwargs": {"enable_thinking": enable_thinking}},
    )
