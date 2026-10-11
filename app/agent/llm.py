# Talks to the LLM (Gemini by default, swappable by env) or runs in mock mode.
# Any failure returns nothing, so the agent falls back to rules or templates.

"""LLM access through one code path for every provider, plus mock mode.

The LLM is used at most twice per request: to classify the request and to write the words.
Failures never raise: callers get (None, 0) and fall back to rules or templates.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from app.config import get_settings

log = logging.getLogger(__name__)

PROVIDER_MAP = {
    "gemini": "google_genai",
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
}
TIMEOUT_S = 20
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm")

os.environ.setdefault("LANGSMITH_TRACING", "false")


def _key_for(settings) -> str:
    return {
        "gemini": settings.gemini_api_key.get_secret_value(),
        "openai": settings.openai_api_key.get_secret_value(),
        "anthropic": settings.anthropic_api_key.get_secret_value(),
        "ollama": "local",
    }[settings.llm_provider]


def llm_status() -> str:
    """mock | configured | missing_key. Never calls the model."""
    settings = get_settings()
    if settings.mock_llm:
        return "mock"
    return "configured" if _key_for(settings) else "missing_key"


def get_llm():
    """A chat model, or None in mock mode or when the provider's key is missing."""
    settings = get_settings()
    if llm_status() != "configured":
        return None
    from langchain.chat_models import init_chat_model

    kwargs: dict = {"temperature": 0, "timeout": TIMEOUT_S, "max_retries": 0}
    if settings.llm_provider == "gemini":
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key.get_secret_value()
    elif settings.llm_provider == "openai":
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key.get_secret_value()
    elif settings.llm_provider == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key.get_secret_value()
    else:
        kwargs = {"temperature": 0, "base_url": settings.ollama_base_url}
    return init_chat_model(
        settings.llm_model, model_provider=PROVIDER_MAP[settings.llm_provider], **kwargs
    )


def _tokens(message) -> int:
    usage = getattr(message, "usage_metadata", None) or {}
    return int(usage.get("total_tokens", 0) or 0)


def _text(message) -> str:
    text = getattr(message, "text", None)
    if callable(text):
        text = text()
    if isinstance(text, str) and text:
        return text
    content = getattr(message, "content", "")
    if isinstance(content, list):  # content blocks from thinking models
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _run(fn):
    try:
        return _pool.submit(fn).result(timeout=TIMEOUT_S + 2)
    except FutureTimeout:
        log.warning("LLM call timed out")
    except Exception as exc:  # noqa: BLE001 - any provider error falls back
        log.warning("LLM call failed: %s", type(exc).__name__)
    return None


def call_structured(schema, system: str, user: str):
    """(parsed object or None, tokens)."""
    llm = get_llm()
    if llm is None:
        return None, 0

    def invoke():
        out = llm.with_structured_output(schema, include_raw=True).invoke(
            [("system", system), ("human", user)]
        )
        return out.get("parsed"), _tokens(out.get("raw"))

    result = _run(invoke)
    if not result or result[0] is None:
        return None, (result[1] if result else 0)
    return result


def call_text(system: str, user: str):
    """(text or None, tokens)."""
    llm = get_llm()
    if llm is None:
        return None, 0

    def invoke():
        message = llm.invoke([("system", system), ("human", user)])
        return _text(message).strip() or None, _tokens(message)

    return _run(invoke) or (None, 0)
