"""Prompt planner configuration (deprecated: use prompt2langgraph.llm.config instead)."""
from __future__ import annotations

import warnings

from prompt2langgraph.llm.config import load_llm_config


class PromptPlannerConfig:
    """Deprecated: use :class:`prompt2langgraph.llm.config.LLMConfig` instead."""

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key


def load_prompt_planner_config() -> PromptPlannerConfig:
    """Deprecated: use :func:`prompt2langgraph.llm.config.load_llm_config` instead."""
    warnings.warn(
        "load_prompt_planner_config() is deprecated, use load_llm_config() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    config = load_llm_config()
    return PromptPlannerConfig(
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key.get_secret_value() if config.api_key else None,
    )
