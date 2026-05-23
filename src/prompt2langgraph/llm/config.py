"""LLM configuration model and loader."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr


class LLMConfig(BaseModel):
    model: str = "qwen-plus"
    base_url: str | None = None
    api_key: SecretStr | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int | None = None
    request_timeout_s: int = 60


def load_llm_config() -> LLMConfig:
    load_dotenv()
    api_key_raw = os.getenv("API_KEY")
    return LLMConfig(
        model=os.getenv("MODEL") or "qwen-plus",
        base_url=os.getenv("BASE_URL"),
        api_key=SecretStr(api_key_raw) if api_key_raw else None,
    )
