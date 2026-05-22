from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.prompting.config import load_prompt_planner_config
from prompt2langgraph.prompting.parser import parse_prompt_plan_text

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


class PromptPlanRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0


class PromptPlanResult(BaseModel):
    raw_text: str
    plan: dict | None = None
    diagnostics: list[dict] = Field(default_factory=list)


SYSTEM_PROMPT = """You generate simplified JSON plan objects for prompt2langgraph.
Return only a JSON object compatible with the project's simplified JSON plan format.
Do not include markdown fences or explanations.
"""


def build_model_client(request: PromptPlanRequest) -> ChatOpenAI:
    from langchain_openai import ChatOpenAI

    config = load_prompt_planner_config()
    return ChatOpenAI(
        model=request.model or config.model or "qwen-plus",
        base_url=request.base_url or config.base_url,
        api_key=request.api_key or config.api_key,
        temperature=request.temperature,
    )


def generate_plan_text(
    request: PromptPlanRequest,
    *,
    model_client: object | None = None,
) -> PromptPlanResult:
    client = model_client or build_model_client(request)
    response = client.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.prompt},
        ]
    )
    raw = response.content
    if isinstance(raw, str):
        content = raw
    elif isinstance(raw, list):
        content = "".join(str(item) for item in raw)
    elif raw is None:
        content = ""
    else:
        content = str(raw)
    return PromptPlanResult(raw_text=content)


def plan_prompt_to_workflow_spec(
    request: PromptPlanRequest,
    *,
    model_client: object | None = None,
) -> WorkflowSpec:
    result = generate_plan_text(request, model_client=model_client)
    result.plan = parse_prompt_plan_text(result.raw_text)
    return JSONPlanAdapter().parse(result.plan, source="prompt")
