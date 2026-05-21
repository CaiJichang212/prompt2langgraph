from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel


class PromptPlannerConfig(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


def load_prompt_planner_config() -> PromptPlannerConfig:
    load_dotenv()
    return PromptPlannerConfig(
        model=os.getenv("MODEL"),
        base_url=os.getenv("BASE_URL"),
        api_key=os.getenv("API_KEY"),
    )
