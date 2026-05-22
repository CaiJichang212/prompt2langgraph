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
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class PromptPlanResult(BaseModel):
    raw_text: str
    plan: dict | None = None
    diagnostics: list[dict] = Field(default_factory=list)


SYSTEM_PROMPT = """You generate simplified JSON plan objects for prompt2langgraph.
Return only a JSON object compatible with the project's simplified JSON plan format.
Do not include markdown fences or explanations.

The JSON object must conform to this schema:
{
  "name": string (required, workflow name),
  "nodes": [
    {
      "id": string (required, unique node identifier),
      "kind": string (required, one of: "llm", "tool", "retriever", "transform", "router", "human_gate", "join", "side_effect"),
      "executor": string (required, executor reference, e.g. "builtin.echo_llm", "builtin.mock_retriever", "builtin.identity_transform", "builtin.route", "builtin.human_gate", "builtin.join"),
      "inputs": object (optional, mapping of executor input names to state keys or {"state_key": "..."} objects),
      "outputs": object (optional, mapping of executor output names to state keys or {"state_key": "..."} objects),
      "params": object (optional, executor parameters, e.g. {"template": "Answer: {question}"})
    }
  ],
  "edges": [
    {
      "from": string (required, source node id),
      "to": string (required, target node id),
      "kind": string (optional, one of: "linear", "conditional", "loop", "fanout"; defaults to "linear"),
      "condition": object (optional, required when kind="conditional", e.g. {"expr": "confidence < 0.75", "routes": {"true": "node_a", "false": "node_b"}}),
      "loop_guard": object (optional, required when kind="loop", e.g. {"max_iterations": 3}),
      "map": object (optional, required when kind="fanout", e.g. {"items_state_key": "items", "item_state_key": "item", "result_state_key": "results"})
    }
  ],
  "entrypoint": string (optional, id of the first node; if omitted, inferred as the node with no incoming edges),
  "inputs": object (optional, mapping of input names to type strings, e.g. {"question": "string"}),
  "outputs": object (optional, mapping of output names to type strings, e.g. {"answer": "string"})
}

Rules:
- "nodes" must contain at least one node.
- Every edge "from"/"to" must reference an existing node id.
- Use "builtin.echo_llm" for llm nodes, "builtin.identity_transform" for transform nodes, "builtin.route" for router nodes, "builtin.human_gate" for human_gate nodes.
- For conditional edges, "routes" must map "true" and "false" to valid node ids.
- For loop edges, "loop_guard.max_iterations" must be a positive integer.
- For fanout edges, the workflow must define a reducer (e.g. "append") for the result state key.
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
