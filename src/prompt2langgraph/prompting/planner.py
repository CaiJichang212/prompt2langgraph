from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.diagnostics.report import Diagnostic
from prompt2langgraph.ir.models import WorkflowSpec
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
    diagnostics: list[Diagnostic] = Field(default_factory=list)


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
"""  # noqa: E501


def build_model_client(request: PromptPlanRequest) -> ChatOpenAI:
    from prompt2langgraph.llm.provider import build_llm_client

    return build_llm_client(
        model=request.model,
        base_url=request.base_url,
        api_key=request.api_key,
        temperature=request.temperature,
    )


def _extract_response_content(response: Any) -> str:
    """Extract text content from an LLM response object.

    Handles str, list, None, and other response.content formats.
    """
    raw = response.content
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(str(item) for item in raw)
    if raw is None:
        return ""
    return str(raw)


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
    return PromptPlanResult(raw_text=_extract_response_content(response))


def plan_prompt_to_workflow_spec(
    request: PromptPlanRequest,
    *,
    model_client: object | None = None,
) -> WorkflowSpec:
    result = generate_plan_text(request, model_client=model_client)
    result.plan = parse_prompt_plan_text(result.raw_text)
    return JSONPlanAdapter().parse(result.plan, source="prompt")
