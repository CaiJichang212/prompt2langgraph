"""Unified LLM client construction."""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from prompt2langgraph.llm.config import LLMConfig, load_llm_config


def build_llm_client(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout_s: int | None = None,
) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    config = load_llm_config()
    effective_api_key = api_key or (config.api_key.get_secret_value() if config.api_key else None)
    return ChatOpenAI(
        model=model or config.model,
        base_url=base_url or config.base_url,
        api_key=effective_api_key,
        temperature=temperature if temperature is not None else config.temperature,
        max_tokens=max_tokens if max_tokens is not None else config.max_tokens,
        request_timeout=timeout_s or config.request_timeout_s,
    )
